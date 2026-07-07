# Beaver's Choice PydanticAI Multi-Agent Workflow

The submitted workflow uses the selected `pydantic-ai` framework in the runnable `project_starter_update.py` path. The architecture stays within the five-agent project limit by using `OrchestratorAgent`, `IntakeAgent`, `InventoryAgent`, `QuotingAgent`, and `SalesAgent`. Evaluation is handled by an Orchestrator-owned tool rather than by a sixth agent.

```mermaid
flowchart TD
    A[Customer quote/order request] --> B[OrchestratorAgent]
    B --> B1[Tool: workflow_plan]
    B1 --> S[Shared typed workflow state]

    S --> I[IntakeAgent]
    I --> I1[Tool: parse_delivery_date -> parse_requested_delivery_date]
    I --> I2[Tool: extract_line_items -> extract_requested_line_items]
    I --> I3[Tool: classify_firm_order -> is_firm_order_request]
    I --> I4[Tool: resolve_catalog_item -> resolve_item_name]
    I --> I5[IntakeResult]

    I5 --> C[InventoryAgent]
    C --> C1[Tool: inventory_snapshot -> get_all_inventory]
    C --> C2[Tool: item_stock_level -> get_stock_level]
    C --> C3[Tool: supplier_delivery_eta -> get_supplier_delivery_date]
    C --> C4[InventoryResult with InventoryAssessment records]

    C4 --> D[QuotingAgent]
    D --> D1[Tool: quote_history_search -> search_quote_history]
    D --> D2[Tool: catalog_unit_price -> catalog price lookup]
    D --> D3[Tool: volume_discount -> calculate_discount]
    D --> D4[QuoteResult with line prices, discounts, and delivery rationale]

    D4 --> E[SalesAgent]
    E --> E1[Tool: record_transaction_once -> create_transaction]
    E --> E2[Tool: wholesale_restock_cost -> get_wholesale_cost]
    E --> E3[Tool: cash_balance -> get_cash_balance]
    E --> E4[Tool: financial_report -> generate_financial_report]
    E --> E5[SalesResult]

    E5 --> F[OrchestratorAgent final response]
    F --> F1[Tool: response_quality_check]
    F1 --> G[Customer-safe response]
    G --> H[test_results.csv with route, tools, status, cash delta, fulfilled items, unfulfilled reasons, response]
```

## Agent Responsibilities

### OrchestratorAgent

The OrchestratorAgent owns the request lifecycle and framework-level coordination. It creates a workflow plan, delegates to the worker agents, synthesizes the final customer response, and uses its `response_quality_check` tool as the final evaluation gate. It does not perform inventory math, quote math, or direct transaction mutation.

### IntakeAgent

The IntakeAgent owns structured request extraction. Its tools parse requested delivery date, extract requested line items, classify whether the request is a firm order, and resolve raw item phrases to catalog item names.

### InventoryAgent

The InventoryAgent owns stock and delivery feasibility. It is read-only except for its structured `InventoryResult`. Its tools are `inventory_snapshot`, `item_stock_level`, and `supplier_delivery_eta`, which call the starter helpers `get_all_inventory`, `get_stock_level`, and `get_supplier_delivery_date`.

### QuotingAgent

The QuotingAgent owns price construction and historical quote context. Its tools call `search_quote_history`, catalog unit-price lookup, and the discount calculator. It does not update inventory or record sales.

### SalesAgent

The SalesAgent is the only worker allowed to mutate business state. It records restock and sale transactions only when the order is firm and fully fulfillable. Its tools call `create_transaction`, `get_cash_balance`, and `generate_financial_report`, with `record_transaction_once` used to reduce duplicate transaction risk.

## Data Flow

1. The OrchestratorAgent receives a customer request and creates a route plan.
2. The IntakeAgent converts raw text into typed request state.
3. The InventoryAgent checks current stock and supplier delivery timing.
4. The QuotingAgent prices fulfillable items and applies quantity discounts.
5. The SalesAgent records transactions only for firm, fully fulfillable orders.
6. The OrchestratorAgent writes and evaluates the customer-facing response.
7. The workflow writes `test_results.csv` with the agent route, tool-call audit, order status, cash deltas, fulfilled items, unfulfilled reasons, evaluation result, and response.
