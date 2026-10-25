import json
import logging
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse, PlainTextResponse

from src.chatbot.core.settings import settings
from src.chatbot.modules.channels.meta.signature import verify_meta_signature
from src.chatbot.modules.channels.meta.normalizer import normalize_messenger_payload
from src.chatbot.infrastructure.messaging.inbox import durable_inbox
from src.chatbot.modules.integrations.misa.warmer import amis_warmer
from src.chatbot.modules.integrations.excel.importer import catalog_importer

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CFC–ZEO AI Chatbot Platform",
    description="Customer Service Backend with Meta Webhook, Aggregator, Qwen 8B, and AMIS CRM Warmer",
    version="0.1.0"
)

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "ollama_model": settings.OLLAMA_MODEL_TAG,
        "inbox_events_count": durable_inbox.count_events(),
    }

# ==============================================================================
# Meta Messenger Webhooks (Phase 1)
# ==============================================================================

@app.get("/webhook")
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
async def handle_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None)
):
    """
    Meta Webhook Receiving Endpoint.
    - Validates HMAC-SHA256 signature (fail-closed)
    - Normalizes Messenger payload into InboxEvent
    - Stores into Durable Inbox with Deduplication (T09)
    - Returns HTTP 200 OK immediately
    """
    body_bytes = await request.body()

    # Signature verification (fail-closed if app secret is configured)
    if settings.CFC_APP_SECRET and settings.CFC_APP_SECRET != "default_cfc_secret":
        is_cfc_valid = verify_meta_signature(body_bytes, x_hub_signature_256, settings.CFC_APP_SECRET)
        is_zeo_valid = verify_meta_signature(body_bytes, x_hub_signature_256, settings.ZEO_APP_SECRET)
        if not (is_cfc_valid or is_zeo_valid):
            logger.warning("[Webhook] Signature verification failed.")
            raise HTTPException(status_code=403, detail="Invalid HMAC signature")

    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {str(e)}")

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
            "new_recorded": new_events_count
        }
    )

# ==============================================================================
# MISA AMIS CRM Sync & Warmer Endpoints (Replaces n8n)
# ==============================================================================

@app.post("/admin/misa/sync")
async def sync_misa_cache(x_internal_token: Optional[str] = Header(None)):
    """
    Trigger AMIS CRM cache warming directly from Python.
    Replaces the n8n schedule trigger and sync workflow.
    """
    if settings.AMIS_SYNC_INTERNAL_TOKEN and x_internal_token != settings.AMIS_SYNC_INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid internal token")

    try:
        result = await amis_warmer.warm_cache()
        return JSONResponse(status_code=200, content=result.model_dump())
    except Exception as e:
        logger.error(f"[AMIS Sync Error] {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")

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
        "dealers": amis_warmer.get_dealers()
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
    return {
        "status": "ok",
        "cfc": cfc_res,
        "zeo": zeo_res,
        "total_staged_faqs": len(catalog_importer.staged_faqs),
        "total_staged_products": len(catalog_importer.staged_products),
        "conflicts": catalog_importer.conflicts,
    }
