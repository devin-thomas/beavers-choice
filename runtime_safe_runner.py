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


db_engine = create_engine("sqlite:///munder_difflin.db")

# Full project catalog. Prices are per sheet/unit unless the item name says otherwise.
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


def init_database(engine: Engine, seed: int = 137) -> Engine:
    """Initialize transactions, quote history, and inventory tables."""
    pd.DataFrame({
        "id": [],
        "item_name": [],
        "transaction_type": [],
        "units": [],
        "price": [],
        "transaction_date": [],
    }).to_sql("transactions", engine, if_exists="replace", index=False)

    initial_date = datetime(2025, 1, 1).isoformat()

    quote_requests_df = pd.read_csv("quote_requests.csv")
    quote_requests_df["id"] = range(1, len(quote_requests_df) + 1)
    quote_requests_df.to_sql("quote_requests", engine, if_exists="replace", index=False)

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
    quotes_df.to_sql("quotes", engine, if_exists="replace", index=False)

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
    pd.DataFrame(transactions).to_sql("transactions", engine, if_exists="append", index=False)
    inventory_df.to_sql("inventory", engine, if_exists="replace", index=False)
    return engine


def create_transaction(item_name: str, transaction_type: str, quantity: int, total_price: float, date: Union[str, datetime]) -> int:
    """Record a stock order or sale. total_price must be the full transaction total."""
    if transaction_type not in {"stock_orders", "sales"}:
        raise ValueError("Transaction type must be 'stock_orders' or 'sales'")
    date_str = date.isoformat() if isinstance(date, datetime) else date
    pd.DataFrame([{
        "item_name": item_name,
        "transaction_type": transaction_type,
        "units": quantity,
        "price": total_price,
        "transaction_date": date_str,
    }]).to_sql("transactions", db_engine, if_exists="append", index=False)
    return int(pd.read_sql("SELECT last_insert_rowid() as id", db_engine).iloc[0]["id"])


def get_stock_level(item_name: str, as_of_date: Union[str, datetime]) -> pd.DataFrame:
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


def get_all_inventory(as_of_date: str) -> Dict[str, int]:
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


def get_supplier_delivery_date(input_date_str: str, quantity: int) -> str:
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


