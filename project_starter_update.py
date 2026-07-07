import ast
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

try:
    from pydantic_ai import Agent, RunContext
except ImportError as exc:
    raise RuntimeError(
        "pydantic-ai is required for this submission because each agent must execute through the framework."
    ) from exc

FRAMEWORK_NAME = "pydantic-ai"


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("BEAVERS_CHOICE_DB_PATH", BASE_DIR / "munder_difflin.db"))
AGENT_MODEL = os.getenv("BEAVERS_CHOICE_AGENT_MODEL", "openai:gpt-4o-mini")

# Udacity's workspace often provides an OpenAI-compatible key under this name.
# pydantic-ai's OpenAI provider expects OPENAI_API_KEY, so mirror it when needed.
if not os.getenv("OPENAI_API_KEY") and os.getenv("UDACITY_OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = os.environ["UDACITY_OPENAI_API_KEY"]

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

ITEM_BY_NAME = {item["item_name"]: item for item in paper_supplies}
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


def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def generate_sample_inventory(supplies: list, coverage: float = 0.4, seed: int = 137) -> pd.DataFrame:
    """Generate reproducible starting inventory for a subset of the catalog."""
    np.random.seed(seed)
    selected_indices = np.random.choice(range(len(supplies)), size=int(len(supplies) * coverage), replace=False)
    rows = []
    for index in selected_indices:
        item = supplies[index]
        rows.append(
            {
                "item_name": item["item_name"],
                "category": item["category"],
                "unit_price": item["unit_price"],
                "current_stock": int(np.random.randint(200, 800)),
                "min_stock_level": int(np.random.randint(50, 150)),
            }
        )
    return pd.DataFrame(rows)


def init_database(seed: int = 137) -> None:
    """Set up transactions, historical quote data, and starting inventory."""
    with get_connection() as conn:
        pd.DataFrame(
            {
                "id": [],
                "item_name": [],
                "transaction_type": [],
                "units": [],
                "price": [],
                "transaction_date": [],
            }
        ).to_sql("transactions", conn, if_exists="replace", index=False)

        quote_requests_df = pd.read_csv(BASE_DIR / "quote_requests.csv")
        quote_requests_df["id"] = range(1, len(quote_requests_df) + 1)
        quote_requests_df.to_sql("quote_requests", conn, if_exists="replace", index=False)

        quotes_df = pd.read_csv(BASE_DIR / "quotes.csv")
        quotes_df["request_id"] = range(1, len(quotes_df) + 1)
        quotes_df["order_date"] = datetime(2025, 1, 1).isoformat()
        if "request_metadata" in quotes_df.columns:
            quotes_df["request_metadata"] = quotes_df["request_metadata"].apply(
                lambda value: ast.literal_eval(value) if isinstance(value, str) else value
            )
            quotes_df["job_type"] = quotes_df["request_metadata"].apply(lambda value: value.get("job_type", ""))
            quotes_df["order_size"] = quotes_df["request_metadata"].apply(lambda value: value.get("order_size", ""))
            quotes_df["event_type"] = quotes_df["request_metadata"].apply(lambda value: value.get("event_type", ""))
        quotes_df = quotes_df[
            ["request_id", "total_amount", "quote_explanation", "order_date", "job_type", "order_size", "event_type"]
        ]
        quotes_df.to_sql("quotes", conn, if_exists="replace", index=False)

        inventory_df = generate_sample_inventory(paper_supplies, seed=seed)
        inventory_df.to_sql("inventory", conn, if_exists="replace", index=False)

        initial_date = datetime(2025, 1, 1).isoformat()
        transactions = [
            {
                "item_name": None,
                "transaction_type": "sales",
                "units": None,
                "price": 50000.0,
                "transaction_date": initial_date,
            }
        ]
        for _, item in inventory_df.iterrows():
            transactions.append(
                {
                    "item_name": item["item_name"],
                    "transaction_type": "stock_orders",
                    "units": int(item["current_stock"]),
                    "price": float(item["current_stock"] * item["unit_price"]),
                    "transaction_date": initial_date,
                }
            )
        pd.DataFrame(transactions).to_sql("transactions", conn, if_exists="append", index=False)


def ensure_inventory_reference(item_name: str) -> None:
    if item_name not in ITEM_BY_NAME:
        return
    with get_connection() as conn:
        existing = pd.read_sql_query("SELECT item_name FROM inventory WHERE item_name = ?", conn, params=(item_name,))
        if existing.empty:
            item = ITEM_BY_NAME[item_name]
            pd.DataFrame(
                [
                    {
                        "item_name": item["item_name"],
                        "category": item["category"],
                        "unit_price": item["unit_price"],
                        "current_stock": 0,
                        "min_stock_level": 100,
                    }
                ]
            ).to_sql("inventory", conn, if_exists="append", index=False)


def create_transaction(item_name: str, transaction_type: str, quantity: int, price: float, date: Union[str, datetime]) -> int:
    """Record a stock order or sale transaction."""
    if transaction_type not in {"stock_orders", "sales"}:
        raise ValueError("Transaction type must be 'stock_orders' or 'sales'")
    if quantity <= 0:
        raise ValueError("Quantity must be positive")
    if item_name:
        ensure_inventory_reference(item_name)
    date_str = date.isoformat() if isinstance(date, datetime) else date
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO transactions (item_name, transaction_type, units, price, transaction_date)
            VALUES (?, ?, ?, ?, ?)
            """,
            (item_name, transaction_type, quantity, price, date_str),
        )
        conn.commit()
        return int(cursor.lastrowid)


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
        WHERE item_name IS NOT NULL AND transaction_date <= ?
        GROUP BY item_name
        HAVING stock > 0
    """
    with get_connection() as conn:
        result = pd.read_sql_query(query, conn, params=(as_of_date,))
    return dict(zip(result["item_name"], result["stock"]))


def get_stock_level(item_name: str, as_of_date: Union[str, datetime]) -> pd.DataFrame:
    """Return stock level for one item as of a date."""
    date_str = as_of_date.isoformat() if isinstance(as_of_date, datetime) else as_of_date
    query = """
        SELECT ? AS item_name,
               COALESCE(SUM(CASE
                   WHEN transaction_type = 'stock_orders' THEN units
                   WHEN transaction_type = 'sales' THEN -units
                   ELSE 0
               END), 0) AS current_stock
        FROM transactions
        WHERE item_name = ? AND transaction_date <= ?
    """
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=(item_name, item_name, date_str))


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
    date_str = as_of_date.isoformat() if isinstance(as_of_date, datetime) else as_of_date
    with get_connection() as conn:
        transactions = pd.read_sql_query("SELECT * FROM transactions WHERE transaction_date <= ?", conn, params=(date_str,))
    sales = transactions.loc[transactions["transaction_type"] == "sales", "price"].sum()
    purchases = transactions.loc[transactions["transaction_type"] == "stock_orders", "price"].sum()
    return float(sales - purchases)


