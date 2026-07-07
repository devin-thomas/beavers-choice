import ast
import re
import time
from datetime import datetime, timedelta
from difflib import get_close_matches
from typing import Dict, List, Optional, Union

import numpy as np
import pandas as pd
from sqlalchemy import Engine, create_engine
from sqlalchemy.sql import text

from models import InventoryDecision, OrderResult, QuoteLine, RequestItem


db_engine = create_engine("sqlite:///munder_difflin.db")

paper_supplies = [
    {"item_name": "A4 paper", "category": "paper", "unit_price": 0.05},
    {"item_name": "Letter-sized paper", "category": "paper", "unit_price": 0.06},
    {"item_name": "Cardstock", "category": "paper", "unit_price": 0.15},
    {"item_name": "Colored paper", "category": "paper", "unit_price": 0.10},
    {"item_name": "Glossy paper", "category": "paper", "unit_price": 0.20},
    {"item_name": "Matte paper", "category": "paper", "unit_price": 0.18},
    {"item_name": "Recycled paper", "category": "paper", "unit_price": 0.08},
    {"item_name": "Eco-friendly paper", "category": "paper", "unit_price": 0.12},
    {"item_name": "Poster paper", "category": "paper", "unit_price": 0.25},
    {"item_name": "Banner paper", "category": "paper", "unit_price": 0.30},
    {"item_name": "Kraft paper", "category": "paper", "unit_price": 0.10},
    {"item_name": "Construction paper", "category": "paper", "unit_price": 0.07},
    {"item_name": "Wrapping paper", "category": "paper", "unit_price": 0.15},
    {"item_name": "Glitter paper", "category": "paper", "unit_price": 0.22},
    {"item_name": "Decorative paper", "category": "paper", "unit_price": 0.18},
    {"item_name": "Letterhead paper", "category": "paper", "unit_price": 0.12},
    {"item_name": "Legal-size paper", "category": "paper", "unit_price": 0.08},
    {"item_name": "Crepe paper", "category": "paper", "unit_price": 0.05},
    {"item_name": "Photo paper", "category": "paper", "unit_price": 0.25},
    {"item_name": "Uncoated paper", "category": "paper", "unit_price": 0.06},
    {"item_name": "Butcher paper", "category": "paper", "unit_price": 0.10},
    {"item_name": "Heavyweight paper", "category": "paper", "unit_price": 0.20},
    {"item_name": "Standard copy paper", "category": "paper", "unit_price": 0.04},
    {"item_name": "Bright-colored paper", "category": "paper", "unit_price": 0.12},
    {"item_name": "Patterned paper", "category": "paper", "unit_price": 0.15},
    {"item_name": "Paper plates", "category": "product", "unit_price": 0.10},
    {"item_name": "Paper cups", "category": "product", "unit_price": 0.08},
    {"item_name": "Paper napkins", "category": "product", "unit_price": 0.02},
    {"item_name": "Disposable cups", "category": "product", "unit_price": 0.10},
    {"item_name": "Table covers", "category": "product", "unit_price": 1.50},
    {"item_name": "Envelopes", "category": "product", "unit_price": 0.05},
    {"item_name": "Sticky notes", "category": "product", "unit_price": 0.03},
    {"item_name": "Notepads", "category": "product", "unit_price": 2.00},
    {"item_name": "Invitation cards", "category": "product", "unit_price": 0.50},
    {"item_name": "Flyers", "category": "product", "unit_price": 0.15},
    {"item_name": "Party streamers", "category": "product", "unit_price": 0.05},
    {"item_name": "Decorative adhesive tape (washi tape)", "category": "product", "unit_price": 0.20},
    {"item_name": "Paper party bags", "category": "product", "unit_price": 0.25},
    {"item_name": "Name tags with lanyards", "category": "product", "unit_price": 0.75},
    {"item_name": "Presentation folders", "category": "product", "unit_price": 0.50},
    {"item_name": "Large poster paper (24x36 inches)", "category": "large_format", "unit_price": 1.00},
    {"item_name": "Rolls of banner paper (36-inch width)", "category": "large_format", "unit_price": 2.50},
    {"item_name": "100 lb cover stock", "category": "specialty", "unit_price": 0.50},
    {"item_name": "80 lb text paper", "category": "specialty", "unit_price": 0.40},
    {"item_name": "250 gsm cardstock", "category": "specialty", "unit_price": 0.30},
    {"item_name": "220 gsm poster paper", "category": "specialty", "unit_price": 0.35},
]

