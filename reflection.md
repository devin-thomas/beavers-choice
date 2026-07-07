# Beaver's Choice Reflection

## Architecture overview

The Beaver's Choice system uses a multi-agent architecture with one Orchestrator Agent and four worker-style responsibilities: Intake, Inventory, Quoting, and Sales. The runnable project path is deterministic so the full evaluation can run without waiting on a remote model call, while `framework_agents.py` documents the corresponding PydanticAI agent/tool bindings.

The Orchestrator Agent manages the full request lifecycle. It receives a customer request, asks the Intake Agent to extract structured requested items and the delivery deadline, asks the Inventory Agent to check stock and reorder feasibility, asks the Quoting Agent to calculate customer-facing prices, and asks the Sales Agent to record transactions only when the order is a firm order and all requested catalog items can be fulfilled.

This design keeps responsibilities separated:

- Intake parses the customer request.
- Inventory checks stock and reorder feasibility.
- Quoting calculates prices and discounts.
- Sales records stock orders and sales transactions.
- The Orchestrator controls task sequence and final response formatting.

## Decision-making process

The most important design decision was to treat low stock as a reorder decision rather than an automatic failure. The original fallback system only checked current inventory, which caused most requests to fail because the seeded starting inventory intentionally covers only part of the catalog. The revised Inventory Agent checks whether missing items can be reordered in time using the supplier delivery helper.

If a missing catalog item can be reordered by the customer's delivery deadline, the order can still be fulfilled. If the item is not carried or the supplier delivery date would miss the requested date, the system explains why the request cannot be fulfilled.

## Evaluation approach

The project evaluates the full `quote_requests_sample.csv` dataset. For each request, the system records:

- the source row;
- the request date;
- the requested delivery date;
- the order status;
- cash before and after;
- inventory value before and after;
- fulfilled items;
- unfulfilled items; and
- the customer-facing response.

These fields are written to `test_results.csv` so the output can be reviewed against the rubric. The important rubric evidence is whether at least three requests change the cash balance, at least three requests are successfully fulfilled or quoted, and some requests remain unfulfilled with clear reasons.

## Strengths

The system is explainable. Customer-facing responses show line-item pricing, discount percentages, delivery feasibility, and reasons for unfulfilled items.

The system is safer than a pure LLM workflow because inventory math, discount math, delivery dates, and transaction updates are deterministic. This avoids hidden model mistakes in the parts of the project that affect the database.

The system uses the required helper functions through clear agent responsibilities. Inventory uses stock and delivery helpers, Quoting uses quote-history context, and Sales uses transaction and financial-report helpers.

## Limitations

The natural-language parser is still rule-based. It handles the provided sample dataset, but a production version would need stronger extraction and validation for unseen customer phrasing.

The reorder model is simple. It only checks whether a supplier delivery date can meet the requested date, and it does not model supplier capacity, multiple suppliers, backorders, or purchasing approval rules.

The default evaluation path does not call an LLM at runtime. This is intentional for reliability, but an interactive demo could use the optional PydanticAI bindings in `framework_agents.py` to generate richer language around the deterministic decisions.

## Future improvements

1. Add a customer-negotiation agent that proposes partial fulfillment or substitutions when the full order cannot be completed.
2. Add a business advisor agent that reviews sales, reorder transactions, and unfulfilled demand to recommend which products Beaver's Choice should stock more consistently.
3. Replace the rule-based parser with structured extraction using a Pydantic model, then validate the extraction before inventory and sales logic run.
4. Add unit tests for parsing, reorder feasibility, quote calculation, and transaction recording.