def get_stock_quantity(item_name: str, as_of_date: str) -> int:
    stock_df = get_stock_level(item_name, as_of_date)
    return int(stock_df.iloc[0]["current_stock"] or 0) if not stock_df.empty else 0


def generate_financial_report(as_of_date: Union[str, datetime]) -> Dict:
    """Generate cash, inventory, and total asset values."""
    date_str = as_of_date.isoformat() if isinstance(as_of_date, datetime) else as_of_date
    cash = get_cash_balance(date_str)
    with get_connection() as conn:
        inventory_df = pd.read_sql_query("SELECT * FROM inventory", conn)
    inventory_value = 0.0
    inventory_summary = []
    for _, item in inventory_df.iterrows():
        stock = get_stock_quantity(item["item_name"], date_str)
        value = float(stock * item["unit_price"])
        inventory_value += value
        inventory_summary.append(
            {
                "item_name": item["item_name"],
                "stock": stock,
                "unit_price": float(item["unit_price"]),
                "value": value,
            }
        )
    return {
        "as_of_date": date_str,
        "cash_balance": cash,
        "inventory_value": inventory_value,
        "total_assets": cash + inventory_value,
        "inventory_summary": inventory_summary,
    }


def search_quote_history(search_terms: List[str], limit: int = 5) -> List[Dict]:
    """Search historical quotes for comparable prior requests."""
    conditions = []
    params: List[Union[str, int]] = []
    for term in search_terms:
        conditions.append("(LOWER(qr.response) LIKE ? OR LOWER(q.quote_explanation) LIKE ?)")
        params.extend([f"%{term.lower()}%", f"%{term.lower()}%"])
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    query = f"""
        SELECT qr.response AS original_request, q.total_amount, q.quote_explanation,
               q.job_type, q.order_size, q.event_type, q.order_date
        FROM quotes q
        JOIN quote_requests qr ON q.request_id = qr.id
        WHERE {where_clause}
        ORDER BY q.order_date DESC
        LIMIT ?
    """
    params.append(limit)
    with get_connection() as conn:
        result = conn.execute(query, params)
        columns = [column[0] for column in result.description]
        return [dict(zip(columns, row)) for row in result.fetchall()]


class RequestedItem(BaseModel):
    quantity: int = Field(ge=1)
    raw_item: str
    item_name: Optional[str] = None


class ParsedRequest(BaseModel):
    request_date: str
    requested_delivery_date: str
    firm_order: bool
    items: List[RequestedItem]


class InventoryAssessment(BaseModel):
    item_name: Optional[str]
    raw_item: str
    quantity: int
    current_stock: int = 0
    missing_quantity: int = 0
    can_fulfill: bool = False
    reorder_needed: bool = False
    reorder_delivery_date: Optional[str] = None
    reason: str


class QuoteLine(BaseModel):
    item_name: str
    quantity: int
    list_unit_price: float
    discount_rate: float
    quoted_unit_price: float
    line_total: float
    delivery_date: str
    rationale: str
    reorder_needed: bool = False


class QuoteProposal(BaseModel):
    lines: List[QuoteLine] = Field(default_factory=list)
    total: float = 0.0
    historical_context: str = ""