ITEM_LOOKUP = {item["item_name"].lower(): item for item in paper_supplies}
CATALOG_NAMES = [item["item_name"] for item in paper_supplies]
MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def generate_sample_inventory(supplies: list, coverage: float = 0.4, seed: int = 137) -> pd.DataFrame:
    """Generate the original assignment-style random inventory subset."""
    np.random.seed(seed)
    selected_indices = np.random.choice(
        range(len(supplies)),
        size=int(len(supplies) * coverage),
        replace=False,
    )
    rows = []
    for index in selected_indices:
        item = supplies[index]
        rows.append({
            "item_name": item["item_name"],
            "category": item["category"],
            "unit_price": item["unit_price"],
            "current_stock": int(np.random.randint(200, 800)),
            "min_stock_level": int(np.random.randint(50, 150)),
        })
    return pd.DataFrame(rows)


def init_database(db_engine: Engine, seed: int = 137) -> Engine:
    """Set up transactions, historical quote data, and starting inventory."""
    pd.DataFrame({
        "id": [],
        "item_name": [],
        "transaction_type": [],
        "units": [],
        "price": [],
        "transaction_date": [],
    }).to_sql("transactions", db_engine, if_exists="replace", index=False)

    initial_date = datetime(2025, 1, 1).isoformat()

    quote_requests_df = pd.read_csv("quote_requests.csv")
    quote_requests_df["id"] = range(1, len(quote_requests_df) + 1)
    quote_requests_df.to_sql("quote_requests", db_engine, if_exists="replace", index=False)

    quotes_df = pd.read_csv("quotes.csv")
    quotes_df["request_id"] = range(1, len(quotes_df) + 1)
    quotes_df["order_date"] = initial_date
    if "request_metadata" in quotes_df.columns:
        quotes_df["request_metadata"] = quotes_df["request_metadata"].apply(
            lambda x: ast.literal_eval(x) if isinstance(x, str) else x
        )
        quotes_df["job_type"] = quotes_df["request_metadata"].apply(lambda x: x.get("job_type", ""))
        quotes_df["order_size"] = quotes_df["request_metadata"].apply(lambda x: x.get("order_size", ""))
        quotes_df["event_type"] = quotes_df["request_metadata"].apply(lambda x: x.get("event_type", ""))
    quotes_df = quotes_df[["request_id", "total_amount", "quote_explanation", "order_date", "job_type", "order_size", "event_type"]]
    quotes_df.to_sql("quotes", db_engine, if_exists="replace", index=False)

    inventory_df = generate_sample_inventory(paper_supplies, seed=seed)
    transactions = [{
        "item_name": None,
        "transaction_type": "sales",
        "units": None,
        "price": 50000.0,
        "transaction_date": initial_date,
    }]
    for _, item in inventory_df.iterrows():
        transactions.append({
            "item_name": item["item_name"],
            "transaction_type": "stock_orders",
            "units": int(item["current_stock"]),
            "price": float(item["current_stock"] * item["unit_price"]),
            "transaction_date": initial_date,
        })
    pd.DataFrame(transactions).to_sql("transactions", db_engine, if_exists="append", index=False)
    inventory_df.to_sql("inventory", db_engine, if_exists="replace", index=False)
    return db_engine


