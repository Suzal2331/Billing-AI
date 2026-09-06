print("######## REPORT AGENT LOADED — STRUCTURED-CARDS-V1 ########")

from datetime import datetime

from tools.db_tool import get_bill
from tools.response import card


def _patient_row_from_columns(columns, row):
    """
    Builds a frontend PatientRow from a raw SQL row that has (at
    least) id/name/age/gender/doctor columns. Same placeholder
    fields as patient_agent._patient_row() for phone/status/
    lastVisit, since this schema doesn't track them.
    """
    idx = {name: i for i, name in enumerate(columns)}

    return {
        "id": row[idx["id"]],
        "name": row[idx["name"]],
        "age": row[idx["age"]],
        "gender": row[idx["gender"]],
        "phone": "N/A",
        "doctor": row[idx["doctor"]],
        "status": "Active",
        "lastVisit": datetime.now().strftime("%Y-%m-%d"),
    }


def _bill_card_from_row(bill_row):
    """
    Builds a structured 'bill_generated' card from a raw bills-table
    row: (bill_id, patient_name, consultation, medicine, lab, gst,
    total, created_at).

    Unlike billing_agent.py (which knows the exact doctor_fee at
    creation time), a bill fetched back out of the DB has no way to
    know how much of `total` was doctor_fee — the bills table only
    stores consultation/medicine/lab/gst/total, not doctor_fee as
    its own column. Subtotal here is backed out as (total - gst)
    rather than summed from parts, and doctor_fee isn't shown as a
    separate item, so items may not add up to `total` for older
    bills. Good enough for display; not exact accounting.
    """
    bill_id, patient_name, consultation, medicine, lab, gst, total, created_at = bill_row

    subtotal = round(total - gst, 2)

    return {
        "kind": "bill_generated",
        "title": "Bill",
        "bill": {
            "patient": patient_name,
            "billNo": str(bill_id),
            "date": created_at,
            "items": [
                {"name": "Consultation", "qty": 1, "price": consultation},
                {"name": "Medicine", "qty": 1, "price": medicine},
                {"name": "Lab Charges", "qty": 1, "price": lab},
            ],
            "subtotal": subtotal,
            "gst": gst,
            "total": total,
            "paymentStatus": "Paid",
        },
    }