class SalesDecision(BaseModel):
    sale_recorded: bool
    transaction_ids: List[int] = Field(default_factory=list)
    reason: str


class ResponseEvaluation(BaseModel):
    passed: bool
    findings: List[str] = Field(default_factory=list)


class WorkflowResult(BaseModel):
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
    fulfilled_items: List[str] = Field(default_factory=list)
    unfulfilled_items: List[str] = Field(default_factory=list)
    agent_route: str
    tool_calls: List[str] = Field(default_factory=list)
    evaluation_passed: bool = False
    evaluation_findings: List[str] = Field(default_factory=list)

    @property
    def cash_changed(self) -> bool:
        return round(self.cash_before, 2) != round(self.cash_after, 2)


@dataclass
class ToolAudit:
    agent_name: str
    tool_name: str
    detail: str

    def format(self) -> str:
        return f"{self.agent_name}.{self.tool_name}: {self.detail}"


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", value.lower()).strip()


def parse_requested_delivery_date(request_text: str, request_date: str) -> str:
    match = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})\b",
        request_text,
        flags=re.IGNORECASE,
    )
    if match:
        return datetime(int(match.group(3)), MONTHS[match.group(1).lower()], int(match.group(2))).strftime("%Y-%m-%d")
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
    positions = [lowered.find(marker.lower()) for marker in markers if lowered.find(marker.lower()) != -1]
    return request_text[: min(positions)] if positions else request_text


