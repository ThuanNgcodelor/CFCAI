import json
import logging

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from src.chatbot.core.settings import settings
from src.chatbot.infrastructure.messaging.inbox import durable_inbox
from src.chatbot.modules.channels.meta.normalizer import (
    normalize_messenger_payload,
    resolve_page_code,
)
from src.chatbot.modules.channels.meta.signature import verify_meta_signature
from src.chatbot.modules.integrations.excel.importer import catalog_importer
from src.chatbot.modules.integrations.misa.warmer import amis_warmer
from src.chatbot.modules.knowledge.retriever import PostgresKnowledgeStore
from src.chatbot.modules.ops.controls import build_ops_control_store
from src.chatbot.shared.enums import PageCode

logger = logging.getLogger(__name__)
ops_controls = build_ops_control_store()

app = FastAPI(
    title="CFC–ZEO AI Chatbot Platform",
    description="Customer Service Backend with Meta Webhook, Aggregator, Qwen 8B, and AMIS CRM Warmer",
    version="0.1.0",
)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "ollama_model": settings.OLLAMA_MODEL_TAG,
        "inbox_events_count": durable_inbox.count_events(),
    }


@app.get("/admin/ops/status")
async def ops_status():
    return ops_controls.snapshot()


@app.post("/admin/ops/{page_id}/pause")
async def ops_pause(page_id: str):
    try:
        page = PageCode(page_id.upper())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Unknown page") from exc
    ops_controls.pause(page)
    return {"page_id": page.value, "paused": True}


@app.post("/admin/ops/{page_id}/resume")
async def ops_resume(page_id: str):
    try:
        page = PageCode(page_id.upper())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Unknown page") from exc
    ops_controls.resume(page)
    return {"page_id": page.value, "paused": False}


# ==============================================================================
# Meta Messenger Webhooks (Phase 1)
# ==============================================================================


@app.get("/webhook")
@app.get("/webhooks/meta")
async def verify_webhook(request: Request):
    """
    Meta Webhook Verification Endpoint.
    Validates hub.mode, hub.verify_token and returns hub.challenge.
    """
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode and token:
        if token in (settings.CFC_VERIFY_TOKEN, settings.ZEO_VERIFY_TOKEN):
            return PlainTextResponse(content=challenge, status_code=200)
        raise HTTPException(status_code=403, detail="Verification token mismatch")
    raise HTTPException(status_code=400, detail="Missing verification parameters")


@app.post("/webhook")
@app.post("/webhooks/meta")
async def handle_webhook(
    request: Request, x_hub_signature_256: str | None = Header(None)
):
    """
    Meta Webhook Receiving Endpoint.
    - Validates HMAC-SHA256 signature (fail-closed)
    - Normalizes Messenger payload into InboxEvent
    - Stores into Durable Inbox with Deduplication (T09)
    - Returns HTTP 200 OK immediately
    """
    body_bytes = await request.body()

    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e!s}")

    # Resolve the Page before verifying with its Page-specific secret.  The
    # raw body remains unchanged for HMAC verification.
    entry_ids = {str(entry.get("id", "")) for entry in payload.get("entry", [])}
    if len(entry_ids) != 1:
        raise HTTPException(
            status_code=400, detail="Exactly one configured Page is required"
        )
    try:
        page_code = resolve_page_code(next(iter(entry_ids)))
    except ValueError as exc:
        logger.warning("[Webhook] Unknown Page ID received: %s", next(iter(entry_ids)))
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    app_secret = (
        settings.CFC_APP_SECRET if page_code.value == "CFC" else settings.ZEO_APP_SECRET
    )
    if not app_secret or not verify_meta_signature(
        body_bytes, x_hub_signature_256, app_secret
    ):
        logger.warning(
            "[Webhook] Signature verification failed for page=%s", page_code.value
        )
        raise HTTPException(status_code=403, detail="Invalid HMAC signature")

    # Normalize into InboxEvent list
    events = normalize_messenger_payload(payload)
    new_events_count = 0

    for event in events:
        is_new = durable_inbox.record_event(event)
        if is_new:
            new_events_count += 1

    return JSONResponse(
        status_code=200,
        content={
            "status": "EVENT_RECEIVED",
            "events_count": len(events),
            "new_recorded": new_events_count,
        },
    )


# ==============================================================================
# MISA AMIS CRM Sync & Warmer Endpoints (Replaces n8n)
# ==============================================================================


@app.post("/admin/misa/sync")
async def sync_misa_cache(x_internal_token: str | None = Header(None)):
    """
    Trigger AMIS CRM cache warming directly from Python.
    Replaces the n8n schedule trigger and sync workflow.
    """
    if (
        settings.AMIS_SYNC_INTERNAL_TOKEN
        and x_internal_token != settings.AMIS_SYNC_INTERNAL_TOKEN
    ):
        raise HTTPException(status_code=403, detail="Invalid internal token")

    try:
        import redis.asyncio as redis

        redis_client = redis.Redis.from_url(settings.get_redis_url(), decode_responses=True)
        try:
            result = await amis_warmer.warm_cache(redis_client=redis_client)
        finally:
            await redis_client.aclose()
        return JSONResponse(status_code=200, content=result.model_dump())
    except Exception as e:
        logger.exception("[AMIS Sync Error]")
        raise HTTPException(status_code=500, detail=f"Sync failed: {e!s}")


@app.get("/admin/misa/status")
async def get_misa_sync_status():
    """
    Returns latest AMIS sync summary and counts.
    """
    if not amis_warmer.latest_result:
        return {"status": "pending", "message": "No sync run completed yet."}
    return amis_warmer.latest_result.model_dump()


@app.get("/admin/dealers")
async def get_eligible_dealers():
    """
    Returns eligible dealers (KH001, KH002) for dealer lookup.
    """
    return {
        "count": len(amis_warmer.get_dealers()),
        "dealers": amis_warmer.get_dealers(),
    }


# ==============================================================================
# Excel Staging Import Endpoints (Phase 3)
# ==============================================================================


@app.post("/admin/catalog/import-excel")
async def import_excel_catalog():
    """
    Triggers staging import from docs/CfcCoBayN8n.xlsx and docs/ZeoN8n.xlsx.
    """
    cfc_res = catalog_importer.import_cfc_file()
    zeo_res = catalog_importer.import_zeo_file()
    persisted = catalog_importer.persist_staging()
    return {
        "status": "ok",
        "cfc": cfc_res,
        "zeo": zeo_res,
        "total_staged_faqs": len(catalog_importer.staged_faqs),
        "total_staged_products": len(catalog_importer.staged_products),
        "conflicts": catalog_importer.conflicts,
        "persisted": persisted,
    }


@app.post("/admin/knowledge/approve/{record_id}")
async def approve_knowledge(record_id: str):
    approved = PostgresKnowledgeStore().approve(record_id)
    return {"record_id": record_id, "approved": approved}


@app.post("/admin/knowledge/approve-page/{page_id}")
async def approve_page_knowledge(page_id: PageCode):
    count = PostgresKnowledgeStore().approve_page(page_id)
    return {"page_id": page_id.value, "approved_count": count}