def report_agent(action, data):

    # ==================================================
    # MEDICAL BILL RECEIPT
    # ==================================================

    if action == "get_bill":

        patient_name = data["patient_name"]

        bill = get_bill(patient_name)

        if bill is None:
            return card("""
============================================================
                    BILL NOT FOUND
============================================================

❌ No bill found for this patient.

============================================================
""")

        text = f"""
============================================================
                 MEDICAL BILL RECEIPT
============================================================

🧾 Bill ID        : {bill[0]}

👤 Patient Name   : {bill[1]}

------------------------------------------------------------

👨‍⚕ Consultation : ₹{bill[2]:,.2f}

💊 Medicine      : ₹{bill[3]:,.2f}

🧪 Lab Charges   : ₹{bill[4]:,.2f}

🧾 GST           : ₹{bill[5]:,.2f}

------------------------------------------------------------

💰 TOTAL AMOUNT  : ₹{bill[6]:,.2f}

============================================================
           Thank You • Get Well Soon ❤️
============================================================
"""

        return card(text, _bill_card_from_row(bill))

    # ==================================================
    # SQL REPORTS
    # ==================================================

    elif action == "sql_report":

        result = data["result"]

        if "error" in result:
            return card(f"""
============================================================
                     ERROR
============================================================

❌ {result['error']}

============================================================
""")

        if result.get("type") == "INSERT":
            return card(f"""
============================================================
                  INSERT SUCCESSFUL
============================================================

✅ {result['message']}

============================================================
""")

        if result.get("type") == "UPDATE":
            return card(f"""
============================================================
                  UPDATE SUCCESSFUL
============================================================

✅ {result['message']}

============================================================
""")

        if result.get("type") == "DELETE":
            return card(f"""
============================================================
                  DELETE SUCCESSFUL
============================================================

✅ {result['message']}

============================================================
""")

        rows = result.get("rows", [])
        columns = result.get("columns", [])

        if len(rows) == 0:
            return card("""
============================================================
                  NO RECORDS FOUND
============================================================

No matching data found.

============================================================
""")

        # ==================================================
        # PATIENT DETAILS / PATIENT LIST CARD
        # ==================================================
        # Handles both "Show Sujal" (1 row) and "Show all
        # patients" (many rows) — same column shape, just a
        # different row count, so one branch covers both.

        if columns == ["id", "name", "age", "gender", "doctor"]:

            patients = [_patient_row_from_columns(columns, r) for r in rows]

            if len(rows) == 1:
                patient = rows[0]
                text = f"""
============================================================
                 PATIENT DETAILS
============================================================

🆔 Patient ID : {patient[0]}

👤 Name       : {patient[1]}

🎂 Age        : {patient[2]}

⚧ Gender      : {patient[3]}

👨‍⚕ Doctor     : {patient[4]}

============================================================
"""
                title = "Patient Details"
            else:
                lines = [
                    "============================================================",
                    "                  PATIENT LIST",
                    "============================================================",
                    "",
                ]
                for p in rows:
                    lines.append(f"🆔 {p[0]}  👤 {p[1]}  🎂 {p[2]}  ⚧ {p[3]}  👨‍⚕ {p[4]}")
                lines += [
                    "",
                    f"📄 Total Records : {len(rows)}",
                    "============================================================",
                ]
                text = "\n".join(lines)
                title = "Patient List"

            return card(text, {
                "kind": "patient_list",
                "title": title,
                "patients": patients,
            })

        # ==================================================
        # LATEST BILL CARD
        # ==================================================

        if columns == [
            "bill_id",
            "patient_name",
            "consultation",
            "medicine",
            "lab",
            "gst",
            "total",
            "created_at"
        ] and len(rows) == 1:

            bill = rows[0]

            text = f"""
============================================================
                 LATEST BILL
============================================================

🧾 Bill ID        : {bill[0]}

👤 Patient        : {bill[1]}

------------------------------------------------------------

👨‍⚕ Consultation : ₹{bill[2]:,.2f}

💊 Medicine      : ₹{bill[3]:,.2f}

🧪 Lab Charges   : ₹{bill[4]:,.2f}

🧾 GST           : ₹{bill[5]:,.2f}

------------------------------------------------------------

💰 TOTAL         : ₹{bill[6]:,.2f}

📅 Date          : {bill[7]}

============================================================
"""

            return card(text, _bill_card_from_row(bill))

        # ==================================================
        # MEDICINE / INVENTORY LIST CARD
        # ==================================================
        # New in this upgrade — "Show inventory" / "Show medicines"
        # previously fell all the way through to the generic table
        # branch at the bottom (text-only). This gives it a real
        # structured card while keeping the same text table too.

        if columns == ["medicine_id", "medicine_name", "stock", "price", "supplier", "expiry_date"]:

            inventory_rows = []
            for m in rows:
                stock = m[2]
                if stock <= 0:
                    status = "Out of Stock"
                elif stock < 50:
                    status = "Low Stock"
                else:
                    status = "In Stock"
                inventory_rows.append({
                    "name": m[1],
                    # No dedicated "category" column exists in the
                    # medicines table — supplier is the closest
                    # available grouping, reused here rather than
                    # inventing a fake category.
                    "category": m[4],
                    "stock": stock,
                    "price": m[3],
                    "status": status,
                })

            output = "\n"
            output += "=" * 90 + "\n"
            output += "MEDICINE INVENTORY\n"
            output += "=" * 90 + "\n\n"
            output += " | ".join(columns) + "\n"
            output += "-" * 90 + "\n"
            for row in rows:
                output += " | ".join(str(x) for x in row) + "\n"
            output += "-" * 90 + "\n"
            output += f"📄 Total Records : {len(rows)}\n"

            return card(output, {
                "kind": "inventory",
                "title": "Medicine Inventory",
                "inventory": inventory_rows,
            })

        # ==================================================
        # PATIENT + MEDICINE HISTORY (JOIN card)
        # ==================================================
        # No matching structured card shape exists on the frontend
        # yet for this compound view (patient + purchases + stock +
        # latest bill all in one) — stays text-only for now, exact
        # same output as before this upgrade.

        history_columns = {"name", "age", "gender", "doctor", "medicine_name"}

        if history_columns.issubset(set(columns)):

            name_i = columns.index("name")
            age_i = columns.index("age")
            gender_i = columns.index("gender")
            doctor_i = columns.index("doctor")
            med_i = columns.index("medicine_name")
            qty_i = columns.index("quantity") if "quantity" in columns else None
            date_i = columns.index("sale_date") if "sale_date" in columns else None
            stock_i = columns.index("current_stock") if "current_stock" in columns else None
            bill_total_i = columns.index("latest_bill_total") if "latest_bill_total" in columns else None
            bill_date_i = columns.index("latest_bill_date") if "latest_bill_date" in columns else None

            first = rows[0]

            lines = [
                "============================================================",
                "                 PATIENT INFORMATION",
                "============================================================",
                "",
                f"👤 Patient : {first[name_i]}",
                "✅ Patient Found",
                "",
                f"Age       : {first[age_i]}",
                f"Gender    : {first[gender_i]}",
                f"Doctor    : {first[doctor_i]}",
                "",
                "------------------------------------------------------------",
                "",
                "💊 MEDICINE HISTORY",
                "",
            ]

            medicine_rows = [r for r in rows if r[med_i]]

            if not medicine_rows:
                lines.append("No medicine purchases on record.")
            else:
                for idx, r in enumerate(medicine_rows, start=1):
                    entry = f"{idx}. {r[med_i]}"
                    if qty_i is not None:
                        entry += f" (x{r[qty_i]})"
                    if date_i is not None:
                        entry += f" — {r[date_i]}"
                    if stock_i is not None and r[stock_i] is not None:
                        stock = r[stock_i]
                        flag = "⚠️ LOW STOCK" if stock < 50 else "✅ in stock"
                        entry += f"  [current stock: {stock} — {flag}]"
                    lines.append(entry)

            lines += [
                "",
                "------------------------------------------------------------",
                "",
                f"📋 Total Medicines : {len(medicine_rows)}",
            ]

            if bill_total_i is not None and first[bill_total_i] is not None:
                lines += [
                    "",
                    "------------------------------------------------------------",
                    "",
                    "🧾 LATEST BILL",
                    "",
                    f"Total : ₹{first[bill_total_i]:,.2f}",
                    f"Date  : {first[bill_date_i] if bill_date_i is not None else 'N/A'}",
                ]

            lines += [
                "",
                "============================================================",
            ]

            # Structured card — built alongside the exact same text
            # above, not replacing it. This is a genuinely different
            # shape than every other card (patient info + a list of
            # purchases + latest bill, all in one), so it gets its
            # own dedicated kind/field rather than being force-fit
            # into patient_list, sale, or the generic table card —
            # any of those would either lose the "belongs together"
            # relationship or need duplicate patient info on every
            # row.
            medicines_structured = []
            for r in medicine_rows:
                stock_val = r[stock_i] if stock_i is not None else None
                if stock_val is None:
                    stock_status = "Unknown"
                elif stock_val <= 0:
                    stock_status = "Out of Stock"
                elif stock_val < 50:
                    stock_status = "Low Stock"
                else:
                    stock_status = "In Stock"

                medicines_structured.append({
                    "name": r[med_i],
                    "quantity": r[qty_i] if qty_i is not None else None,
                    "saleDate": r[date_i] if date_i is not None else None,
                    "currentStock": stock_val,
                    "stockStatus": stock_status,
                })

            latest_bill_structured = None
            if bill_total_i is not None and first[bill_total_i] is not None:
                latest_bill_structured = {
                    "total": first[bill_total_i],
                    "date": first[bill_date_i] if bill_date_i is not None else None,
                }

            structured = {
                "kind": "patient_history",
                "title": "Patient History",
                "patientHistory": {
                    # NOTE: this specific JOIN query never selects
                    # patients.id — only name/age/gender/doctor — so
                    # this deliberately does NOT reuse the strict
                    # PatientRow shape (which requires a real id).
                    # Sending a fake null id would be worse than not
                    # having one.
                    "patient": {
                        "name": first[name_i],
                        "age": first[age_i],
                        "gender": first[gender_i],
                        "doctor": first[doctor_i],
                    },
                    "medicines": medicines_structured,
                    "latestBill": latest_bill_structured,
                },
            }

            return card("\n".join(lines), structured)

        # ==================================================
        # HOSPITAL DASHBOARD
        # ==================================================

        dashboard_columns = {
            "total_patients",
            "total_bills",
            "total_revenue",
            "today_revenue",
        }

        if dashboard_columns.issubset(set(columns)) and len(rows) == 1:

            row = rows[0]

            total_patients = row[0]
            total_bills = row[1]
            total_revenue = row[2] or 0
            today_revenue = row[3] or 0
            total_medicine_stock = row[4] if len(row) > 4 else 0
            total_medicine_sold = row[5] if len(row) > 5 else 0
            top_medicine = row[6] if len(row) > 6 and row[6] else "N/A"
            low_stock = row[7] if len(row) > 7 else 0

            low_stock_flag = "⚠️" if low_stock > 0 else "✅"

            text = f"""
╔══════════════════════════════════════════════════════════╗
║                  🏥  HOSPITAL DASHBOARD                    ║
╚══════════════════════════════════════════════════════════╝

  👨‍⚕  Total Patients          {total_patients}
  🧾  Total Bills             {total_bills}
  💰  Total Revenue           ₹{total_revenue:,.2f}
  📅  Today's Revenue         ₹{today_revenue:,.2f}

  ──────────────────────────────────────────────────────

  💊  Total Medicine Stock    {total_medicine_stock}
  📈  Medicines Sold          {total_medicine_sold}
  🏆  Top Selling Medicine    {top_medicine}
  {low_stock_flag}  Low Stock Medicines     {low_stock}

  ──────────────────────────────────────────────────────

  🟢  Database Status         CONNECTED
  🤖  AI Assistant            ACTIVE

╚══════════════════════════════════════════════════════════╝
"""

            # LIMITATION: DASHBOARD_SQL (sql_agent.py) only returns
            # system-wide totals, not day-over-day deltas or a
            # per-medicine sales breakdown. So "delta"/"trend" below
            # are placeholders (no historical baseline exists to
            # compute a real change from), and medicineSales is an
            # empty list rather than fabricated numbers.
            # topSellingMedicine.units is a best-effort — it's the
            # overall total medicines sold, not that specific
            # medicine's own count, because the SQL doesn't break
            # that down. If real trend/per-medicine data matters
            # later, DASHBOARD_SQL needs a second query added.
            structured = {
                "kind": "dashboard",
                "title": "Hospital Dashboard",
                "dashboard": {
                    "metrics": [
                        {"label": "Total Patients", "value": str(total_patients), "delta": "—", "trend": "up", "icon": "patients"},
                        {"label": "Total Bills", "value": str(total_bills), "delta": "—", "trend": "up", "icon": "bills"},
                        {"label": "Total Revenue", "value": f"₹{total_revenue:,.2f}", "delta": "—", "trend": "up", "icon": "revenue"},
                        {"label": "Today's Revenue", "value": f"₹{today_revenue:,.2f}", "delta": "—", "trend": "up", "icon": "revenue"},
                        {"label": "Medicine Stock", "value": str(total_medicine_stock), "delta": "—", "trend": "up", "icon": "inventory"},
                        {"label": "Medicines Sold", "value": str(total_medicine_sold), "delta": "—", "trend": "up", "icon": "inventory"},
                        {"label": "Low Stock Medicines", "value": str(low_stock), "delta": "—", "trend": "down" if low_stock > 0 else "up", "icon": "inventory"},
                    ],
                    "topSellingMedicine": {
                        "name": top_medicine,
                        "units": total_medicine_sold,
                        "revenue": "N/A",
                    },
                    "medicineSales": [],
                },
            }

            return card(text, structured)

        # ==================================================
        # SINGLE VALUE REPORT
        # ==================================================

        if len(columns) == 1 and len(rows) == 1:

            text = f"""
============================================================
                     REPORT
============================================================

📊 {columns[0]} : {rows[0][0]}

============================================================
"""
            return card(text, {
                "kind": "report",
                "title": "Report",
                "report": {
                    "title": columns[0],
                    "rows": [
                        {"metric": columns[0], "value": str(rows[0][0]), "change": ""}
                    ],
                },
            })

        # ==================================================
        # NORMAL TABLE REPORT
        # ==================================================
        # Arbitrary LLM-generated SQL can return any shape of
        # columns/rows — this used to stay text-only forever,
        # because ReportRow (metric/value/change) can't represent
        # a real N-column table without dropping or misrepresenting
        # data. Now uses a genuinely generic table card instead
        # (kind 'sql_result' + table{columns, rows} — see
        # TableCard in ResponseCardView.tsx), so any arbitrary
        # analytics question ("which medicine sold more", "show
        # all bills", "top 5 patients by spending", etc.) gets an
        # accurate real card instead of plain text.

        output = "\n"
        output += "=" * 90 + "\n"
        output += "RESULT\n"
        output += "=" * 90 + "\n\n"

        output += " | ".join(columns)
        output += "\n"
        output += "-" * 90 + "\n"

        for row in rows:
            output += " | ".join(str(x) for x in row)
            output += "\n"

        output += "-" * 90 + "\n"
        output += f"📄 Total Records : {len(rows)}\n"

        return card(output, {
            "kind": "sql_result",
            "title": "Query Result",
            "table": {
                "columns": columns,
                # Row values are already plain Python types coming
                # out of sqlite3 (str/int/float/None) — safe to
                # pass straight through as JSON. list(row) turns
                # each sqlite3 row tuple into a plain list.
                "rows": [list(row) for row in rows],
            },
        })

    # ==================================================
    # UNKNOWN ACTION
    # ==================================================

    return card("""
============================================================
                    UNKNOWN REQUEST
============================================================

❌ Unsupported report action.

============================================================
""")