def prepare_request_text(request_text: str) -> str:
    text_value = strip_order_tail(request_text)
    text_value = re.sub(
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b",
        " ",
        text_value,
        flags=re.IGNORECASE,
    )
    text_value = re.sub(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", " ", text_value)
    text_value = text_value.replace("\n", " ")
    text_value = re.sub(r"\s+-\s+", ", ", text_value)
    text_value = re.sub(r"\b(along with|as well as)\b", ", ", text_value, flags=re.IGNORECASE)
    text_value = re.sub(r"\s+and\s+(?=\d[\d,]*\s)", ", ", text_value, flags=re.IGNORECASE)
    text_value = re.sub(r"\b(high-quality|high quality|sturdy)\s*,\s*", r"\1 ", text_value, flags=re.IGNORECASE)
    text_value = re.sub(
        r"8\s*\.\s*5\s*(?:\"+|inches|inch|in)?\s*x\s*11\s*(?:\"+|inches|inch|in)?",
        "letter-sized",
        text_value,
        flags=re.IGNORECASE,
    )
    return text_value


def clean_item_phrase(raw_item: str) -> str:
    cleaned = raw_item.lower().replace('"', " ").replace("'", " ")
    cleaned = re.sub(r"^\s*(?:sheets?|rolls?|roll|reams?|ream|packets?|packet|units?|unit)\s+(?:of\s+)?", " ", cleaned)
    cleaned = re.sub(r"\([^)]*(?:white|assorted|biodegradable|colors?|inches?)\)", " ", cleaned)
    cleaned = re.sub(
        r"\b(?:high quality|high-quality|sturdy|various colors|assorted colors|assorted|white|biodegradable|size)\b",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"\b(?:for|by|to)\b.*$", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def resolve_item_name(raw_name: str) -> Optional[str]:
    cleaned = normalize_text(raw_name)
    if not cleaned or any(word in cleaned for word in ["balloon", "ticket", "cardboard"]):
        return None
    normalized_catalog = {normalize_text(name): name for name in CATALOG_NAMES}
    if cleaned in normalized_catalog:
        return normalized_catalog[cleaned]
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
        return "A4 paper" if "a4" in cleaned else "Standard copy paper"
    if "a3" in cleaned and "glossy" in cleaned:
        return "Glossy paper"
    if "a3" in cleaned and "matte" in cleaned:
        return "Matte paper"
    if "a3" in cleaned and "colored" in cleaned:
        return "Colored paper"
    if "a3" in cleaned:
        return None
    if "a4" in cleaned and "glossy" in cleaned:
        return "Glossy paper"
    if "a4" in cleaned and "matte" in cleaned:
        return "Matte paper"
    if "a4" in cleaned and "recycled" in cleaned:
        return "Recycled paper"
    if "glossy" in cleaned:
        return "Glossy paper"
    if "matte" in cleaned:
        return "Matte paper"
    if "recycled" in cleaned and "cardstock" not in cleaned:
        return "Recycled paper"
    if "colored" in cleaned or "bright" in cleaned or "colorful" in cleaned:
        return "Poster paper" if "poster" in cleaned else "Colored paper"
    if "heavyweight" in cleaned:
        return "Heavyweight paper"
    matches = get_close_matches(raw_name, CATALOG_NAMES, n=1, cutoff=0.82)
    return matches[0] if matches else None


def extract_requested_line_items(request_text: str) -> List[RequestedItem]:
    pattern = re.compile(
        r"(?P<qty>\d[\d,]*)\s+"
        r"(?:(?P<measure>sheets?|rolls?|roll|reams?|ream|packets?|packet|units?|unit)\s+(?:of\s+)?)?"
        r"(?P<item>[^,\.]+)",
        flags=re.IGNORECASE,
    )
    items: List[RequestedItem] = []
    for match in pattern.finditer(prepare_request_text(request_text)):
        quantity = int(match.group("qty").replace(",", ""))
        raw_phrase = f"{(match.group('measure') or '').strip()} {(match.group('item') or '').strip()}".strip()
        cleaned_phrase = clean_item_phrase(raw_phrase)
        items.append(RequestedItem(quantity=quantity, raw_item=raw_phrase, item_name=resolve_item_name(cleaned_phrase)))
    return consolidate_request_items(items)


def consolidate_request_items(items: List[RequestedItem]) -> List[RequestedItem]:
    consolidated: Dict[str, RequestedItem] = {}
    output: List[RequestedItem] = []
    for item in items:
        if not item.item_name:
            output.append(item)
            continue
        if item.item_name not in consolidated:
            consolidated[item.item_name] = RequestedItem(
                quantity=item.quantity,
                raw_item=item.item_name,
                item_name=item.item_name,
            )
            output.append(consolidated[item.item_name])
        else:
            consolidated[item.item_name].quantity += item.quantity
    return output


def is_firm_order_request(request_text: str) -> bool:
    lower_request = request_text.lower()
    return any(
        phrase in lower_request
        for phrase in ["place an order", "need to order", "confirm the order", "large order", "medium order", "small order"]
    )


def get_unit_price(item_name: str) -> float:
    return float(ITEM_BY_NAME[item_name]["unit_price"])


def get_wholesale_cost(item_name: str, quantity: int) -> float:
    return round(get_unit_price(item_name) * quantity * 0.60, 2)


def calculate_discount(quantity: int, need_size: str) -> float:
    if quantity >= 5000 or need_size == "large":
        return 0.15
    if quantity >= 1000:
        return 0.12
    if quantity >= 500 or need_size == "medium":
        return 0.10
    if quantity >= 100:
        return 0.05
    return 0.0


def make_framework_agent(name: str, prompt: str, output_type: Any) -> Agent:
    """Create a pydantic-ai Agent while supporting both old and new result/output APIs."""
    system_prompt = f"""
{name}: {prompt}

You are part of a five-agent Munder Difflin multi-agent workflow.
Use your registered tools whenever your task depends on catalog, inventory,
pricing, quote history, transactions, balances, or quality checks.
Return only data matching the required structured output schema.
Do not reveal internal profit margin, wholesale cost, database details, API keys,
or stack traces in customer-facing text.
""".strip()
    try:
        return Agent(AGENT_MODEL, system_prompt=system_prompt, output_type=output_type)
    except TypeError:
        # Older pydantic-ai releases used result_type instead of output_type.
        return Agent(AGENT_MODEL, system_prompt=system_prompt, result_type=output_type)


class OrchestrationPlan(BaseModel):
    route: List[str]
    rationale: str


class FinalResponseResult(BaseModel):
    order_status: str
    response: str
    evaluation_passed: bool
    evaluation_findings: List[str] = Field(default_factory=list)


class IntakeResult(ParsedRequest):
    notes: str = ""


class InventoryResult(BaseModel):
    assessments: List[InventoryAssessment]
    notes: str = ""


class QuoteResult(QuoteProposal):
    notes: str = ""


class SalesResult(SalesDecision):
    cash_after: float
    inventory_after: float
    notes: str = ""


@dataclass
class AgentToolRecorder:
    agent_name: str
    tool_audit: List[ToolAudit] = field(default_factory=list)

    def record_tool(self, tool_name: str, detail: str) -> None:
        self.tool_audit.append(ToolAudit(self.agent_name, tool_name, detail))

    @staticmethod
    def _output(result: Any) -> Any:
        """Return pydantic-ai run output across API versions."""
        if hasattr(result, "output"):
            return result.output
        if hasattr(result, "data"):
            return result.data
        return result


class IntakeAgent(AgentToolRecorder):
    """Framework-executed agent that turns raw customer text into structured order intent."""

    def __init__(self) -> None:
        super().__init__("IntakeAgent")
        self.framework_agent = make_framework_agent(
            self.agent_name,
            "Extract delivery date, firm-order intent, quantities, and catalog-resolved item names from the customer request.",
            IntakeResult,
        )
        self._register_tools()

    def _register_tools(self) -> None:
        @self.framework_agent.tool
        def parse_delivery_date(ctx: RunContext, request_text: str, request_date: str) -> str:
            self.record_tool("parse_delivery_date", f"request_date={request_date}")
            return parse_requested_delivery_date(request_text, request_date)

        @self.framework_agent.tool
        def extract_line_items(ctx: RunContext, request_text: str) -> List[Dict[str, Any]]:
            self.record_tool("extract_line_items", "raw customer request parsed")
            return [item.model_dump() for item in extract_requested_line_items(request_text)]

        @self.framework_agent.tool
        def classify_firm_order(ctx: RunContext, request_text: str) -> bool:
            self.record_tool("classify_firm_order", "customer intent classified")
            return is_firm_order_request(request_text)

        @self.framework_agent.tool
        def resolve_catalog_item(ctx: RunContext, raw_item: str) -> Optional[str]:
            self.record_tool("resolve_catalog_item", f"raw_item={raw_item}")
            return resolve_item_name(clean_item_phrase(raw_item))

    def run_intake(self, request_text: str, request_date: str) -> IntakeResult:
        prompt = f"""
Customer request date: {request_date}
Customer request text:
{request_text}

Use the tools to parse delivery date, firm-order intent, and line items. Return an IntakeResult.
Each item must preserve the raw phrase and include the catalog item_name when a catalog match exists.
""".strip()
        return self._output(self.framework_agent.run_sync(prompt))


class InventoryAgent(AgentToolRecorder):
    """Framework-executed agent that checks stock and reorder feasibility."""

    def __init__(self) -> None:
        super().__init__("InventoryAgent")
        self.framework_agent = make_framework_agent(
            self.agent_name,
            "Check stock, reorder needs, and supplier delivery dates. Do not quote prices or record sales.",
            InventoryResult,
        )
        self._register_tools()

    def _register_tools(self) -> None:
        @self.framework_agent.tool
        def inventory_snapshot(ctx: RunContext, as_of_date: str) -> Dict[str, int]:
            self.record_tool("inventory_snapshot", f"as_of_date={as_of_date}")
            return get_all_inventory(as_of_date)

        @self.framework_agent.tool
        def item_stock_level(ctx: RunContext, item_name: str, as_of_date: str) -> Dict[str, Any]:
            self.record_tool("item_stock_level", f"item_name={item_name}, as_of_date={as_of_date}")
            stock_df = get_stock_level(item_name, as_of_date)
            return stock_df.to_dict(orient="records")[0] if not stock_df.empty else {"item_name": item_name, "current_stock": 0}

        @self.framework_agent.tool
        def supplier_delivery_eta(ctx: RunContext, request_date: str, quantity: int) -> str:
            self.record_tool("supplier_delivery_eta", f"request_date={request_date}, quantity={quantity}")
            return get_supplier_delivery_date(request_date, quantity)

    def run_inventory(self, parsed: IntakeResult) -> InventoryResult:
        prompt = f"""
Parsed request JSON:
{parsed.model_dump_json(indent=2)}

Use inventory_snapshot at least once for the request date. For each requested item:
- If item_name is null, mark can_fulfill false with reason "not carried in the current catalog".
- Otherwise use item_stock_level for the exact item and request date.
- If stock is short, use supplier_delivery_eta for the missing quantity.
- Mark reorder_needed true only when supplier ETA is on or before requested_delivery_date.
Return InventoryResult with one InventoryAssessment per requested item.
""".strip()
        return self._output(self.framework_agent.run_sync(prompt))


class QuotingAgent(AgentToolRecorder):
    """Framework-executed agent that generates quote lines and rationale."""

    def __init__(self) -> None:
        super().__init__("QuotingAgent")
        self.framework_agent = make_framework_agent(
            self.agent_name,
            "Generate explainable quotes using catalog prices, volume discounts, and historical quote context. Do not mutate inventory.",
            QuoteResult,
        )
        self._register_tools()

    def _register_tools(self) -> None:
        @self.framework_agent.tool
        def quote_history_search(ctx: RunContext, search_terms: List[str], limit: int = 5) -> List[Dict[str, Any]]:
            self.record_tool("quote_history_search", f"terms={search_terms}, limit={limit}")
            return search_quote_history(search_terms, limit)

        @self.framework_agent.tool
        def catalog_unit_price(ctx: RunContext, item_name: str) -> float:
            self.record_tool("catalog_unit_price", f"item_name={item_name}")
            return get_unit_price(item_name)

        @self.framework_agent.tool
        def volume_discount(ctx: RunContext, quantity: int, need_size: str) -> float:
            self.record_tool("volume_discount", f"quantity={quantity}, need_size={need_size}")
            return calculate_discount(quantity, need_size.lower())

    def run_quote(self, parsed: IntakeResult, inventory: InventoryResult, request_context: Dict[str, Any]) -> QuoteResult:
        prompt = f"""
Parsed request JSON:
{parsed.model_dump_json(indent=2)}

Inventory result JSON:
{inventory.model_dump_json(indent=2)}

Request context JSON:
{request_context}

Use quote_history_search once with job, event, and need_size terms when available.
For each inventory assessment that can be fulfilled and has an item_name:
- Use catalog_unit_price.
- Use volume_discount with the item quantity and need_size.
- Compute quoted_unit_price = list_unit_price * (1 - discount_rate).
- Compute line_total = quoted_unit_price * quantity.
- Use the requested delivery date unless an item has a reorder_delivery_date.
Return QuoteResult. Do not include unfulfillable items as quote lines.
""".strip()
        return self._output(self.framework_agent.run_sync(prompt))


class SalesAgent(AgentToolRecorder):
    """Framework-executed agent that records only fully fulfillable firm orders."""

    def __init__(self) -> None:
        super().__init__("SalesAgent")
        self.framework_agent = make_framework_agent(
            self.agent_name,
            "Finalize only fully fulfillable firm orders, record idempotent transactions, and report financial state.",
            SalesResult,
        )
        self._register_tools()

    def _transaction_exists(
        self,
        item_name: str,
        transaction_type: str,
        quantity: int,
        price: float,
        date: str,
    ) -> Optional[int]:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT rowid FROM transactions
                WHERE item_name IS ?
                  AND transaction_type = ?
                  AND units = ?
                  AND ABS(price - ?) < 0.0001
                  AND transaction_date = ?
                LIMIT 1
                """,
                (item_name, transaction_type, quantity, price, date),
            ).fetchone()
        return int(row[0]) if row else None

    def _register_tools(self) -> None:
        @self.framework_agent.tool
        def record_transaction_once(
            ctx: RunContext,
            item_name: str,
            transaction_type: str,
            quantity: int,
            price: float,
            date: str,
        ) -> int:
            self.record_tool("record_transaction_once", f"{transaction_type} {quantity} {item_name} at {price} on {date}")
            existing_id = self._transaction_exists(item_name, transaction_type, quantity, price, date)
            if existing_id is not None:
                return existing_id
            return create_transaction(item_name, transaction_type, quantity, price, date)

        @self.framework_agent.tool
        def wholesale_restock_cost(ctx: RunContext, item_name: str, quantity: int) -> float:
            self.record_tool("wholesale_restock_cost", f"item_name={item_name}, quantity={quantity}")
            return get_wholesale_cost(item_name, quantity)

        @self.framework_agent.tool
        def cash_balance(ctx: RunContext, as_of_date: str) -> float:
            self.record_tool("cash_balance", f"as_of_date={as_of_date}")
            return get_cash_balance(as_of_date)

        @self.framework_agent.tool
        def financial_report(ctx: RunContext, as_of_date: str) -> Dict[str, Any]:
            self.record_tool("financial_report", f"as_of_date={as_of_date}")
            return generate_financial_report(as_of_date)

    def run_sales(self, parsed: IntakeResult, inventory: InventoryResult, quote: QuoteResult) -> SalesResult:
        prompt = f"""
Parsed request JSON:
{parsed.model_dump_json(indent=2)}

Inventory result JSON:
{inventory.model_dump_json(indent=2)}

Quote result JSON:
{quote.model_dump_json(indent=2)}

Rules:
- If firm_order is false, do not record transactions. Return sale_recorded false.
- If any inventory assessment cannot be fulfilled, do not record transactions. Return sale_recorded false.
- If there are no quote lines, do not record transactions. Return sale_recorded false.
- For each reorder_needed assessment, call wholesale_restock_cost and then record_transaction_once for a stock_orders transaction.
- For each quote line, call record_transaction_once for a sales transaction using line_total.
- Always call cash_balance and financial_report for the request date before returning.
Return SalesResult with cash_after and inventory_after from the final financial report.
""".strip()
        return self._output(self.framework_agent.run_sync(prompt))


class OrchestratorAgent(AgentToolRecorder):
    """Framework-executed coordinator plus evaluator for the five-agent system."""

    def __init__(self) -> None:
        super().__init__("OrchestratorAgent")
        self.framework_agent = make_framework_agent(
            self.agent_name,
            "Coordinate Intake, Inventory, Quoting, and Sales agents, then synthesize and evaluate the final customer response.",
            OrchestrationPlan,
        )
        self.final_response_agent = make_framework_agent(
            f"{self.agent_name}FinalResponse",
            "Write a concise, transparent customer-facing response and evaluate it using the response_quality_check tool.",
            FinalResponseResult,
        )
        self.intake_agent = IntakeAgent()
        self.inventory_agent = InventoryAgent()
        self.quoting_agent = QuotingAgent()
        self.sales_agent = SalesAgent()
        self._register_tools()

    def _register_tools(self) -> None:
        @self.framework_agent.tool
        def workflow_plan(ctx: RunContext, request_summary: str) -> Dict[str, Any]:
            self.record_tool("workflow_plan", "route planning requested")
            return {
                "route": ["IntakeAgent", "InventoryAgent", "QuotingAgent", "SalesAgent", "OrchestratorAgent"],
                "rationale": "Parse request, assess fulfillment, quote fulfillable items, finalize firm orders, then evaluate response.",
                "request_summary": request_summary,
            }

        @self.final_response_agent.tool
        def response_quality_check(ctx: RunContext, response: str) -> Dict[str, Any]:
            self.record_tool("response_quality_check", "final customer response reviewed")
            blocked_terms = ["wholesale", "margin", "traceback", "sqlite", "sqlalchemy", "api key"]
            findings = [f"contains sensitive/internal term: {term}" for term in blocked_terms if term in response.lower()]
            if not response.strip():
                findings.append("response is empty")
            if not any(term in response.lower() for term in ["because", "discount", "not carried", "unavailable", "reorder"]):
                findings.append("response lacks a clear rationale")
            return {"passed": not findings, "findings": findings}

    def run_plan(self, row: pd.Series, request_date: str) -> OrchestrationPlan:
        prompt = f"""
Customer request date: {request_date}
Job: {row.get('job', '')}
Event: {row.get('event', '')}
Need size: {row.get('need_size', '')}
Request: {row.get('request', '')}

Call workflow_plan, then return an OrchestrationPlan that delegates to IntakeAgent, InventoryAgent, QuotingAgent,
SalesAgent, and OrchestratorAgent final evaluation in that order.
""".strip()
        return self._output(self.framework_agent.run_sync(prompt))

    def process_request(self, request_id: int, source_row: int, row: pd.Series) -> WorkflowResult:
        request_date = row["request_date"].strftime("%Y-%m-%d")
        cash_before = generate_financial_report(request_date)["cash_balance"]
        inventory_before = generate_financial_report(request_date)["inventory_value"]

        plan = self.run_plan(row, request_date)
        parsed = self.intake_agent.run_intake(str(row["request"]), request_date)
        inventory = self.inventory_agent.run_inventory(parsed)
        request_context = {
            "job": str(row.get("job", "")),
            "event": str(row.get("event", "")),
            "need_size": str(row.get("need_size", "")),
        }
        quote = self.quoting_agent.run_quote(parsed, inventory, request_context)
        sales = self.sales_agent.run_sales(parsed, inventory, quote)

        fulfilled_items = [line.item_name for line in quote.lines]
        unfulfilled_items = [assessment.raw_item for assessment in inventory.assessments if not assessment.can_fulfill]
        all_fulfillable = bool(inventory.assessments) and all(assessment.can_fulfill for assessment in inventory.assessments)

        final = self.run_final_response(parsed, inventory, quote, sales, all_fulfillable)
        report_after = generate_financial_report(request_date)

        return WorkflowResult(
            request_id=request_id,
            source_row=source_row,
            request_date=request_date,
            requested_delivery_date=parsed.requested_delivery_date,
            order_status=final.order_status,
            response=final.response,
            cash_before=cash_before,
            cash_after=report_after["cash_balance"],
            inventory_before=inventory_before,
            inventory_after=report_after["inventory_value"],
            fulfilled_items=fulfilled_items,
            unfulfilled_items=unfulfilled_items,
            agent_route=" -> ".join(plan.route),
            tool_calls=[audit.format() for audit in self.collect_tool_audit()],
            evaluation_passed=final.evaluation_passed,
            evaluation_findings=final.evaluation_findings,
        )

    def run_final_response(
        self,
        parsed: IntakeResult,
        inventory: InventoryResult,
        quote: QuoteResult,
        sales: SalesResult,
        all_fulfillable: bool,
    ) -> FinalResponseResult:
        deterministic_status = self.determine_order_status(parsed, quote, sales, all_fulfillable)
        factual_summary = self.build_factual_response_summary(parsed, inventory, quote, sales)
        prompt = f"""
Order status to use exactly: {deterministic_status}

Parsed request JSON:
{parsed.model_dump_json(indent=2)}

Inventory result JSON:
{inventory.model_dump_json(indent=2)}

Quote result JSON:
{quote.model_dump_json(indent=2)}

Sales result JSON:
{sales.model_dump_json(indent=2)}

Factual response summary drafted from validated agent outputs:
{factual_summary}

Write the final customer-facing response using only the facts above. Include relevant quantities, quote totals,
delivery feasibility, discounts, and why unfulfilled items cannot be fulfilled. Do not reveal wholesale costs,
profit margins, database internals, API details, or stack traces. Call response_quality_check on the response
before returning FinalResponseResult. The order_status field must exactly match the provided status.
""".strip()
        return self._output(self.final_response_agent.run_sync(prompt))

    @staticmethod
    def determine_order_status(parsed: IntakeResult, quote: QuoteResult, sales: SalesResult, all_fulfillable: bool) -> str:
        if sales.sale_recorded:
            return "fulfilled_sale_recorded"
        if all_fulfillable and quote.lines:
            return "quote_ready"
        if quote.lines:
            return "partial_quote_needs_review"
        return "unfulfilled"

    @staticmethod
    def build_factual_response_summary(
        parsed: IntakeResult,
        inventory: InventoryResult,
        quote: QuoteResult,
        sales: SalesResult,
    ) -> str:
        lines: List[str] = []
        quote_by_item = {line.item_name: line for line in quote.lines}
        for assessment in inventory.assessments:
            if not assessment.item_name:
                lines.append(f"- {assessment.raw_item}: not carried in the current catalog.")
                continue
            if not assessment.can_fulfill:
                lines.append(f"- {assessment.item_name}: unavailable because {assessment.reason}.")
                continue
            quote_line = quote_by_item.get(assessment.item_name)
            if not quote_line:
                continue
            reorder_note = ""
            if assessment.reorder_needed:
                reorder_note = (
                    f" Reorder is required for {assessment.missing_quantity} units; "
                    f"supplier ETA is {assessment.reorder_delivery_date}."
                )
            lines.append(
                f"- {quote_line.item_name}: {quote_line.quantity} units at ${quote_line.quoted_unit_price:.2f} each "
                f"after a {quote_line.discount_rate * 100:.0f}% discount = ${quote_line.line_total:.2f}. "
                f"Deliverable by {parsed.requested_delivery_date}.{reorder_note}"
            )
        if quote.lines:
            lines.append(f"Quote total: ${quote.total:.2f}. {quote.historical_context}")
        if sales.sale_recorded:
            lines.append("The firm order has been recorded and balances have been updated.")
        elif quote.lines and parsed.firm_order:
            lines.append(f"No sale was recorded because {sales.reason}.")
        elif quote.lines:
            lines.append("This is a quote only; the customer needs to confirm before a sale is recorded.")
        else:
            lines.append("No quote was generated because no requested item can be fulfilled by the requested delivery date.")
        return "\n".join(lines)

    def collect_tool_audit(self) -> List[ToolAudit]:
        audits = list(self.tool_audit)
        for worker in [self.intake_agent, self.inventory_agent, self.quoting_agent, self.sales_agent]:
            audits.extend(worker.tool_audit)
            worker.tool_audit.clear()
        self.tool_audit.clear()
        return audits


def build_agent_team() -> OrchestratorAgent:
    return OrchestratorAgent()


def run_test_scenarios(output_path: str = "test_results.csv", sleep_seconds: float = 0.0):
    print("Initializing Database...")
    init_database()
    try:
        quote_requests_sample = pd.read_csv(BASE_DIR / "quote_requests_sample.csv")
        quote_requests_sample["request_date"] = pd.to_datetime(
            quote_requests_sample["request_date"], format="%m/%d/%y", errors="coerce"
        )
        quote_requests_sample.dropna(subset=["request_date"], inplace=True)
        quote_requests_sample = quote_requests_sample.sort_values("request_date")
    except Exception as exc:
        print(f"FATAL: Error loading test data: {exc}")
        return []

    orchestrator = build_agent_team()
    print(f"Using {FRAMEWORK_NAME} framework-executed five-agent workflow.")
    initial_date = quote_requests_sample["request_date"].min().strftime("%Y-%m-%d")
    report = generate_financial_report(initial_date)
    current_cash = report["cash_balance"]
    current_inventory = report["inventory_value"]

    results: List[WorkflowResult] = []
    for request_number, (source_index, row) in enumerate(quote_requests_sample.iterrows(), start=1):
        request_date = row["request_date"].strftime("%Y-%m-%d")
        print(f"\n=== Request {request_number} ===")
        print(f"Source Row: {source_index + 1}")
        print(f"Context: {row['job']} organizing {row['event']}")
        print(f"Request Date: {request_date}")
        print(f"Cash Balance: ${current_cash:.2f}")
        print(f"Inventory Value: ${current_inventory:.2f}")
        result = orchestrator.process_request(request_number, source_index + 1, row)
        report = generate_financial_report(result.request_date)
        current_cash = report["cash_balance"]
        current_inventory = report["inventory_value"]
        print(f"Status: {result.order_status}")
        print(f"Response: {result.response}")
        print(f"Updated Cash: ${current_cash:.2f}")
        print(f"Updated Inventory: ${current_inventory:.2f}")
        results.append(result)
        if sleep_seconds:
            time.sleep(sleep_seconds)

    final_date = quote_requests_sample["request_date"].max().strftime("%Y-%m-%d")
    final_report = generate_financial_report(final_date)
    print("\n===== FINAL FINANCIAL REPORT =====")
    print(f"Final Cash: ${final_report['cash_balance']:.2f}")
    print(f"Final Inventory: ${final_report['inventory_value']:.2f}")
    write_results_csv(results, output_path)
    print_final_summary(results, output_path)
    return results


def write_results_csv(results: List[WorkflowResult], output_path: str) -> None:
    pd.DataFrame(
        [
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
                "agent_route": result.agent_route,
                "tool_calls": " | ".join(result.tool_calls),
                "evaluation_passed": result.evaluation_passed,
                "evaluation_findings": "; ".join(result.evaluation_findings),
                "response": result.response,
            }
            for result in results
        ]
    ).to_csv(output_path, index=False)


def print_final_summary(results: List[WorkflowResult], output_path: str) -> None:
    successful_sales = sum(result.order_status == "fulfilled_sale_recorded" for result in results)
    successful_quotes = sum(result.order_status in {"fulfilled_sale_recorded", "quote_ready"} for result in results)
    unfulfilled = sum(result.order_status == "unfulfilled" for result in results)
    cash_changes = sum(result.cash_changed for result in results)
    print("\n===== EVALUATION SUMMARY =====")
    print(f"Requests processed: {len(results)}")
    print(f"Successful sales recorded: {successful_sales}")
    print(f"Successful quote/sale outcomes: {successful_quotes}")
    print(f"Unfulfilled requests: {unfulfilled}")
    print(f"Requests with cash-balance changes: {cash_changes}")
    print(f"Results saved to {output_path}")


if __name__ == "__main__":
    run_test_scenarios()
