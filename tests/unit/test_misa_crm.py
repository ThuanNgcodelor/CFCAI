from src.chatbot.modules.integrations.misa.schemas import AmisCustomer, AmisSaleOrder, AmisProduct
from src.chatbot.modules.integrations.misa.warmer import AmisCacheWarmer

def test_amis_customer_dealer_eligibility():
    # Eligible dealer: KH001, active, has purchase date
    c1 = AmisCustomer(
        account_id="acc_001",
        account_name="Đại lý Nông nghiệp Cò Bay A",
        account_type="KH001",
        inactive=False,
        purchase_date_first="2024-01-15",
        latitude=10.75,
        longitude=106.67
    )
    assert c1.is_eligible_dealer is True
    assert c1.has_coordinates is True

    # Ineligible: KH003 (retail customer)
    c2 = AmisCustomer(
        account_id="acc_002",
        account_name="Khách lẻ B",
        account_type="KH003",
        inactive=False,
        purchase_date_first="2024-02-10"
    )
    assert c2.is_eligible_dealer is False

    # Ineligible: Inactive dealer
    c3 = AmisCustomer(
        account_id="acc_003",
        account_name="Đại lý cũ C",
        account_type="KH001",
        inactive=True,
        purchase_date_first="2023-01-01"
    )
    assert c3.is_eligible_dealer is False

    # Ineligible: Never purchased
    c4 = AmisCustomer(
        account_id="acc_004",
        account_name="Đại lý tiềm năng D",
        account_type="KH002",
        inactive=False,
        purchase_date_first=None
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
