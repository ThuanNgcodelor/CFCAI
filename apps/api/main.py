import json
import logging

# pyrefly: ignore[missing-import]
from fastapi import FastAPI, Header, HTTPException, Request
# pyrefly: ignore[missing-import]
from fastapi.responses import JSONResponse, PlainTextResponse
# pyrefly: ignore[missing-import]
from pydantic import BaseModel

from src.chatbot.core.settings import settings
from src.chatbot.infrastructure.db.migrations import apply_migrations
from src.chatbot.infrastructure.messaging.inbox import durable_inbox
from src.chatbot.modules.channels.meta.normalizer import (
    normalize_messenger_payload,
    resolve_page_code,
)
from src.chatbot.modules.channels.meta.signature import verify_meta_signature
from src.chatbot.modules.conversations.repository import PostgresConversationRepository
from src.chatbot.modules.integrations.excel.importer import ExcelCatalogImporter
from src.chatbot.modules.integrations.excel.repository import CatalogPublishRepository
from src.chatbot.modules.integrations.misa.warmer import amis_warmer
from src.chatbot.modules.ops.controls import build_ops_control_store
from src.chatbot.shared.enums import PageCode

logger = logging.getLogger(__name__)
ops_controls = build_ops_control_store()

if settings.INBOX_BACKEND.lower() == "postgres":
    apply_migrations(settings.get_database_url())


class TakeoverRequest(BaseModel):
    actor: str
    reason: str


class RecordReviewRequest(BaseModel):
    record_type: str
    record_id: str
    decision: str

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
        # pyrefly: ignore[missing-import]
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
    repository = CatalogPublishRepository(settings.get_database_url())
    importer = ExcelCatalogImporter(repository=repository)
    reports = importer.import_all()
    return {
        "status": "ok",
        "batches": reports,
        "total_staged_faqs": len(importer.staged_faqs),
        "total_staged_products": len(importer.staged_products),
        "conflicts": importer.conflicts,
    }


@app.post("/admin/catalog/import-batches/{page_id}/{batch_id}/approve")
async def approve_import_batch(page_id: PageCode, batch_id: str):
    repository = CatalogPublishRepository(settings.get_database_url())
    try:
        count = repository.approve_batch(page_id, batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"page_id": page_id.value, "batch_id": batch_id, "approved_count": count}


@app.post("/admin/catalog/import-batches/{page_id}/{batch_id}/reject")
async def reject_import_batch(page_id: PageCode, batch_id: str):
    repository = CatalogPublishRepository(settings.get_database_url())
    try:
        count = repository.reject_batch(page_id, batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"page_id": page_id.value, "batch_id": batch_id, "rejected_count": count}


@app.post("/admin/catalog/import-batches/{page_id}/{batch_id}/review-record")
async def review_import_record(
    page_id: PageCode, batch_id: str, request: RecordReviewRequest
):
    repository = CatalogPublishRepository(settings.get_database_url())
    try:
        changed = repository.review_record(
            page_id,
            batch_id,
            record_type=request.record_type,
            record_id=request.record_id,
            decision=request.decision,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not changed:
        raise HTTPException(status_code=404, detail="Record not found in page-scoped batch")
    return {"page_id": page_id.value, "batch_id": batch_id, "reviewed": True}


@app.get("/admin/catalog/import-batches/{page_id}/{batch_id}/records")
async def list_import_records(
    page_id: PageCode, batch_id: str, limit: int = 100, offset: int = 0
):
    repository = CatalogPublishRepository(settings.get_database_url())
    try:
        records = repository.list_records(
            page_id, batch_id, limit=limit, offset=offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "page_id": page_id.value,
        "batch_id": batch_id,
        "limit": limit,
        "offset": offset,
        "records": records,
    }


@app.post("/admin/catalog/import-batches/{page_id}/{batch_id}/publish")
async def publish_import_batch(page_id: PageCode, batch_id: str):
    repository = CatalogPublishRepository(settings.get_database_url())
    try:
        version = repository.publish_batch(page_id, batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"page_id": page_id.value, "batch_id": batch_id, "version": version}


@app.post("/admin/catalog/publications/{page_id}/{version}/rollback")
async def rollback_publication(page_id: PageCode, version: int):
    repository = CatalogPublishRepository(settings.get_database_url())
    try:
        batch_id = repository.rollback(page_id, version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"page_id": page_id.value, "version": version, "batch_id": batch_id}


@app.post("/admin/conversations/{page_id}/{conversation_id:path}/takeover")
async def takeover_conversation(
    page_id: PageCode, conversation_id: str, request: TakeoverRequest
):
    repository = PostgresConversationRepository(settings.get_database_url())
    try:
        state = repository.takeover(
            page_id,
            conversation_id,
            actor=request.actor,
            reason=request.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "page_id": state.page_id.value,
        "conversation_id": state.conversation_id,
        "ownership": state.ownership.value,
        "version": state.version,
        "batch_version": state.batch_version,
    }


@app.post("/admin/conversations/{page_id}/{conversation_id:path}/resume")
async def resume_conversation(
    page_id: PageCode, conversation_id: str, request: TakeoverRequest
):
    repository = PostgresConversationRepository(settings.get_database_url())
    try:
        state = repository.resume(
            page_id,
            conversation_id,
            actor=request.actor,
            reason=request.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "page_id": state.page_id.value,
        "conversation_id": state.conversation_id,
        "ownership": state.ownership.value,
        "version": state.version,
        "batch_version": state.batch_version,
    }


@app.post("/admin/knowledge/approve/{record_id}")
async def approve_knowledge(record_id: str):
    raise HTTPException(
        status_code=410,
        detail="Direct read-model approval is disabled; approve and publish an import batch.",
    )


@app.post("/admin/knowledge/approve-page/{page_id}")
async def approve_page_knowledge(page_id: PageCode):
    raise HTTPException(
        status_code=410,
        detail=(
            f"Direct approval for {page_id.value} is disabled; "
            "approve and publish an import batch."
        ),
    )
