"""
tools/documents.py

The Document Engine — a shared, reusable system for generating any
PDF document and comparing any two things, instead of writing a new
hand-built function for every single report type.

CHANGED (professional layout): render_document() now draws a real
letterhead header (clinic name + a thin brand-colored rule) and a
footer (generated timestamp + page number) on every page, and the
tables use a more polished color palette and spacing. This is a
purely visual upgrade — no document type's DATA or registry entry
needed to change, since every document type already flows through
this one shared function.
"""

from tools.sql_tool import execute_sql


# =====================================================
# BRANDING — change these two lines to rebrand every PDF at once
# =====================================================
CLINIC_NAME = "Medical Billing AI — Hospital Records"
BRAND_COLOR_HEX = "#2563eb"  # matches the app's primary blue


# =====================================================
# PART 1 — PDF RENDERING ENGINE (shared by every document type)
# =====================================================

def render_document(title, sections, subtitle=None, note=None):
    """
    Builds a PDF from a title and a list of sections. Each section
    is a dict with a "type":

        {"type": "table", "heading": "...", "columns": [...], "rows": [...]}
        {"type": "text", "content": "..."}
        {"type": "keyvalue", "heading": "...", "items": {"Patient": "Sujal", ...}}

    Every page gets a consistent letterhead header and footer (see
    _draw_header_footer below) — this is what makes the finished
    PDF look like one coherent document instead of a raw data dump.

    Returns a BytesIO buffer ready to send with Flask's send_file(),
    same as every PDF route already does.
    """
    import io
    from datetime import datetime
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    buffer = io.BytesIO()

    # Reserve top/bottom margin space for the header/footer drawn
    # separately below, so body content never overlaps them.
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=28 * mm,
        bottomMargin=20 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Title"],
        fontSize=18,
        spaceAfter=4,
        textColor=colors.HexColor("#0f172a"),
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#475569"),
        spaceAfter=10,
    )
    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor(BRAND_COLOR_HEX),
        spaceBefore=4,
        spaceAfter=6,
    )
    note_style = ParagraphStyle(
        "Note",
        parent=styles["Italic"],
        fontSize=8,
        textColor=colors.HexColor("#64748b"),
    )

    elements = [Paragraph(title, title_style)]
    if subtitle:
        elements.append(Paragraph(subtitle, subtitle_style))
    elements.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#e2e8f0")))
    elements.append(Spacer(1, 14))

    for section in sections:
        kind = section.get("type")

        if kind == "table":
            if section.get("heading"):
                elements.append(Paragraph(section["heading"], heading_style))

            columns = section["columns"]
            rows = section["rows"]

            table_data = [columns] + [
                [str(c) if c is not None else "-" for c in row] for row in rows
            ]
            table = Table(table_data, repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BRAND_COLOR_HEX)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 16))

        elif kind == "text":
            elements.append(Paragraph(section["content"], styles["Normal"]))
            elements.append(Spacer(1, 10))

        elif kind == "keyvalue":
            if section.get("heading"):
                elements.append(Paragraph(section["heading"], heading_style))

            kv_rows = [[k, str(v) if v is not None else "-"] for k, v in section["items"].items()]
            kv_table = Table(kv_rows, colWidths=[140, 320], hAlign="LEFT")
            kv_table.setStyle(TableStyle([
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#334155")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
            ]))
            elements.append(kv_table)
            elements.append(Spacer(1, 16))

    if note:
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(f"ℹ {note}", note_style))

    generated_at = datetime.now().strftime("%d %b %Y, %I:%M %p")

    def _draw_header_footer(canvas_obj, doc_obj):
        canvas_obj.saveState()
        page_w, page_h = A4

        # --- Header: clinic name + brand-colored rule ---
        canvas_obj.setFont("Helvetica-Bold", 10)
        canvas_obj.setFillColor(colors.HexColor("#0f172a"))
        canvas_obj.drawString(18 * mm, page_h - 15 * mm, CLINIC_NAME)

        canvas_obj.setStrokeColor(colors.HexColor(BRAND_COLOR_HEX))
        canvas_obj.setLineWidth(1.5)
        canvas_obj.line(18 * mm, page_h - 18 * mm, page_w - 18 * mm, page_h - 18 * mm)

        # --- Footer: generated timestamp (left) + page number (right) ---
        canvas_obj.setFont("Helvetica", 7.5)
        canvas_obj.setFillColor(colors.HexColor("#94a3b8"))
        canvas_obj.drawString(18 * mm, 12 * mm, f"Generated {generated_at}")
        canvas_obj.drawRightString(page_w - 18 * mm, 12 * mm, f"Page {doc_obj.page}")

        canvas_obj.restoreState()

    doc.build(elements, onFirstPage=_draw_header_footer, onLaterPages=_draw_header_footer)
    buffer.seek(0)
    return buffer


