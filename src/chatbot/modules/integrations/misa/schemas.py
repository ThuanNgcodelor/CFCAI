from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class AmisCustomer(BaseModel):
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    account_code: Optional[str] = None
    account_type: Optional[Any] = None  # KH001, KH002, etc.
    inactive: Optional[bool] = False
    purchase_date_first: Optional[str] = None
    billing_address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    mobile: Optional[str] = None
    raw_data: Dict[str, Any] = Field(default_factory=dict)

    @property
    def is_eligible_dealer(self) -> bool:
        """
        Quy tắc nghiệp vụ từ n8n:
        - Không inactive
        - Phải có purchase_date_first
        - account_type chứa KH001 (Đại lý cấp 1) hoặc KH002 (Đại lý cấp 2)
        """
        if self.inactive:
            return False
        if not self.purchase_date_first:
            return False
        if not self.account_type:
            return False
            
        types = self.account_type if isinstance(self.account_type, list) else [self.account_type]
        for t in types:
            s = str(t)
            if s in ("KH001", "KH002") or "001" in s or "002" in s:
                return True
        return False

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None

class AmisProduct(BaseModel):
    product_id: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    inactive: Optional[bool] = False
    raw_data: Dict[str, Any] = Field(default_factory=dict)

class AmisSaleOrder(BaseModel):
    order_id: Optional[str] = None
    order_code: Optional[str] = None
    customer_id: Optional[str] = None
    status: Optional[str] = None
    order_date: Optional[str] = None
    total_amount: Optional[float] = None
    raw_data: Dict[str, Any] = Field(default_factory=dict)

    @property
    def is_eligible(self) -> bool:
        """
        Quy tắc lọc từ n8n: Loại bỏ các đơn hàng bị hủy hoặc từ chối.
        """
        s = str(self.status or "").lower()
        forbidden = ["huy", "hủy", "tu choi", "từ chối", "cancel", "reject"]
        return not any(f in s for f in forbidden)

class AmisSyncSnapshot(BaseModel):
    snapshot_hash: str
    record_count: int
    data: List[Dict[str, Any]] = Field(default_factory=list)

class AmisSyncResult(BaseModel):
    status: str = "ok"
    source: str = "amis_crm"
    synced_at: str
    location_count: int
    location_with_coordinates_count: int
    product_count: int
    order_lookup_count: int
    loyalty_lookup_count: int
    direct_loyalty_count: int
    locations_snapshot_hash: str
    products_snapshot_hash: str
