from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RequestItem:
    """A parsed quantity/item pair from a customer request."""
    quantity: int
    raw_item: str
    item_name: Optional[str]


@dataclass
class InventoryDecision:
    """Inventory agent decision for one requested item."""
    item_name: Optional[str]
    raw_item: str
    quantity: int
    current_stock: int = 0
    missing_quantity: int = 0
    can_fulfill: bool = False
    reorder_needed: bool = False
    reorder_delivery_date: Optional[str] = None
    reason: str = ""


@dataclass
class QuoteLine:
    """Customer-facing quote line for one inventory decision."""
    item_name: str
    quantity: int
    unit_price: float
    discount_rate: float
    final_unit_price: float
    line_total: float
    delivery_date: str
    reorder_needed: bool = False


@dataclass
class OrderResult:
    """Full orchestrator result for one customer request."""
    request_id: int
    source_row: int
    request_date: str
    requested_delivery_date: str
    order_status: str
    response: str
    cash_before: float
    cash_after: float
    inventory_before: float
    inventory_after: float
    fulfilled_items: List[str] = field(default_factory=list)
    unfulfilled_items: List[str] = field(default_factory=list)

    @property
    def cash_changed(self) -> bool:
        return round(self.cash_before, 2) != round(self.cash_after, 2)
