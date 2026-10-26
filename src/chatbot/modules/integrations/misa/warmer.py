import hashlib
import json
import logging
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

    async def warm_cache(self, redis_client=None) -> AmisSyncResult:
        logger.info("[AMIS Warmer] Starting sync cycle from MISA AMIS CRM...")

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

        # 6. Save in memory and/or write to Redis
        self._in_memory_dealers = locations_data
        self._in_memory_products = products_data

        if redis_client:
            await redis_client.set("cfc:dealers:locations", json.dumps(locations_data))
            await redis_client.set("cfc:products:catalog", json.dumps(products_data))
            await redis_client.set("cfc:sync:last_hash", loc_hash)

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
