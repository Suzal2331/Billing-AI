from agents.sql_agent import generate_sql, NEEDS_VALUE_SENTINEL
from tools.sql_tool import execute_sql
from agents.report_agent import report_agent
from tools.response import card
from memory import (
    set_last_medicine,
    get_last_medicine
)


def inventory_agent(user_query):

    # =====================================
    # Remember Medicine Name
    # =====================================

    ignore_words = [
        "show",
        "stock",
        "medicine",
        "medicines",
        "inventory",
        "of",
        "the",
        "all",
        "do",
        "we",
        "have",
        "low",
        "sell",
        "available",
        "is",
        "there",
        "increase",
        "decrease",
        "update",
        "set",
        "by",
        "to"
    ]

    medicine_name = None

    for word in user_query.replace("?", "").split():

        clean = word.lower()

        if clean not in ignore_words and not clean.isdigit():
            medicine_name = word
            break

    if medicine_name:
        set_last_medicine(medicine_name)
    else:
        medicine_name = get_last_medicine()

    # =====================================
    # Generate SQL
    # =====================================

    sql = generate_sql(user_query)

    print("\n[Inventory Agent SQL]")
    print(sql)

    if sql == NEEDS_VALUE_SENTINEL:
        return card(
            "❓ You didn't say what the new value should be. "
            "Please repeat with the new value included — e.g. "
            "\"Set Crocin stock to 100\"."
        )

    # =====================================
    # SAFETY GUARD
    # =====================================
    # inventory_agent must only ever touch the medicine tables. If
    # a misclassified query lands here (e.g. the context agent's
    # LLM fallback guessing wrong on something like "add Raj"), the
    # SQL generator can hallucinate a query against patients/bills
    # instead — which previously inserted a garbage row straight
    # into the patients table, bypassing patient_agent's duplicate
    # checking entirely. Block that here, before execute_sql ever
    # runs, rather than trusting classification alone to prevent it.

    lower_sql = sql.lower()

    if "patients" in lower_sql or "bills" in lower_sql:
        text = f"""
============================================================
                  REQUEST NOT UNDERSTOOD
============================================================

❌ This didn't look like a medicine/inventory request, so
nothing was changed.

If you meant to manage a patient or bill, try rephrasing,
e.g. "Register patient {medicine_name or '<name>'}" or
"Generate bill for {medicine_name or '<name>'}".

============================================================
"""
        return card(text)

    # =====================================
    # Execute SQL
    # =====================================

    result = execute_sql(sql)

    # =====================================
    # Error
    # =====================================

    if "error" in result:
        return card(f"❌ {result['error']}")

    # =====================================
    # UPDATE
    # =====================================

    if result.get("type") == "UPDATE":

        if "increase" in user_query.lower():
            action_word = "increased"
        elif "decrease" in user_query.lower():
            action_word = "decreased"
        else:
            action_word = "updated"

        text = f"""
============================================================
                INVENTORY UPDATED
============================================================

✅ {medicine_name} stock {action_word} successfully.

Database Updated Successfully ✔

============================================================
"""
        return card(text)

    # =====================================
    # INSERT
    # =====================================

    if result.get("type") == "INSERT":

        text = f"""
============================================================
                 MEDICINE ADDED
============================================================

✅ {medicine_name} added successfully.

============================================================
"""
        return card(text)

    # =====================================
    # DELETE
    # =====================================

    if result.get("type") == "DELETE":

        text = f"""
============================================================
               MEDICINE REMOVED
============================================================

✅ {medicine_name} deleted successfully.

============================================================
"""
        return card(text)

    # =====================================
    # SELECT — delegate to report_agent, which now returns a
    # card dict itself (including the new "inventory" structured
    # card for medicine-list queries). Nothing more to do here.
    # =====================================

    return report_agent(
        "sql_report",
        {
            "query": user_query,
            "result": result
        }
    )