def create_transaction(item_name: str, transaction_type: str, quantity: int, price: float, date: Union[str, datetime]) -> int:
    """Record a stock order or sale transaction. The price argument is the total transaction price."""
    if transaction_type not in {"stock_orders", "sales"}:
        raise ValueError("Transaction type must be 'stock_orders' or 'sales'")
    date_str = date.isoformat() if isinstance(date, datetime) else date
    pd.DataFrame([{
        "item_name": item_name,
        "transaction_type": transaction_type,
        "units": quantity,
        "price": price,
        "transaction_date": date_str,
    }]).to_sql("transactions", db_engine, if_exists="append", index=False)
    return int(pd.read_sql("SELECT last_insert_rowid() as id", db_engine).iloc[0]["id"])


def get_all_inventory(as_of_date: str) -> Dict[str, int]:
    """Return positive stock levels as of a date."""
    query = """
        SELECT item_name,
               SUM(CASE
                   WHEN transaction_type = 'stock_orders' THEN units
                   WHEN transaction_type = 'sales' THEN -units
                   ELSE 0
               END) as stock
        FROM transactions
        WHERE item_name IS NOT NULL AND transaction_date <= :as_of_date
        GROUP BY item_name
        HAVING stock > 0
    """
    result = pd.read_sql(query, db_engine, params={"as_of_date": as_of_date})
    return dict(zip(result["item_name"], result["stock"]))


def get_stock_level(item_name: str, as_of_date: Union[str, datetime]) -> pd.DataFrame:
    """Return stock level for one item as of a date."""
    if isinstance(as_of_date, datetime):
        as_of_date = as_of_date.isoformat()
    query = """
        SELECT item_name,
               COALESCE(SUM(CASE
                   WHEN transaction_type = 'stock_orders' THEN units
                   WHEN transaction_type = 'sales' THEN -units
                   ELSE 0
               END), 0) AS current_stock
        FROM transactions
        WHERE item_name = :item_name AND transaction_date <= :as_of_date
    """
    return pd.read_sql(query, db_engine, params={"item_name": item_name, "as_of_date": as_of_date})


def get_stock_quantity(item_name: str, as_of_date: str) -> int:
    df = get_stock_level(item_name, as_of_date)
    if df.empty:
        return 0
    return int(df.iloc[0]["current_stock"] or 0)


def get_supplier_delivery_date(input_date_str: str, quantity: int) -> str:
    """Estimate supplier delivery date from order date and quantity."""
    base_date = datetime.fromisoformat(input_date_str.split("T")[0])
    if quantity <= 10:
        days = 0
    elif quantity <= 100:
        days = 1
    elif quantity <= 1000:
        days = 4
    else:
        days = 7
    return (base_date + timedelta(days=days)).strftime("%Y-%m-%d")


def get_cash_balance(as_of_date: Union[str, datetime]) -> float:
    """Calculate cash balance as of a date."""
    if isinstance(as_of_date, datetime):
        as_of_date = as_of_date.isoformat()
    transactions = pd.read_sql(
        "SELECT * FROM transactions WHERE transaction_date <= :as_of_date",
        db_engine,
        params={"as_of_date": as_of_date},
    )
    sales = transactions.loc[transactions["transaction_type"] == "sales", "price"].sum()
    purchases = transactions.loc[transactions["transaction_type"] == "stock_orders", "price"].sum()
    return float(sales - purchases)


def generate_financial_report(as_of_date: Union[str, datetime]) -> Dict:
    """Generate cash, inventory, and total asset values."""
    if isinstance(as_of_date, datetime):
        as_of_date = as_of_date.isoformat()
    cash = get_cash_balance(as_of_date)
    inventory_df = pd.read_sql("SELECT * FROM inventory", db_engine)
    inventory_value = 0.0
    inventory_summary = []
    for _, item in inventory_df.iterrows():
        stock = get_stock_quantity(item["item_name"], as_of_date)
        value = stock * item["unit_price"]
        inventory_value += value
        inventory_summary.append({
            "item_name": item["item_name"],
            "stock": stock,
            "unit_price": item["unit_price"],
            "value": value,
        })
    return {
        "as_of_date": as_of_date,
        "cash_balance": cash,
        "inventory_value": inventory_value,
        "total_assets": cash + inventory_value,
        "inventory_summary": inventory_summary,
    }


