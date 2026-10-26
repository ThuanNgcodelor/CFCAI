import pytest

from src.chatbot.modules.integrations.misa.schemas import AmisCustomer, AmisSaleOrder
from src.chatbot.modules.integrations.misa.warmer import AmisCacheWarmer


class _FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.operations = []

    def set(self, key, value, **kwargs):
        self.operations.append(("set", key, value, kwargs))
        return self

    def delete(self, *keys):
        self.operations.append(("delete", keys))
        return self

    async def execute(self):
        for operation in self.operations:
            if operation[0] == "set":
                _, key, value, _ = operation
                self.redis.values[key] = value
            else:
                for key in operation[1]:
                    self.redis.values.pop(key, None)


class _FakeRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, *, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def eval(self, script, number_of_keys, key, token):
        if self.values.get(key) == token:
            self.values.pop(key, None)
            return 1
        return 0

    def pipeline(self, transaction=True):
        return _FakePipeline(self)


class _FakeAmisClient:
    async def fetch_all_pages(self, resource, max_pages):
        if resource == "Customers":
            return [
                {
                    "account_id": "dealer-1",
                    "account_name": "Đại lý A",
                    "account_code": "DL-A",
                    "account_type": "KH001",
                    "purchase_date_first": "2026-01-01",
                    "billing_address": "Cần Thơ",
                    "latitude": 10.0,
                    "longitude": 105.0,
                    "mobile": "0900000000",
                }
            ]
        if resource == "Products":
            return [
                {"product_id": "p1", "product_code": "CB1", "product_name": "Cobanic"}
            ]
        return [
            {
                "order_id": "o1",
                "order_code": "SO1",
                "account_code": "DL-A",
                "status": "Mới",
            }
        ]


def test_amis_customer_dealer_eligibility():
    # Eligible dealer: KH001, active, has purchase date
    c1 = AmisCustomer(
        account_id="acc_001",
        account_name="Đại lý Nông nghiệp Cò Bay A",
        account_type="KH001",
        inactive=False,
        purchase_date_first="2024-01-15",
        latitude=10.75,
        longitude=106.67,
    )
    assert c1.is_eligible_dealer is True
    assert c1.has_coordinates is True

    # Ineligible: KH003 (retail customer)
    c2 = AmisCustomer(
        account_id="acc_002",
        account_name="Khách lẻ B",
        account_type="KH003",
        inactive=False,
        purchase_date_first="2024-02-10",
    )
    assert c2.is_eligible_dealer is False

    # Ineligible: Inactive dealer
    c3 = AmisCustomer(
        account_id="acc_003",
        account_name="Đại lý cũ C",
        account_type="KH001",
        inactive=True,
        purchase_date_first="2023-01-01",
    )
    assert c3.is_eligible_dealer is False

    # Ineligible: Never purchased
    c4 = AmisCustomer(
        account_id="acc_004",
        account_name="Đại lý tiềm năng D",
        account_type="KH002",
        inactive=False,
        purchase_date_first=None,
    )
    assert c4.is_eligible_dealer is False


def test_amis_sale_order_eligibility():
    # Valid order
    o1 = AmisSaleOrder(order_id="ord_1", status="Đã giao hàng")
    assert o1.is_eligible is True

    # Cancelled orders in Vietnamese and English
    assert AmisSaleOrder(order_id="ord_2", status="Đã hủy").is_eligible is False
    assert AmisSaleOrder(order_id="ord_3", status="Từ chối").is_eligible is False
    assert AmisSaleOrder(order_id="ord_4", status="Cancelled").is_eligible is False
    assert AmisSaleOrder(order_id="ord_5", status="Rejected").is_eligible is False


def test_amis_warmer_hashing():
    warmer = AmisCacheWarmer()
    data = [{"name": "Cobanic", "sku": "CB-01"}]
    h1 = warmer._hash_data(data)
    h2 = warmer._hash_data(data)
    assert h1 == h2
    assert len(h1) == 16


async def test_amis_warmer_switches_atomic_snapshot_and_persists_status():
    redis = _FakeRedis()
    warmer = AmisCacheWarmer(client=_FakeAmisClient())

    result = await warmer.warm_cache(redis_client=redis)
    status = await warmer.read_status(redis)

    assert result.location_count == 1
    assert redis.values["cfc:sync:current"]
    assert redis.values["cfc:dealers:locations"]
    assert redis.values["cfc:products:catalog"]
    assert "cfc:sync:lock" not in redis.values
    assert status is not None
    assert status["status"] == "ok"
    assert status["stale"] is False


async def test_amis_warmer_refuses_concurrent_sync():
    redis = _FakeRedis()
    redis.values["cfc:sync:lock"] = "other"
    warmer = AmisCacheWarmer(client=_FakeAmisClient())

    with pytest.raises(RuntimeError, match="already running"):
        await warmer.warm_cache(redis_client=redis)