def strip_order_tail(request_text: str) -> str:
    """Remove delivery-only sentences so they do not get parsed as item names."""
    markers = [
        "I need these supplies delivered",
        "We need these supplies delivered",
        "I need these items delivered",
        "We need these items delivered",
        "Please ensure delivery",
        "Please deliver these supplies",
        "Please deliver the supplies",
        "Please deliver",
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
    """Normalize request text before extracting quantity/item pairs."""
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
    """Map customer wording to the closest catalog item without inventing unsupported sizes."""
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


def get_unit_price(item_name: str) -> float:
    return float(ITEM_LOOKUP[item_name.lower()]["unit_price"])


def calculate_discount(quantity: int) -> float:
    if quantity >= 1000:
        return 0.15
    if quantity >= 500:
        return 0.10
    if quantity >= 100:
        return 0.05
    return 0.0


def extract_requested_line_items(request_text: str) -> List[Dict[str, Union[str, int, None]]]:
    """Extract quantity/item pairs and preserve unmatched items for explicit reporting."""
    text_value = prepare_request_text(request_text)
    pattern = re.compile(
        r"(?P<qty>\d[\d,]*)\s+"
        r"(?:(?P<measure>sheets?|rolls?|roll|reams?|ream|packets?|packet|units?|unit)\s+(?:of\s+)?)?"
        r"(?P<item>[^,\.]+)",
        flags=re.IGNORECASE,
    )

    line_items: List[Dict[str, Union[str, int, None]]] = []
    for match in pattern.finditer(text_value):
        quantity = int(match.group("qty").replace(",", ""))
        measure = (match.group("measure") or "").strip()
        item = (match.group("item") or "").strip()
        raw_phrase = f"{measure} {item}".strip()
        cleaned_phrase = clean_item_phrase(raw_phrase)
        item_name = resolve_item_name(cleaned_phrase)
        line_items.append({
            "quantity": quantity,
            "raw_item": raw_phrase,
            "cleaned_item": cleaned_phrase,
            "item_name": item_name,
        })

    return line_items


def consolidate_line_items(line_items: List[Dict[str, Union[str, int, None]]]) -> List[Dict[str, Union[str, int, List[str], None]]]:
    """Merge duplicate resolved catalog items while keeping unknown items separate."""
    consolidated: Dict[str, Dict[str, Union[str, int, List[str], None]]] = {}
    output: List[Dict[str, Union[str, int, List[str], None]]] = []

    for item in line_items:
        item_name = item["item_name"]
        quantity = int(item["quantity"])
        raw_item = str(item["raw_item"])
        if item_name:
            key = str(item_name)
            if key not in consolidated:
                consolidated[key] = {"item_name": key, "quantity": 0, "raw_items": []}
                output.append(consolidated[key])
            consolidated[key]["quantity"] = int(consolidated[key]["quantity"]) + quantity
            consolidated[key]["raw_items"].append(raw_item)
        else:
            output.append({"item_name": None, "quantity": quantity, "raw_items": [raw_item]})

    return output


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


def generate_quote_response(line_items: List[Dict[str, Union[str, int, List[str], None]]], date: str, finalize_sale: bool = False) -> str:
    """Generate a customer-facing quote. Do not record partial sales for incomplete orders."""
    if not line_items:
        inventory = get_all_inventory(date)
        examples = ", ".join(list(inventory.keys())[:8])
        return f"Thanks for the request. I could not identify quantity/item pairs clearly enough to quote it. Available examples: {examples}."

    response_lines: List[str] = []
    available_lines: List[Dict[str, Union[str, int, float]]] = []
    has_issue = False

    for line_item in line_items:
        item_name = line_item["item_name"]
        quantity = int(line_item["quantity"])
        raw_label = ", ".join(line_item["raw_items"])

        if not item_name:
            has_issue = True
            response_lines.append(f"- {raw_label}: not carried in the current catalog.")
            continue

        stock = get_stock_quantity(str(item_name), date)
        unit_price = get_unit_price(str(item_name))
        discount = calculate_discount(quantity)
        final_unit_price = unit_price * (1 - discount)
        line_total = final_unit_price * quantity
        eta = get_supplier_delivery_date(date, quantity)

        if stock < quantity:
            has_issue = True
            response_lines.append(f"- {item_name}: requested {quantity}, but only {stock} are available as of {date}.")
            continue

        available_lines.append({
            "item_name": str(item_name),
            "quantity": quantity,
            "line_total": line_total,
        })
        response_lines.append(
            f"- {item_name}: {quantity} units at ${final_unit_price:.2f} each "
            f"({discount * 100:.0f}% discount) = ${line_total:.2f}; estimated delivery {eta}."
        )

    available_total = sum(float(line["line_total"]) for line in available_lines)

    if finalize_sale and not has_issue and available_lines:
        for line in available_lines:
            create_transaction(str(line["item_name"]), "sales", int(line["quantity"]), float(line["line_total"]), date)
        response_lines.append(f"Order total: ${available_total:.2f}")
        response_lines.append("The full order has been recorded.")
    elif finalize_sale and has_issue:
        if available_total > 0:
            response_lines.append(f"Available line-item subtotal: ${available_total:.2f}")
        response_lines.append("The full order cannot be fulfilled as requested, so no sale has been recorded.")
    elif available_total > 0:
        label = "Available line-item quote" if has_issue else "Estimated quote"
        response_lines.append(f"{label}: ${available_total:.2f}")
        if has_issue:
            response_lines.append("Please review the unavailable or non-carried items before confirming an order.")
        else:
            response_lines.append("Please confirm if you would like to place this order.")

    return "\n".join(response_lines)


def handle_request(request_text: str, request_date: str) -> str:
    raw_line_items = extract_requested_line_items(request_text)
    line_items = consolidate_line_items(raw_line_items)
    return generate_quote_response(
        line_items,
        request_date,
        finalize_sale=is_firm_order_request(request_text),
    )


def run_test_scenarios():
    print("Initializing Database...")
    init_database(db_engine)
    try:
        quote_requests_sample = pd.read_csv("quote_requests_sample.csv")
        quote_requests_sample["request_date"] = pd.to_datetime(quote_requests_sample["request_date"], format="%m/%d/%y", errors="coerce")
        quote_requests_sample.dropna(subset=["request_date"], inplace=True)
        quote_requests_sample = quote_requests_sample.sort_values("request_date")
    except Exception as e:
        print(f"FATAL: Error loading test data: {e}")
        return []

    print("Using runtime-safe deterministic request handler. This avoids the previous hanging run_sync call.")
    initial_date = quote_requests_sample["request_date"].min().strftime("%Y-%m-%d")
    report = generate_financial_report(initial_date)
    current_cash = report["cash_balance"]
    current_inventory = report["inventory_value"]

    results = []
    for request_number, (source_index, row) in enumerate(quote_requests_sample.iterrows(), start=1):
        request_date = row["request_date"].strftime("%Y-%m-%d")
        print(f"\n=== Request {request_number} ===")
        print(f"Source Row: {source_index + 1}")
        print(f"Context: {row['job']} organizing {row['event']}")
        print(f"Request Date: {request_date}")
        print(f"Cash Balance: ${current_cash:.2f}")
        print(f"Inventory Value: ${current_inventory:.2f}")

        response = handle_request(row["request"], request_date)
        report = generate_financial_report(request_date)
        current_cash = report["cash_balance"]
        current_inventory = report["inventory_value"]

        print(f"Response: {response}")
        print(f"Updated Cash: ${current_cash:.2f}")
        print(f"Updated Inventory: ${current_inventory:.2f}")
        results.append({
            "request_id": request_number,
            "source_row": source_index + 1,
            "request_date": request_date,
            "cash_balance": current_cash,
            "inventory_value": current_inventory,
            "response": response,
        })
        time.sleep(1)

    final_date = quote_requests_sample["request_date"].max().strftime("%Y-%m-%d")
    final_report = generate_financial_report(final_date)
    print("\n===== FINAL FINANCIAL REPORT =====")
    print(f"Final Cash: ${final_report['cash_balance']:.2f}")
    print(f"Final Inventory: ${final_report['inventory_value']:.2f}")
    pd.DataFrame(results).to_csv("test_results.csv", index=False)
    return results