def search_quote_history(search_terms: List[str], limit: int = 5) -> List[Dict]:
    """Search historical quotes for similar customer contexts."""
    conditions = []
    params = {}
    for i, term in enumerate(search_terms):
        param_name = f"term_{i}"
        conditions.append(f"(LOWER(qr.response) LIKE :{param_name} OR LOWER(q.quote_explanation) LIKE :{param_name})")
        params[param_name] = f"%{term.lower()}%"
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    query = f"""
        SELECT qr.response AS original_request, q.total_amount, q.quote_explanation,
               q.job_type, q.order_size, q.event_type, q.order_date
        FROM quotes q
        JOIN quote_requests qr ON q.request_id = qr.id
        WHERE {where_clause}
        ORDER BY q.order_date DESC
        LIMIT {limit}
    """
    with db_engine.connect() as conn:
        return [dict(row._mapping) for row in conn.execute(text(query), params)]


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", value.lower()).strip()


def parse_requested_delivery_date(request_text: str, request_date: str) -> str:
    """Parse dates like 'April 15, 2025'. Fall back to two weeks after request date."""
    match = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})\b",
        request_text,
        flags=re.IGNORECASE,
    )
    if match:
        month = MONTHS[match.group(1).lower()]
        day = int(match.group(2))
        year = int(match.group(3))
        return datetime(year, month, day).strftime("%Y-%m-%d")
    return (datetime.fromisoformat(request_date) + timedelta(days=14)).strftime("%Y-%m-%d")


def strip_order_tail(request_text: str) -> str:
    markers = [
        "I need these supplies delivered",
        "We need these supplies delivered",
        "I need these items delivered",
        "We need these items delivered",
        "Please ensure delivery",
        "Please deliver these supplies",
        "Please deliver the supplies",
        "The supplies are needed",
        "The supplies must be delivered",
        "I need the order delivered",
        "We need the supplies delivered",
    ]
    lowered = request_text.lower()
    cut_positions = [lowered.find(marker.lower()) for marker in markers if lowered.find(marker.lower()) != -1]
    if cut_positions:
        return request_text[: min(cut_positions)]
    return request_text