# =====================================================
# PART 2 — COMPARISON ENGINE (generic, works for anything)
# =====================================================
# Unchanged below this point — the layout upgrade above is the only
# change needed, since every document/comparison type already
# flows through render_document().

def _pct_change(this_value, last_value):
    if last_value == 0:
        return "N/A" if this_value == 0 else "+∞%"
    change = ((this_value - last_value) / last_value) * 100
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:.1f}%"


def compare_metrics(metrics, filter_a, filter_b, label_a="A", label_b="B"):
    rows = []

    for metric in metrics:
        sql_a = metric["sql"].format(filter=filter_a)
        sql_b = metric["sql"].format(filter=filter_b)

        result_a = execute_sql(sql_a)
        result_b = execute_sql(sql_b)

        value_a = (result_a["rows"][0][0] if result_a.get("rows") else 0) or 0
        value_b = (result_b["rows"][0][0] if result_b.get("rows") else 0) or 0

        fmt = metric.get("format", "{:,.0f}")
        rows.append([
            metric["label"],
            fmt.format(value_a),
            fmt.format(value_b),
            _pct_change(value_a, value_b),
        ])

    return rows, [label_a, label_b]


import re


def _prepare_doctor_filter(raw):
    return raw.replace("'", "''")


def _prepare_month_filter(raw):
    if raw in (None, "", "this-month"):
        return "strftime('%Y-%m','now')"
    if raw == "last-month":
        return "strftime('%Y-%m','now','-1 month')"
    if re.fullmatch(r"\d{4}-\d{2}", raw):
        return f"'{raw}'"
    raise ValueError(f"Invalid month value '{raw}' — expected YYYY-MM, 'this-month', or 'last-month'.")


COMPARISON_TEMPLATES = {
    "doctors": {
        "title": "Doctor Comparison Report",
        "metrics": [
            {"label": "Patients Treated", "sql": "SELECT COUNT(*) FROM patients WHERE doctor='{filter}'"},
        ],
        "prepare_filter": _prepare_doctor_filter,
    },
    "months": {
        "title": "Monthly Comparison Report",
        "metrics": [
            {"label": "Total Revenue", "sql": "SELECT IFNULL(SUM(total),0) FROM bills WHERE strftime('%Y-%m', created_at) = {filter}", "format": "Rs. {:,.2f}"},
            {"label": "Total Bills", "sql": "SELECT COUNT(*) FROM bills WHERE strftime('%Y-%m', created_at) = {filter}", "format": "{:,.0f}"},
            {"label": "Medicines Sold (units)", "sql": "SELECT IFNULL(SUM(quantity),0) FROM medicine_sales WHERE strftime('%Y-%m', sale_date) = {filter}", "format": "{:,.0f}"},
        ],
        "prepare_filter": _prepare_month_filter,
        "default_a": "this-month",
        "default_b": "last-month",
    },
}


