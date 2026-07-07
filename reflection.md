# Beaver's Choice Reflection

## Architecture Overview

The rebuilt Beaver's Choice solution uses a real `pydantic-ai` multi-agent architecture in the runnable `project_starter_update.py` submission path. The system stays within the rubric's five-agent maximum by using five agents: `OrchestratorAgent`, `IntakeAgent`, `InventoryAgent`, `QuotingAgent`, and `SalesAgent`.

The `OrchestratorAgent` owns coordination and final response evaluation. It receives each customer request, creates a framework-executed workflow plan, delegates request extraction to the `IntakeAgent`, delegates stock and delivery feasibility to the `InventoryAgent`, delegates customer-facing pricing to the `QuotingAgent`, delegates firm-order transaction control to the `SalesAgent`, and then uses its own `response_quality_check` tool as the final customer-safety gate. Evaluation is intentionally handled by the Orchestrator rather than a sixth agent so the implementation and diagram stay within the project limit.

Each worker has non-overlapping responsibilities:

- `IntakeAgent` extracts delivery date, firm-order intent, requested quantities, raw item phrases, and resolved catalog item names.
- `InventoryAgent` checks current stock, missing quantities, supplier delivery dates, and whether reorders can meet the requested delivery date.
- `QuotingAgent` reviews historical quote context and creates customer-facing prices, discounts, quote totals, and delivery rationale.
- `SalesAgent` records only valid firm-order transactions and reports updated cash and inventory state.
- `OrchestratorAgent` coordinates the workflow, creates the final response, and evaluates that response for completeness, rationale, and customer safety.

## Framework and Tool Use

The project uses `pydantic-ai` as the selected orchestration framework. Each agent is instantiated as an `Agent`, each worker exposes framework tools registered with `@agent.tool`, and each specialist is executed through `run_sync()` instead of being used only as a tool registry. The workflow also writes an agent route and tool-call audit into `test_results.csv`, making delegation visible during evaluation.

The required starter helper functions are used through agent tools:

- `get_all_inventory` is used by `InventoryAgent.inventory_snapshot`.
- `get_stock_level` is used by `InventoryAgent.item_stock_level`.
- `get_supplier_delivery_date` is used by `InventoryAgent.supplier_delivery_eta`.
- `search_quote_history` is used by `QuotingAgent.quote_history_search`.
- `create_transaction` is used by `SalesAgent.record_transaction_once`.
- `get_cash_balance` is used by `SalesAgent.cash_balance`.
- `generate_financial_report` is used by `SalesAgent.financial_report`.

The `OrchestratorAgent.response_quality_check` tool is not a sixth agent. It is a final evaluation tool used by the Orchestrator to block internal implementation details, secrets, stack traces, and sensitive business terms from customer-facing output.

## Decision-Making Process

The most important architecture decision was to let agents make domain decisions while keeping arithmetic, catalog lookup, and database mutation inside deterministic tools. This gives the system real framework-based multi-agent execution while preserving reliable stock math, pricing math, supplier ETA calculation, and transaction updates.

The workflow treats missing inventory as a reorder decision rather than an automatic failure. If supplier delivery can meet the requested delivery date, the item remains fulfillable and the customer receives a reorder note. If an item is not carried or supplier delivery would miss the requested date, the customer receives an explicit reason.

Sales are recorded only when the customer request is a firm order and every requested catalog item can be fulfilled. The SalesAgent uses an idempotent transaction tool so repeated execution is less likely to duplicate sales or restock rows.

## Evaluation Results

The full `quote_requests_sample.csv` dataset is evaluated and written to `test_results.csv`. The results include request source row, request date, requested delivery date, order status, cash before and after, inventory value before and after, fulfilled items, unfulfilled items, agent route, tool calls, evaluation pass/fail, and the final customer response.

The included evaluation output shows:

- 20 requests processed.
- 5 requests with cash-balance changes.
- 10 successful quote or sale outcomes.
- 3 unfulfilled requests with reasons.
- All final responses passed the Orchestrator customer-safety evaluation gate.

These results satisfy the rubric requirements that at least three requests change cash balance, at least three quote requests are fulfilled or quote-ready, and not all requests are fulfilled.

## Strengths

The implementation is explainable. Customer responses include item-level pricing, discount percentages, delivery feasibility, reorder notes, quote totals, and reasons when an item cannot be fulfilled.

The system is modular while still matching the five-agent limit. Intake, inventory, quoting, sales, and orchestration/evaluation have clear ownership, and the workflow diagram matches the code.

The system is safer than letting a model freely edit database state. Agents coordinate decisions, but tools enforce stock math, delivery-date calculations, transaction creation, and financial reporting.

## Limitations

The parser is now handled by an IntakeAgent, but its tools still use deterministic extraction rules. This is reliable for the sample data, but a production system should add confidence scoring and clarification handling for ambiguous item names.

The supplier model is simplified. It estimates delivery by quantity only and does not model supplier capacity, multiple vendors, holiday calendars, or procurement approvals.

Historical quote context is currently used as supporting context rather than a full pricing model. A future version could build a richer quote-history retrieval and scoring strategy.

## Future Improvements

1. Add a customer-negotiation workflow that proposes substitutions, partial fulfillment, or adjusted delivery dates when the full request cannot be satisfied.
2. Add a business-advisor mode inside the Orchestrator that reviews transactions and unfulfilled demand to recommend catalog and inventory strategy.
3. Add confidence scoring to the IntakeAgent so uncertain item names trigger clarification instead of silent matching.
4. Expand evaluation to include trajectory scoring: expected tools used, tool argument validity, response quality, and financial-state consistency.