def prepare_request_text(request_text: str) -> str:
    text_value = strip_order_tail(request_text)
    text_value = re.sub(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b", " ", text_value, flags=re.IGNORECASE)
    text_value = re.sub(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", " ", text_value)
    text_value = text_value.replace("\n", " ")
    text_value = re.sub(r"\s+-\s+", ", ", text_value)
    text_value = re.sub(r"\b(along with|as well as)\b", ", ", text_value, flags=re.IGNORECASE)
    text_value = re.sub(r"\s+and\s+(?=\d[\d,]*\s)", ", ", text_value, flags=re.IGNORECASE)
    text_value = re.sub(r"\b(high-quality|high quality|sturdy)\s*,\s*", r"\1 ", text_value, flags=re.IGNORECASE)
    text_value = re.sub(r"8\s*\.\s*5\s*(?:\"+|inches|inch|in)?\s*x\s*11\s*(?:\"+|inches|inch|in)?", "letter-sized", text_value, flags=re.IGNORECASE)
    return text_value


def clean_item_phrase(raw_item: str) -> str:
    cleaned = raw_item.lower()
    cleaned = cleaned.replace('"', " ").replace("'", " ")
    cleaned = re.sub(r"^\s*(?:sheets?|rolls?|reams?|packets?|packet|units?|unit)\s+(?:of\s+)?", " ", cleaned)
    cleaned = re.sub(r"\([^)]*(?:white|assorted|biodegradable|colors?|inches?)\)", " ", cleaned)
    cleaned = re.sub(r"\b(?:high quality|high-quality|sturdy|various colors|assorted colors|assorted|white|biodegradable|size)\b", " ", cleaned)
    cleaned = re.sub(r"\b(?:for|by|to)\b.*$", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def resolve_item_name(raw_name: str) -> Optional[str]:
    cleaned = normalize_text(raw_name)
    if not cleaned:
        return None
    if any(word in cleaned for word in ["balloon", "ticket", "cardboard"]):
        return None
    if "washi" in cleaned or "decorative adhesive tape" in cleaned:
        return "Decorative adhesive tape (washi tape)"
    if "poster board" in cleaned or ("poster" in cleaned and "24" in cleaned and "36" in cleaned):
        return "Large poster paper (24x36 inches)"
    if cleaned in {"flyer", "flyers"}:
        return "Flyers"
    if cleaned in {"poster", "posters"} or "poster paper" in cleaned:
        return "Poster paper"
    if "streamer" in cleaned:
        return "Party streamers"
    if "disposable cup" in cleaned:
        return "Disposable cups"
    if "paper cup" in cleaned or cleaned == "cups":
        return "Paper cups"
    if "paper plate" in cleaned or cleaned == "plates":
        return "Paper plates"
    if "napkin" in cleaned:
        return "Paper napkins"
    if "envelope" in cleaned:
        return "Envelopes"
    if "cardstock" in cleaned:
        return "Cardstock"
    if "construction" in cleaned:
        return "Construction paper"
    if "kraft" in cleaned:
        return "Kraft paper"
    if "printer" in cleaned or "printing" in cleaned or "copy" in cleaned:
        if "a4" in cleaned:
            return "A4 paper"
        return "Standard copy paper"
    if "a4" in cleaned and "glossy" in cleaned:
        return "Glossy paper"
    if "a4" in cleaned and "matte" in cleaned:
        return "Matte paper"
    if "a4" in cleaned and "recycled" in cleaned:
        return "Recycled paper"
    if cleaned in {"a4 paper", "a4 white paper"}:
        return "A4 paper"
    if cleaned in {"a3 paper", "a3 white paper"}:
        return None
    if "a3" in cleaned and "glossy" in cleaned:
        return "Glossy paper"
    if "a3" in cleaned and "matte" in cleaned:
        return "Matte paper"
    if "a3" in cleaned and "colored" in cleaned:
        return "Colored paper"
    if "a5" in cleaned and "colored" in cleaned:
        return "Colored paper"
    if "letter sized" in cleaned and "colored" in cleaned:
        return "Colored paper"
    if "glossy" in cleaned:
        return "Glossy paper"
    if "matte" in cleaned:
        return "Matte paper"
    if "recycled" in cleaned and "cardstock" not in cleaned:
        return "Recycled paper"
    if "colored" in cleaned or "bright" in cleaned or "colorful" in cleaned:
        if "poster" in cleaned:
            return "Poster paper"
        if "construction" in cleaned:
            return "Construction paper"
        return "Colored paper"
    if "heavyweight" in cleaned:
        return "Heavyweight paper"

    normalized_catalog = {normalize_text(name): name for name in CATALOG_NAMES}
    if cleaned in normalized_catalog:
        return normalized_catalog[cleaned]
    matches = get_close_matches(raw_name, CATALOG_NAMES, n=1, cutoff=0.82)
    return matches[0] if matches else None


def extract_requested_line_items(request_text: str) -> List[RequestItem]:
    text_value = prepare_request_text(request_text)
    pattern = re.compile(
        r"(?P<qty>\d[\d,]*)\s+"
        r"(?:(?P<measure>sheets?|rolls?|roll|reams?|ream|packets?|packet|units?|unit)\s+(?:of\s+)?)?"
        r"(?P<item>[^,\.]+)",
        flags=re.IGNORECASE,
    )
    items: List[RequestItem] = []
    for match in pattern.finditer(text_value):
        quantity = int(match.group("qty").replace(",", ""))
        measure = (match.group("measure") or "").strip()
        item = (match.group("item") or "").strip()
        raw_phrase = f"{measure} {item}".strip()
        cleaned_phrase = clean_item_phrase(raw_phrase)
        items.append(RequestItem(quantity=quantity, raw_item=raw_phrase, item_name=resolve_item_name(cleaned_phrase)))
    return consolidate_request_items(items)


def consolidate_request_items(items: List[RequestItem]) -> List[RequestItem]:
    consolidated: Dict[str, RequestItem] = {}
    output: List[RequestItem] = []
    for item in items:
        if item.item_name:
            if item.item_name not in consolidated:
                consolidated[item.item_name] = RequestItem(
                    quantity=0,
                    raw_item=item.item_name,
                    item_name=item.item_name,
                )
                output.append(consolidated[item.item_name])
            consolidated[item.item_name].quantity += item.quantity
        else:
            output.append(item)
    return output


def calculate_discount(quantity: int) -> float:
    if quantity >= 1000:
        return 0.15
    if quantity >= 500:
        return 0.10
    if quantity >= 100:
        return 0.05
    return 0.0


def get_unit_price(item_name: str) -> float:
    return float(ITEM_LOOKUP[item_name.lower()]["unit_price"])


def get_wholesale_cost(item_name: str, quantity: int) -> float:
    """Internal restock cost. Kept out of customer-facing responses."""
    return get_unit_price(item_name) * quantity * 0.60


def is_firm_order_request(request_text: str) -> bool:
    lower_request = request_text.lower()
    return any(phrase in lower_request for phrase in [
        "place an order",
        "need to order",
        "confirm the order",
        "large order",
        "medium order",
        "small order",
    ])


class IntakeAgent:
    """Extract structured line items and requested delivery date from the customer request."""

    def parse_request(self, request_text: str, request_date: str) -> tuple[List[RequestItem], str, bool]:
        items = extract_requested_line_items(request_text)
        requested_delivery_date = parse_requested_delivery_date(request_text, request_date)
        firm_order = is_firm_order_request(request_text)
        return items, requested_delivery_date, firm_order


class InventoryAgent:
    """Check stock and decide whether reorder can satisfy the requested delivery date."""

    def assess_items(self, items: List[RequestItem], request_date: str, requested_delivery_date: str) -> List[InventoryDecision]:
        decisions: List[InventoryDecision] = []
        for item in items:
            if not item.item_name:
                decisions.append(InventoryDecision(
                    item_name=None,
                    raw_item=item.raw_item,
                    quantity=item.quantity,
                    can_fulfill=False,
                    reason="not carried in the current catalog",
                ))
                continue

            current_stock = get_stock_quantity(item.item_name, request_date)
            missing_quantity = max(0, item.quantity - current_stock)
            if missing_quantity == 0:
                decisions.append(InventoryDecision(
                    item_name=item.item_name,
                    raw_item=item.raw_item,
                    quantity=item.quantity,
                    current_stock=current_stock,
                    can_fulfill=True,
                    reason="available from current stock",
                ))
                continue

            reorder_delivery_date = get_supplier_delivery_date(request_date, missing_quantity)
            can_reorder = reorder_delivery_date <= requested_delivery_date
            decisions.append(InventoryDecision(
                item_name=item.item_name,
                raw_item=item.raw_item,
                quantity=item.quantity,
                current_stock=current_stock,
                missing_quantity=missing_quantity,
                can_fulfill=can_reorder,
                reorder_needed=can_reorder,
                reorder_delivery_date=reorder_delivery_date,
                reason=(
                    f"short {missing_quantity}; reorder arrives {reorder_delivery_date}"
                    if can_reorder
                    else f"short {missing_quantity}; supplier delivery {reorder_delivery_date} misses requested delivery {requested_delivery_date}"
                ),
            ))
        return decisions


class QuotingAgent:
    """Generate quote lines using discount rules and inventory decisions."""

    def generate_quote_lines(self, decisions: List[InventoryDecision]) -> List[QuoteLine]:
        quote_lines: List[QuoteLine] = []
        for decision in decisions:
            if not decision.can_fulfill or not decision.item_name:
                continue
            unit_price = get_unit_price(decision.item_name)
            discount_rate = calculate_discount(decision.quantity)
            final_unit_price = unit_price * (1 - discount_rate)
            delivery_date = decision.reorder_delivery_date or get_supplier_delivery_date("2025-01-01", decision.quantity)
            quote_lines.append(QuoteLine(
                item_name=decision.item_name,
                quantity=decision.quantity,
                unit_price=unit_price,
                discount_rate=discount_rate,
                final_unit_price=final_unit_price,
                line_total=final_unit_price * decision.quantity,
                delivery_date=delivery_date,
                reorder_needed=decision.reorder_needed,
            ))
        return quote_lines


class SalesAgent:
    """Finalize firm orders by recording needed stock orders and sales."""

    def finalize_sale(self, decisions: List[InventoryDecision], quote_lines: List[QuoteLine], request_date: str) -> bool:
        if not decisions or any(not decision.can_fulfill for decision in decisions):
            return False

        for decision in decisions:
            if decision.reorder_needed and decision.item_name and decision.missing_quantity > 0:
                create_transaction(
                    decision.item_name,
                    "stock_orders",
                    decision.missing_quantity,
                    get_wholesale_cost(decision.item_name, decision.missing_quantity),
                    request_date,
                )

        for quote_line in quote_lines:
            create_transaction(
                quote_line.item_name,
                "sales",
                quote_line.quantity,
                quote_line.line_total,
                request_date,
            )
        return True


class OrchestratorAgent:
    """Coordinate intake, inventory, quoting, sales, and reporting."""

    def __init__(self):
        self.intake_agent = IntakeAgent()
        self.inventory_agent = InventoryAgent()
        self.quoting_agent = QuotingAgent()
        self.sales_agent = SalesAgent()

    def process_request(self, request_id: int, source_row: int, row: pd.Series) -> OrderResult:
        request_date = row["request_date"].strftime("%Y-%m-%d")
        cash_before = generate_financial_report(request_date)["cash_balance"]
        inventory_before = generate_financial_report(request_date)["inventory_value"]

        items, requested_delivery_date, firm_order = self.intake_agent.parse_request(row["request"], request_date)
        decisions = self.inventory_agent.assess_items(items, request_date, requested_delivery_date)
        quote_lines = self.quoting_agent.generate_quote_lines(decisions)

        fulfilled_items = [line.item_name for line in quote_lines]
        unfulfilled_items = [decision.raw_item for decision in decisions if not decision.can_fulfill]
        all_fulfillable = bool(decisions) and all(decision.can_fulfill for decision in decisions)
        sale_recorded = firm_order and all_fulfillable and self.sales_agent.finalize_sale(decisions, quote_lines, request_date)

        report_after = generate_financial_report(request_date)
        cash_after = report_after["cash_balance"]
        inventory_after = report_after["inventory_value"]

        if sale_recorded:
            order_status = "fulfilled_sale_recorded"
        elif all_fulfillable:
            order_status = "quote_ready"
        elif quote_lines:
            order_status = "partial_quote_needs_review"
        else:
            order_status = "unfulfilled"

        response = self._format_response(
            decisions,
            quote_lines,
            firm_order,
            sale_recorded,
            requested_delivery_date,
        )

        return OrderResult(
            request_id=request_id,
            source_row=source_row,
            request_date=request_date,
            requested_delivery_date=requested_delivery_date,
            order_status=order_status,
            response=response,
            cash_before=cash_before,
            cash_after=cash_after,
            inventory_before=inventory_before,
            inventory_after=inventory_after,
            fulfilled_items=fulfilled_items,
            unfulfilled_items=unfulfilled_items,
        )

    def _format_response(
        self,
        decisions: List[InventoryDecision],
        quote_lines: List[QuoteLine],
        firm_order: bool,
        sale_recorded: bool,
        requested_delivery_date: str,
    ) -> str:
        lines: List[str] = []
        quote_by_item = {line.item_name: line for line in quote_lines}

        for decision in decisions:
            if not decision.item_name:
                lines.append(f"- {decision.raw_item}: not carried in the current catalog.")
                continue
            if not decision.can_fulfill:
                lines.append(f"- {decision.item_name}: {decision.reason}.")
                continue

            quote_line = quote_by_item[decision.item_name]
            reorder_note = ""
            if decision.reorder_needed:
                reorder_note = f" Reorder needed for {decision.missing_quantity} units; supplier ETA {decision.reorder_delivery_date}."
            lines.append(
                f"- {quote_line.item_name}: {quote_line.quantity} units at ${quote_line.final_unit_price:.2f} each "
                f"({quote_line.discount_rate * 100:.0f}% discount) = ${quote_line.line_total:.2f}; "
                f"deliverable by {requested_delivery_date}.{reorder_note}"
            )

        quote_total = sum(line.line_total for line in quote_lines)
        if sale_recorded:
            lines.append(f"Order total: ${quote_total:.2f}")
            lines.append("The full order has been recorded.")
        elif quote_lines and firm_order:
            lines.append(f"Available/reorderable subtotal: ${quote_total:.2f}")
            lines.append("The full order was not recorded because at least one requested item cannot be fulfilled as requested.")
        elif quote_lines:
            lines.append(f"Estimated quote: ${quote_total:.2f}")
            lines.append("Please confirm if you would like to place this order.")
        else:
            lines.append("No quote was generated because none of the requested items can be fulfilled from the catalog by the requested delivery date.")

        return "\n".join(lines)


def run_test_scenarios():
    print("Initializing Database...")
    init_database(db_engine)
    try:
        quote_requests_sample = pd.read_csv("quote_requests_sample.csv")
        quote_requests_sample["request_date"] = pd.to_datetime(
            quote_requests_sample["request_date"],
            format="%m/%d/%y",
            errors="coerce",
        )
        quote_requests_sample.dropna(subset=["request_date"], inplace=True)
        quote_requests_sample = quote_requests_sample.sort_values("request_date")
    except Exception as e:
        print(f"FATAL: Error loading test data: {e}")
        return []

    print("Using deterministic multi-agent workflow with reorder-aware inventory decisions.")
    orchestrator = OrchestratorAgent()
    initial_date = quote_requests_sample["request_date"].min().strftime("%Y-%m-%d")
    current_report = generate_financial_report(initial_date)

    results: List[OrderResult] = []
    for request_number, (source_index, row) in enumerate(quote_requests_sample.iterrows(), start=1):
        print(f"\n=== Request {request_number} ===")
        print(f"Source Row: {source_index + 1}")
        print(f"Context: {row['job']} organizing {row['event']}")
        print(f"Request Date: {row['request_date'].strftime('%Y-%m-%d')}")
        print(f"Cash Balance: ${current_report['cash_balance']:.2f}")
        print(f"Inventory Value: ${current_report['inventory_value']:.2f}")

        result = orchestrator.process_request(request_number, source_index + 1, row)
        current_report = generate_financial_report(result.request_date)

        print(f"Response: {result.response}")
        print(f"Order Status: {result.order_status}")
        print(f"Updated Cash: ${result.cash_after:.2f}")
        print(f"Updated Inventory: ${result.inventory_after:.2f}")
        results.append(result)
        time.sleep(1)

    final_date = quote_requests_sample["request_date"].max().strftime("%Y-%m-%d")
    final_report = generate_financial_report(final_date)
    print("\n===== FINAL FINANCIAL REPORT =====")
    print(f"Final Cash: ${final_report['cash_balance']:.2f}")
    print(f"Final Inventory: ${final_report['inventory_value']:.2f}")

    pd.DataFrame([
        {
            "request_id": result.request_id,
            "source_row": result.source_row,
            "request_date": result.request_date,
            "requested_delivery_date": result.requested_delivery_date,
            "order_status": result.order_status,
            "cash_before": result.cash_before,
            "cash_after": result.cash_after,
            "cash_changed": result.cash_changed,
            "inventory_before": result.inventory_before,
            "inventory_after": result.inventory_after,
            "fulfilled_items": "; ".join(result.fulfilled_items),
            "unfulfilled_items": "; ".join(result.unfulfilled_items),
            "response": result.response,
        }
        for result in results
    ]).to_csv("test_results.csv", index=False)
    return results
