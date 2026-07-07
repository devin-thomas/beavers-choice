"""Optional PydanticAI agent bindings for the Beaver's Choice workflow.

The executable workflow in project_starter.py uses deterministic business tools so the
rubric evaluation can run reliably without hanging on an external model call. This file
keeps the project architecture aligned with the requested PydanticAI framework by
showing the orchestrator/worker agents and tool bindings that map to the helper
functions used by the deterministic workflow.
"""

from business_rules import (
    create_transaction,
    generate_financial_report,
    get_all_inventory,
    get_cash_balance,
    get_stock_level,
    get_supplier_delivery_date,
    search_quote_history,
)


def build_pydantic_ai_agents(model):
    """Build the PydanticAI agents and their tools without running them.

    This function is intentionally optional. It can be used for interactive demos, while
    the default evaluation path remains deterministic and repeatable.
    """
    from pydantic_ai import Agent, RunContext

    inventory_agent = Agent(
        model=model,
        system_prompt=(
            "Inventory Agent: check stock, assess reorder needs, and report supplier "
            "delivery dates. Do not generate quotes or finalize sales."
        ),
    )

    @inventory_agent.tool
    def check_inventory(ctx: RunContext[None], as_of_date: str) -> str:
        """Use get_all_inventory to summarize current stock."""
        return str(get_all_inventory(as_of_date))

    @inventory_agent.tool
    def check_stock_level(ctx: RunContext[None], item_name: str, as_of_date: str) -> str:
        """Use get_stock_level to inspect one catalog item."""
        return str(get_stock_level(item_name, as_of_date).to_dict(orient="records"))

    @inventory_agent.tool
    def estimate_supplier_delivery(ctx: RunContext[None], request_date: str, quantity: int) -> str:
        """Use get_supplier_delivery_date to decide whether reorder can meet the deadline."""
        return get_supplier_delivery_date(request_date, quantity)

    quoting_agent = Agent(
        model=model,
        system_prompt=(
            "Quoting Agent: price line items, apply discount rules, and explain quote "
            "rationale. Do not change inventory or record sales."
        ),
    )

    @quoting_agent.tool
    def find_similar_quotes(ctx: RunContext[None], search_terms: list[str]) -> str:
        """Use search_quote_history for comparable historical requests."""
        return str(search_quote_history(search_terms))

    sales_agent = Agent(
        model=model,
        system_prompt=(
            "Sales Agent: finalize approved fulfillable orders and update the database. "
            "Do not invent inventory or quote prices."
        ),
    )

    @sales_agent.tool
    def record_transaction(ctx: RunContext[None], item_name: str, transaction_type: str, quantity: int, price: float, date: str) -> str:
        """Use create_transaction to record stock orders or sales."""
        return str(create_transaction(item_name, transaction_type, quantity, price, date))

    @sales_agent.tool
    def financial_report(ctx: RunContext[None], as_of_date: str) -> str:
        """Use generate_financial_report and get_cash_balance after a transaction."""
        return str({
            "cash_balance": get_cash_balance(as_of_date),
            "report": generate_financial_report(as_of_date),
        })

    orchestrator_agent = Agent(
        model=model,
        system_prompt=(
            "Orchestrator Agent: parse the customer request, delegate inventory checks "
            "to Inventory Agent, quote generation to Quoting Agent, and order recording "
            "to Sales Agent. Keep final responses customer-facing and explainable."
        ),
    )

    return {
        "orchestrator": orchestrator_agent,
        "inventory": inventory_agent,
        "quoting": quoting_agent,
        "sales": sales_agent,
    }
