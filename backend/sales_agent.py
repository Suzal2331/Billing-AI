print("######## SALES AGENT LOADED — PATIENT-LINK-V1 ########")

from tools.db_tool import sell_medicine
from tools.sql_tool import execute_sql
from tools.response import card


def _sql_escape(value):
    """Minimal single-quote escaping for building a raw SQL string.
    Only used for the patient-name backfill below, where the value
    comes from either the LLM extraction or conversation memory —
    never raw, unvalidated user SQL."""
    return str(value).replace("'", "''")


def sales_agent(data):

    result = sell_medicine(
        data["medicine_name"],
        data["quantity"]
    )

    # =====================================
    # ERROR
    # =====================================

    if not result["success"]:

        text = f"""
============================================================
                    SALE FAILED
============================================================

❌ {result["message"]}

============================================================
"""
        return card(text)

    # =====================================
    # LINK THIS SALE TO A PATIENT
    # =====================================
    # sell_medicine() only knows about the medicine — it has no
    # concept of which patient the sale is for, and changing its
    # signature isn't something to do blind without seeing
    # db_tool.py. Instead, backfill patient_name on the row that
    # was just inserted via a direct UPDATE. This is what makes
    # "what medicines has X taken" queries answerable going
    # forward (medicine_sales needs the patient_name column added
    # first — see migrate_medicine_sales.py).
    #
    # This is best-effort: if it fails for any reason, the sale
    # itself has already succeeded and should not be rolled back
    # over a missing patient link.

    patient_name = data.get("patient_name")

    print(f"[Sales Agent] patient_name from data: {patient_name!r}")

    if patient_name:
        try:
            execute_sql(
                "UPDATE medicine_sales "
                f"SET patient_name = '{_sql_escape(patient_name)}' "
                "WHERE sale_id = (SELECT MAX(sale_id) FROM medicine_sales)"
            )
            print(f"[Sales Agent] Linked latest sale to patient: {patient_name}")
        except Exception as e:
            print(f"[Sales Agent] Failed to link patient — {e}")

    # =====================================
    # SUCCESS
    # =====================================

    patient_line = f"\n👤 Patient         : {patient_name}\n" if patient_name else ""

    text = f"""
============================================================
                MEDICINE SALE RECEIPT
============================================================

💊 Medicine        : {result["medicine"]}

📦 Quantity Sold   : {result["quantity"]}

💰 Amount          : ₹{result["amount"]:.2f}

📉 Remaining Stock : {result["remaining_stock"]}
{patient_line}
------------------------------------------------------------

✅ Sale Recorded Successfully

Thank you.

============================================================
"""

    structured = {
        "kind": "sale",
        "title": "Medicine Sale Receipt",
        "sale": {
            "medicine": result["medicine"],
            "qty": result["quantity"],
            "total": f"₹{result['amount']:.2f}",
            "remainingStock": result["remaining_stock"],
        },
    }

    return card(text, structured)