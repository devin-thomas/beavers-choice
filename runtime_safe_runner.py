import ast
import re
import time
from datetime import datetime, timedelta
from difflib import get_close_matches
from typing import Dict, List, Union

import numpy as np
import pandas as pd
from sqlalchemy import Engine, create_engine
from sqlalchemy.sql import text


db_engine = create_engine("sqlite:///munder_difflin.db")

paper_supplies = [
    {"item_name": "A4 paper", "category": "paper", "unit_price": 0.05},
    {"item_name": "Letter-sized paper", "category": "paper", "unit_price": 0.06},
    {"item_name": "Cardstock", "category": "paper", "unit_price": 0.15},
    {"item_name": "Colored paper", "category": "paper", "unit_price": 0.10},
    {"item_name": "Glossy paper", "category": "paper", "unit_price": 0.20},
    {"item_name": "Poster paper", "category": "paper", "unit_price": 0.25},
    {"item_name": "Heavyweight paper", "category": "paper", "unit_price": 0.20},
    {"item_name": "Standard copy paper", "category": "paper", "unit_price": 0.04},
    {"item_name": "Party streamers", "category": "product", "unit_price": 0.05},
    {"item_name": "Large poster paper (24x36 inches)", "category": "large_format", "unit_price": 1.00},
]

ITEM_LOOKUP = {item["item_name"].lower(): item for item in paper_supplies}
ALIASES = {
    "a4 glossy paper": "Glossy paper",
    "glossy paper": "Glossy paper",
    "heavy cardstock": "Cardstock",
    "heavy cardstock white": "Cardstock",
    "cardstock": "Cardstock",
    "colored paper": "Colored paper",
    "colorful poster paper": "Poster paper",
    "poster paper": "Poster paper",
    "streamers": "Party streamers",
    "roll of streamers": "Party streamers",
    "rolls of streamers": "Party streamers",
    "printer paper": "Standard copy paper",
    "copy paper": "Standard copy paper",
    "a4 paper": "A4 paper",
    "a3 paper": "A4 paper",
}


def generate_sample_inventory(supplies: list, seed: int = 137) -> pd.DataFrame:
    """Generate deterministic starting inventory for the runtime-safe runner."""
    np.random.seed(seed)
    rows = []
    for item in supplies:
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
    for _, item in inventory_df.iterrows():
        stock = get_stock_level(item["item_name"], as_of_date)["current_stock"].iloc[0]
        inventory_value += stock * item["unit_price"]
    return {"as_of_date": as_of_date, "cash_balance": cash, "inventory_value": inventory_value, "total_assets": cash + inventory_value}


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


def resolve_item_name(raw_name: str) -> str | None:
    cleaned = normalize_text(raw_name)
    if cleaned in ALIASES:
        return ALIASES[cleaned]
    for alias, canonical in ALIASES.items():
        if alias in cleaned or cleaned in alias:
            return canonical
    matches = get_close_matches(raw_name, [item["item_name"] for item in paper_supplies], n=1, cutoff=0.55)
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


def extract_requested_items(request_text: str) -> Dict[str, int]:
    text_value = request_text.replace("\n", " ")
    matches = re.findall(
        r"(\d[\d,]*)\s+(?:sheets? of |sheet of |rolls? of |roll of |reams? of |ream of |units? of )?([A-Za-z0-9\-\(\) ]+?)(?=,| and | for |\. |$)",
        text_value,
        flags=re.IGNORECASE,
    )
    requested_items: Dict[str, int] = {}
    for quantity_text, raw_item in matches:
        quantity = int(quantity_text.replace(",", ""))
        cleaned_item = raw_item.strip().lower()
        cleaned_item = re.sub(r"\b(white|assorted colors|assorted|color|colors|the|a|an)\b", "", cleaned_item).strip()
        cleaned_item = re.sub(r"\s+", " ", cleaned_item)
        item_name = resolve_item_name(cleaned_item)
        if item_name:
            requested_items[item_name] = requested_items.get(item_name, 0) + quantity
    return requested_items


def generate_quote_response(items: Dict[str, int], date: str, finalize_sale: bool = False) -> str:
    if not items:
        inventory = get_all_inventory(date)
        return "Thanks for the request. I could not confidently match the request to our catalog. Available examples: " + ", ".join(list(inventory.keys())[:8])

    response_lines = []
    total_quote = 0.0
    for item_name, quantity in items.items():
        stock = int(get_stock_level(item_name, date)["current_stock"].iloc[0])
        unit_price = get_unit_price(item_name)
        discount = calculate_discount(quantity)
        final_unit_price = unit_price * (1 - discount)
        line_total = final_unit_price * quantity
        eta = get_supplier_delivery_date(date, quantity)
        if stock < quantity:
            response_lines.append(f"- {item_name}: requested {quantity}, but only {stock} are available as of {date}.")
            continue
        total_quote += line_total
        response_lines.append(f"- {item_name}: {quantity} units at ${final_unit_price:.2f} each ({discount * 100:.0f}% discount) = ${line_total:.2f}; estimated delivery {eta}.")
        if finalize_sale:
            create_transaction(item_name, "sales", quantity, line_total, date)
    if total_quote > 0:
        response_lines.append(f"{'Order total' if finalize_sale else 'Estimated quote'}: ${total_quote:.2f}")
        response_lines.append("The sale has been recorded." if finalize_sale else "Please confirm if you would like to place this order.")
    return "\n".join(response_lines)


def handle_request(request_text: str, request_date: str) -> str:
    items = extract_requested_items(request_text)
    lower_request = request_text.lower()
    is_firm_order = any(phrase in lower_request for phrase in ["place an order", "need to order", "confirm the order"])
    return generate_quote_response(items, request_date, finalize_sale=is_firm_order)


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
    for idx, row in quote_requests_sample.iterrows():
        request_date = row["request_date"].strftime("%Y-%m-%d")
        print(f"\n=== Request {idx + 1} ===")
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
        results.append({"request_id": idx + 1, "request_date": request_date, "cash_balance": current_cash, "inventory_value": current_inventory, "response": response})
        time.sleep(1)

    final_date = quote_requests_sample["request_date"].max().strftime("%Y-%m-%d")
    final_report = generate_financial_report(final_date)
    print("\n===== FINAL FINANCIAL REPORT =====")
    print(f"Final Cash: ${final_report['cash_balance']:.2f}")
    print(f"Final Inventory: ${final_report['inventory_value']:.2f}")
    pd.DataFrame(results).to_csv("test_results.csv", index=False)
    return results