def compare_documents(compare_type, raw_a, raw_b):
    template = COMPARISON_TEMPLATES.get(compare_type)
    if not template:
        return None, f"Unknown comparison type '{compare_type}'. Available: {', '.join(COMPARISON_TEMPLATES.keys())}"

    raw_a = raw_a or template.get("default_a")
    raw_b = raw_b or template.get("default_b")

    if not raw_a or not raw_b:
        return None, "Both 'a' and 'b' values are required for this comparison type."

    try:
        filter_a = template["prepare_filter"](raw_a)
        filter_b = template["prepare_filter"](raw_b)
    except ValueError as e:
        return None, str(e)

    rows, labels = compare_metrics(
        metrics=template["metrics"],
        filter_a=filter_a, filter_b=filter_b,
        label_a=raw_a, label_b=raw_b,
    )

    pdf = render_document(
        template["title"],
        [{"type": "table", "columns": ["Metric", labels[0], labels[1], "Change"], "rows": rows}],
        subtitle=f"{raw_a} vs. {raw_b}",
        note=(
            "Note: patient registration counts are not included — the patients "
            "table does not store a registration date, so month-over-month new-"
            "patient counts cannot be computed."
        ) if compare_type == "months" else None,
    )
    return pdf, None


# =====================================================
# PART 3 — DOCUMENT REGISTRY  (unchanged from before)
# =====================================================

def _fetch_patients(params):
    return execute_sql("SELECT id, name, age, gender, doctor FROM patients;")


def _layout_patients(result):
    return {
        "title": "Patient List",
        "sections": [
            {"type": "table", "columns": result["columns"], "rows": result["rows"]},
        ],
    }


def _fetch_sales(params):
    return execute_sql(
        "SELECT medicine_name, patient_name, quantity, amount, sale_date "
        "FROM medicine_sales ORDER BY sale_date DESC;"
    )


def _layout_sales(result):
    return {
        "title": "Medicine Sales Report",
        "sections": [
            {"type": "table", "columns": result["columns"], "rows": result["rows"]},
        ],
    }


def _fetch_patient_report(params):
    name = params["name"].replace("'", "''")
    sql = f"""
    SELECT p.name, p.age, p.gender, p.doctor,
           ms.medicine_name, ms.quantity, ms.sale_date,
           m.stock AS current_stock,
           b.total AS latest_bill_total, b.created_at AS latest_bill_date
    FROM patients p
    LEFT JOIN medicine_sales ms ON LOWER(p.name) = LOWER(ms.patient_name)
    LEFT JOIN medicines m ON LOWER(ms.medicine_name) = LOWER(m.medicine_name)
    LEFT JOIN bills b ON LOWER(p.name) = LOWER(b.patient_name)
        AND b.bill_id = (
            SELECT MAX(bill_id) FROM bills WHERE LOWER(patient_name) = LOWER(p.name)
        )
    WHERE LOWER(p.name) = LOWER('{name}');
    """
    return execute_sql(sql)


def _layout_patient_report(result):
    return {
        "title": f"Patient Report — {result['rows'][0][0] if result['rows'] else ''}",
        "sections": [
            {"type": "table", "columns": result["columns"], "rows": result["rows"]},
        ],
    }


def _fetch_prescription(params):
    return _fetch_patient_report(params)


def _layout_prescription(result):
    if not result.get("rows"):
        return {
            "title": "Prescription Slip",
            "sections": [{"type": "text", "content": "No patient found with that name."}],
        }

    first = result["rows"][0]
    columns = result["columns"]
    name_i, age_i, gender_i, doctor_i = columns.index("name"), columns.index("age"), columns.index("gender"), columns.index("doctor")
    med_i, qty_i, date_i = columns.index("medicine_name"), columns.index("quantity"), columns.index("sale_date")

    medicine_rows = [
        [r[med_i], r[qty_i], r[date_i]]
        for r in result["rows"] if r[med_i]
    ]

    return {
        "title": "Prescription Slip",
        "sections": [
            {
                "type": "keyvalue",
                "heading": "Patient",
                "items": {
                    "Name": first[name_i],
                    "Age": first[age_i],
                    "Gender": first[gender_i],
                    "Doctor": first[doctor_i],
                },
            },
            {
                "type": "table",
                "heading": "Medicines Dispensed",
                "columns": ["Medicine", "Quantity", "Date"],
                "rows": medicine_rows if medicine_rows else [["No medicines on record", "-", "-"]],
            },
        ],
        "note": (
            "Note: this reflects medicines dispensed/purchased on record, not a "
            "separately stored doctor's prescription — this system does not "
            "currently have a dedicated prescriptions table."
        ),
    }


