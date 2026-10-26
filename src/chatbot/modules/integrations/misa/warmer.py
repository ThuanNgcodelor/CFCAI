import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from src.chatbot.core.settings import settings
from src.chatbot.modules.integrations.misa.client import AmisCrmClient
from src.chatbot.modules.integrations.misa.schemas import (
    AmisCustomer,
    AmisProduct,
    AmisSaleOrder,
    AmisSyncResult,
)

logger = logging.getLogger(__name__)


class AmisCacheWarmer:
    """
    Pure Python AMIS Cache Warmer.
    Replaces n8n 'AMIS CRM Full Warm — Redis Sync Every 1h' workflow.
    """

    def __init__(self, client: AmisCrmClient | None = None):
        self.client = client or AmisCrmClient()
        self.latest_result: AmisSyncResult | None = None
        self._in_memory_dealers: list[dict[str, Any]] = []
        self._in_memory_products: list[dict[str, Any]] = []
        self._in_memory_orders: dict[str, list[dict[str, Any]]] = {}

    def _hash_data(self, data: Any) -> str:
        s = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    async def read_status(redis_client) -> dict[str, Any] | None:
        raw = await redis_client.get("cfc:sync:status")
        if not raw:
            return None
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return None
        synced_at = parsed.get("synced_at")
        try:
            synced = datetime.fromisoformat(str(synced_at))
            age_seconds = max(0, int((datetime.now(UTC) - synced).total_seconds()))
        except (TypeError, ValueError):
            age_seconds = None
        parsed["age_seconds"] = age_seconds
        parsed["stale"] = (
            age_seconds is None or age_seconds > settings.AMIS_SYNC_FRESHNESS_SECONDS
        )
        return parsed

    @staticmethod
    async def _release_lock(redis_client, token: str) -> None:
        await redis_client.eval(
            """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1])
            end
            return 0
            """,
            1,
            "cfc:sync:lock",
            token,
        )

    async def warm_cache(self, redis_client=None) -> AmisSyncResult:
        logger.info("[AMIS Warmer] Starting sync cycle from MISA AMIS CRM...")

        lock_token: str | None = None
        if redis_client:
            lock_token = uuid.uuid4().hex
            acquired = await redis_client.set(
                "cfc:sync:lock",
                lock_token,
                nx=True,
                ex=settings.AMIS_SYNC_LOCK_SECONDS,
            )
            if not acquired:
                raise RuntimeError(
                    "[AMIS Warmer] Another sync cycle is already running."
                )

        try:
            return await self._warm_locked(redis_client)
        finally:
            if redis_client and lock_token:
                await self._release_lock(redis_client, lock_token)

    async def _warm_locked(self, redis_client=None) -> AmisSyncResult:

        # 1. Fetch Customers
        raw_customers = await self.client.fetch_all_pages("Customers", max_pages=50)
        all_customers = [AmisCustomer(**c, raw_data=c) for c in raw_customers]
        eligible_dealers = [c for c in all_customers if c.is_eligible_dealer]

        # 2. Fetch Products
        raw_products = await self.client.fetch_all_pages("Products", max_pages=20)
        all_products = [AmisProduct(**p, raw_data=p) for p in raw_products]

        # 3. Fetch Sale Orders
        raw_orders = await self.client.fetch_all_pages("SaleOrders", max_pages=300)
        all_orders = [AmisSaleOrder(**o, raw_data=o) for o in raw_orders]
        eligible_orders = [o for o in all_orders if o.is_eligible]

        # 4. Source Count Validation Gates (matching ValidateSourceCounts node in n8n)
        if len(eligible_dealers) < 1 and not settings.DEBUG:
            raise ValueError(
                f"[AMIS Warmer] Too few eligible dealers: {len(eligible_dealers)} (raw: {len(all_customers)})"
            )

        if len(all_products) < 1 and not settings.DEBUG:
            raise ValueError("[AMIS Warmer] No products fetched from AMIS.")

        with_coords = sum(1 for d in eligible_dealers if d.has_coordinates)
        if with_coords < 1 and not settings.AMIS_PILOT_APPROVE_ALL:
            raise ValueError("[AMIS Warmer] Zero locations with GPS coordinates.")

        # 5. Build Snapshot Payloads
        locations_data = [
            {
                "account_id": d.account_id,
                "name": d.account_name,
                "code": d.account_code,
                "address": d.billing_address,
                "latitude": d.latitude,
                "longitude": d.longitude,
                "mobile": d.mobile,
            }
            for d in eligible_dealers
        ]
        products_data = [
            {
                "product_id": p.product_id,
                "code": p.product_code,
                "name": p.product_name,
                "category": p.category,
                "unit": p.unit,
            }
            for p in all_products
        ]

        loc_hash = self._hash_data(locations_data)
        prod_hash = self._hash_data(products_data)

        # Index eligible orders by phone and order code
        import re

        customer_phone_map: dict[str, str] = {}
        for c in all_customers:
            phone = c.effective_phone
            if phone:
                if c.account_code:
                    customer_phone_map[c.account_code] = phone
                if c.account_name:
                    customer_phone_map[c.account_name.lower()] = phone
                if c.account_id:
                    customer_phone_map[c.account_id] = phone
                if c.id:
                    customer_phone_map[c.id] = phone

        orders_by_phone: dict[str, list[dict[str, Any]]] = {}
        orders_by_code: dict[str, dict[str, Any]] = {}
        for o in eligible_orders:
            code = o.effective_code
            status_text = o.delivery_status or o.status or "Đang xử lý"
            date_text = o.effective_date or ""

            phone = o.phone
            if phone:
                clean = re.sub(r"\D", "", str(phone))
                if clean.startswith("84"):
                    clean = "0" + clean[2:]
                phone = clean
            else:
                phone = (
                    customer_phone_map.get(o.account_code or "")
                    or customer_phone_map.get((o.account_name or "").lower())
                    or customer_phone_map.get(o.customer_id or "")
                )

            summary = {
                "order_id": o.order_id or o.id,
                "order_code": code,
                "account_name": o.account_name,
                "status": status_text,
                "order_date": date_text,
                "total_amount": o.total_amount,
                "phone": phone,
            }
            if code:
                orders_by_code[code.upper()] = summary
                lstripped = code.lstrip("0")
                if lstripped and lstripped != code:
                    orders_by_code[lstripped.upper()] = summary
            if phone:
                orders_by_phone.setdefault(phone, []).append(summary)

        # 6. Build the result before atomically switching the Redis snapshot.
        self._in_memory_dealers = locations_data
        self._in_memory_products = products_data
        self._in_memory_orders = orders_by_phone

        now_iso = datetime.now(UTC).isoformat()
        result = AmisSyncResult(
            status="ok",
            source="amis_crm",
            synced_at=now_iso,
            location_count=len(locations_data),
            location_with_coordinates_count=with_coords,
            product_count=len(products_data),
            order_lookup_count=len(eligible_orders),
            loyalty_lookup_count=len(all_customers),
            direct_loyalty_count=len(all_customers),
            locations_snapshot_hash=loc_hash,
            products_snapshot_hash=prod_hash,
        )

        if redis_client:
            sync_id = f"{loc_hash}-{prod_hash}"
            dealers_json = json.dumps(locations_data, ensure_ascii=False)
            products_json = json.dumps(products_data, ensure_ascii=False)
            status_json = result.model_dump_json()
            new_order_keys = {
                *(f"cfc:orders:phone:{phone}" for phone in orders_by_phone),
                *(f"cfc:orders:code:{code}" for code in orders_by_code),
            }
            old_order_index_raw = await redis_client.get("cfc:orders:index")
            old_order_keys = set(json.loads(old_order_index_raw or "[]"))

            pipe = redis_client.pipeline(transaction=True)
            pipe.set(
                f"cfc:snapshots:{sync_id}:dealers",
                dealers_json,
                ex=settings.AMIS_SNAPSHOT_RETENTION_SECONDS,
            )
            pipe.set(
                f"cfc:snapshots:{sync_id}:products",
                products_json,
                ex=settings.AMIS_SNAPSHOT_RETENTION_SECONDS,
            )
            # Compatibility read keys are switched in the same Redis transaction.
            pipe.set("cfc:dealers:locations", dealers_json)
            pipe.set("cfc:products:catalog", products_json)
            pipe.set("cfc:sync:current", sync_id)
            pipe.set("cfc:sync:last_hash", loc_hash)
            pipe.set("cfc:sync:products_hash", prod_hash)
            pipe.set("cfc:sync:status", status_json)
            pipe.set("cfc:orders:index", json.dumps(sorted(new_order_keys)))
            obsolete = sorted(old_order_keys - new_order_keys)
            if obsolete:
                pipe.delete(*obsolete)
            for phone, ord_list in orders_by_phone.items():
                pipe.set(
                    f"cfc:orders:phone:{phone}",
                    json.dumps(ord_list, ensure_ascii=False),
                )
            for code, ord_item in orders_by_code.items():
                pipe.set(
                    f"cfc:orders:code:{code}",
                    json.dumps(ord_item, ensure_ascii=False),
                )
            await pipe.execute()
        self.latest_result = result
        logger.info(
            f"[AMIS Warmer] Sync complete: {result.location_count} dealers, {result.product_count} products, {result.order_lookup_count} orders."
        )
        return result

    def get_dealers(self) -> list[dict[str, Any]]:
        return self._in_memory_dealers

    def get_products(self) -> list[dict[str, Any]]:
        return self._in_memory_products


amis_warmer = AmisCacheWarmer()
