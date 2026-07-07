import time
from collections import Counter
from typing import List

import pandas as pd

from business_rules import (
    OrchestratorAgent,
    db_engine,
    generate_financial_report,
    init_database,
)
from models import InventoryDecision, OrderResult, QuoteLine


class ConciseOrchestratorAgent(OrchestratorAgent):
    """Orchestrator with shorter terminal/customer-facing responses for evaluation runs."""

    def _format_response(
        self,
        decisions: List[InventoryDecision],
        quote_lines: List[QuoteLine],
        firm_order: bool,
        sale_recorded: bool,
        requested_delivery_date: str,
    ) -> str:
        quote_total = sum(line.line_total for line in quote_lines)
        reorder_count = sum(1 for decision in decisions if decision.reorder_needed)
        unfulfilled = [decision for decision in decisions if not decision.can_fulfill]

        lines: List[str] = []
        if quote_lines:
            item_summary = self._summarize_quote_items(quote_lines)
            lines.append(
                f"Quoted {len(quote_lines)} item(s): {item_summary}. "
                f"Total: ${quote_total:.2f}; delivery target {requested_delivery_date}."
            )
            if reorder_count:
                lines.append(
                    f"Reorder needed for {reorder_count} quoted item(s); supplier ETA is within the requested delivery window."
                )

        if unfulfilled:
            lines.append(
                f"Cannot fulfill {len(unfulfilled)} item(s): {self._summarize_unfulfilled_items(unfulfilled)}."
            )

        if sale_recorded:
            lines.append("Sale recorded and inventory/cash balances updated.")
        elif quote_lines and firm_order:
            lines.append("Partial quote only; no sale recorded because the full firm order cannot be fulfilled as requested.")
        elif quote_lines:
            lines.append("Quote ready; awaiting customer confirmation before recording a sale.")
        else:
            lines.append("No quote generated because no requested catalog items can meet the delivery requirements.")

        return "\n".join(lines)

    @staticmethod
    def _summarize_quote_items(quote_lines: List[QuoteLine], limit: int = 4) -> str:
        parts = [f"{line.item_name} x{line.quantity}" for line in quote_lines[:limit]]
        if len(quote_lines) > limit:
            parts.append(f"and {len(quote_lines) - limit} more")
        return ", ".join(parts)

    @staticmethod
    def _summarize_unfulfilled_items(decisions: List[InventoryDecision], limit: int = 3) -> str:
        parts = []
        for decision in decisions[:limit]:
            label = decision.item_name or decision.raw_item
            if decision.item_name:
                parts.append(f"{label} ({decision.reason})")
            else:
                parts.append(f"{label} (not carried)")
        if len(decisions) > limit:
            parts.append(f"and {len(decisions) - limit} more")
        return "; ".join(parts)


def run_test_scenarios():
    """Run the full sample dataset and print a concise rubric-friendly summary."""
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

    print("Using concise deterministic multi-agent evaluation workflow.")
    orchestrator = ConciseOrchestratorAgent()
    initial_date = quote_requests_sample["request_date"].min().strftime("%Y-%m-%d")
    current_report = generate_financial_report(initial_date)

    results: List[OrderResult] = []
    for request_number, (source_index, row) in enumerate(quote_requests_sample.iterrows(), start=1):
        request_date = row["request_date"].strftime("%Y-%m-%d")
        print(f"\n=== Request {request_number} ===")
        print(f"Source Row: {source_index + 1} | {row['job']} / {row['event']} | Date: {request_date}")
        print(f"Before: Cash ${current_report['cash_balance']:.2f} | Inventory ${current_report['inventory_value']:.2f}")

        result = orchestrator.process_request(request_number, source_index + 1, row)
        current_report = generate_financial_report(result.request_date)

        print(f"Status: {result.order_status}")
        print(f"Response: {result.response}")
        print(f"After: Cash ${result.cash_after:.2f} | Inventory ${result.inventory_after:.2f}")
        results.append(result)
        time.sleep(1)

    write_results_csv(results)
    print_final_summary(results)
    return results


def write_results_csv(results: List[OrderResult]) -> None:
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


def print_final_summary(results: List[OrderResult]) -> None:
    status_counts = Counter(result.order_status for result in results)
    successful_sales = status_counts.get("fulfilled_sale_recorded", 0)
    quote_ready = status_counts.get("quote_ready", 0)
    partial_quotes = status_counts.get("partial_quote_needs_review", 0)
    unfulfilled = status_counts.get("unfulfilled", 0)
    cash_changes = sum(1 for result in results if result.cash_changed)
    successful_quotes = successful_sales + quote_ready

    final_cash = results[-1].cash_after if results else 0.0
    final_inventory = results[-1].inventory_after if results else 0.0

    print("\n===== EVALUATION SUMMARY =====")
    print(f"Total requests processed: {len(results)}")
    print(f"Successful sales recorded: {successful_sales}")
    print(f"Quote-ready requests: {quote_ready}")
    print(f"Successful quote/sale outcomes: {successful_quotes}")
    print(f"Partial quotes needing review: {partial_quotes}")
    print(f"Unfulfilled requests: {unfulfilled}")
    print(f"Requests with cash-balance changes: {cash_changes}")
    print(f"Final Cash: ${final_cash:.2f}")
    print(f"Final Inventory: ${final_inventory:.2f}")
    print("Results saved to test_results.csv")
