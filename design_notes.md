# Design Notes: Beaver's Choice Paper Company

## Agent Workflow Explanation

The system is designed with four agents using the **pydantic-ai** framework to automate sales, inventory management, and quoting processes. The architecture employs a hierarchical structure where an `Orchestrator Agent` delegates tasks to three specialized worker agents based on the customer request:

1.  **Orchestrator Agent**: Acts as the main interface. It parses customer queries, extracts relevant context (like the date of request), and delegates the work to the most appropriate specialized agent.
2.  **Inventory Agent**: Handles queries related to stock availability and low stock conditions. It is equipped with tools to check overall inventory, check single item stock, and place restock orders (transactions of type 'purchase').
3.  **Quoting Agent**: Responsible for calculating quotes and analyzing historical pricing. It retrieves stock availability to ensure quotes can be fulfilled and automatically applies tiered bulk discounts based on the requested volume.
4.  **Sales Agent**: Finalizes customer orders. It verifies stock levels and records the 'sales' transaction in the system, subsequently providing delivery ETAs to the customer.

## Evaluation Results

- The `test_results.csv` was successfully generated covering all 71 simulated scenarios.
- The `cash_balance` dynamically changed as the sales and purchase transactions were recorded.
- Stock shortfalls were correctly detected and customers were appropriately informed when insufficient stock prevented an order fulfillment.
- Bulk discounts were systematically applied to accurate line-item quotes based on the defined schedule.

## Suggested Improvements

To further enhance the company's multi-agent system, I recommend the following additions:
1.  **Customer Negotiation Agent**: Currently, the Quoting Agent offers a fixed discount based on volume. A Negotiation Agent could be implemented to handle counter-offers or adjust quotes dynamically based on a customer's lifetime value, urgency, or competitive matching, all while protecting a minimum profit margin.
2.  **Business Intelligence / Forecasting Agent**: Rather than waiting for stock to run low and reacting to it, a Forecasting Agent could analyze seasonal trends and historic quote volumes to preemptively trigger purchase orders, ensuring the company never misses out on a large sale due to inadequate stock.