# Fixed Doctor Fee — kept as a named constant (not a magic 450.00
# scattered across files) so it's obvious this must always match
# the same value in agents/billing_agent.py. The bills table itself
# does NOT store doctor_fee as its own column (create_bill() is
# only ever called with consultation/medicine/lab/gst/total) — it's
# silently folded into the saved `total`. Without this constant,
# the PDF invoice would show line items that don't add up to the
# total, which looks like a math error to anyone reading it.
DOCTOR_FEE = 450.00


def _fetch_invoice(params):
    name = params["name"].replace("'", "''")
    return execute_sql(
        "SELECT bill_id, patient_name, consultation, medicine, lab, gst, total, created_at "
        "FROM bills WHERE LOWER(patient_name) = LOWER('" + name + "') "
        "ORDER BY bill_id DESC LIMIT 1;"
    )


def _layout_invoice(result):
    bill_id, patient_name, consultation, medicine, lab, gst, total, created_at = result["rows"][0]

    # Recompute subtotal the same way billing_agent.py originally
    # did, purely to LABEL the breakdown correctly — the actual
    # stored gst/total from the database are still what's displayed
    # and trusted as the source of truth, this just fills in the
    # one missing line item (Doctor Fee) so the rows visibly add up.
    subtotal = consultation + medicine + lab + DOCTOR_FEE

    return {
        "title": "Medical Invoice",
        "sections": [
            {
                "type": "keyvalue",
                "heading": "Bill Details",
                "items": {
                    "Bill ID": bill_id,
                    "Patient": patient_name,
                    "Date": created_at,
                },
            },
            {
                "type": "table",
                "heading": "Charges",
                "columns": ["Item", "Amount (Rs.)"],
                "rows": [
                    ["Consultation", f"{consultation:,.2f}"],
                    ["Medicine", f"{medicine:,.2f}"],
                    ["Lab Charges", f"{lab:,.2f}"],
                    ["Doctor Fee", f"{DOCTOR_FEE:,.2f}"],
                    ["Subtotal", f"{subtotal:,.2f}"],
                    ["GST (18%)", f"{gst:,.2f}"],
                    ["Total", f"{total:,.2f}"],
                ],
            },
        ],
        "note": (
            "Payment Status: Paid. Thank you for choosing our hospital."
        ),
    }


DOCUMENT_TEMPLATES = {
    "patients":       {"fetch": _fetch_patients,        "layout": _layout_patients},
    "sales":          {"fetch": _fetch_sales,            "layout": _layout_sales},
    "patient":        {"fetch": _fetch_patient_report,   "layout": _layout_patient_report},
    "prescription":   {"fetch": _fetch_prescription,     "layout": _layout_prescription},
    "invoice":        {"fetch": _fetch_invoice,          "layout": _layout_invoice},
}


def generate_document(template_name, params):
    template = DOCUMENT_TEMPLATES.get(template_name)
    if not template:
        return None, f"Unknown document type '{template_name}'. Available: {', '.join(DOCUMENT_TEMPLATES.keys())}"

    result = template["fetch"](params)

    if "error" in result:
        return None, result["error"]

    if not result.get("rows"):
        return None, f"No data found for '{template_name}' with the given parameters."

    layout = template["layout"](result)
    pdf = render_document(layout["title"], layout["sections"], note=layout.get("note"))
    return pdf, None