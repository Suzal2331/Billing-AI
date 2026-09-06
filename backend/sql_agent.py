print("######## SQL AGENT LOADED — AMBIGUOUS-UPDATE-GUARD-V6 ########")

from llm import llm

# Returned by generate_sql() instead of a SQL statement when an
# UPDATE was requested but the message never actually specified
# what the new value should be — e.g. "Update Dhananjay Doctor"
# says WHICH field to change but not what to change it TO. Every
# call site that runs generate_sql() must check for this sentinel
# before passing its result to execute_sql() — see orchestrator.py
# and inventory_agent.py.
NEEDS_VALUE_SENTINEL = "NEEDS_VALUE"

SCHEMA = """
Database : medical.db

Tables

patients
---------
id
name
age
gender
doctor

bills
---------
bill_id
patient_name
consultation
medicine
lab
gst
total
created_at

medicines
---------
medicine_id
medicine_name
stock
price
supplier
expiry_date

medicine_sales
---------
sale_id
patient_name
medicine_name
quantity
amount
sale_date
"""

# =====================================================
# HARDCODED / DETERMINISTIC REPORTS
# =====================================================
# These are fixed, well-known reports. Letting the LLM regenerate
# their SQL every time is a real risk — it drifted into a wrong
# column count/order for the dashboard more than once. Matching
# the query text and returning known-good SQL directly removes
# that risk entirely (and skips an LLM call, so it's faster too).
#
# Only genuinely flexible/novel questions fall through to the LLM.
# =====================================================

# ---- Hospital Dashboard --------------------------------------
# COLUMN ORDER IS LOAD-BEARING: report_agent.py's dashboard card
# unpacks this by position (row[0], row[1], ...), not by name.
# If you change a column here, update report_agent.py's
# "HOSPITAL DASHBOARD" section unpacking to match.
#
# Order:
#   0 total_patients
#   1 total_bills
#   2 total_revenue
#   3 today_revenue
#   4 total_medicine_stock
#   5 total_medicine_sold
#   6 top_selling_medicine
#   7 low_stock_medicines

DASHBOARD_SQL = """
SELECT
(SELECT COUNT(*) FROM patients) AS total_patients,
(SELECT COUNT(*) FROM bills) AS total_bills,
(SELECT IFNULL(SUM(total),0) FROM bills) AS total_revenue,
(SELECT IFNULL(SUM(total),0) FROM bills WHERE created_at = DATE('now')) AS today_revenue,
(SELECT IFNULL(SUM(stock),0) FROM medicines) AS total_medicine_stock,
(SELECT IFNULL(SUM(quantity),0) FROM medicine_sales) AS total_medicine_sold,
(SELECT medicine_name
 FROM medicine_sales
 GROUP BY medicine_name
 ORDER BY SUM(quantity) DESC
 LIMIT 1) AS top_selling_medicine,
(SELECT COUNT(*) FROM medicines WHERE stock < 50) AS low_stock_medicines;
"""

DASHBOARD_TRIGGERS = [
    "dashboard",
    "hospital dashboard",
    "hospital overview",
    "hospital summary",
    "hospital status"
]

# ---- Count Patients --------------------------------------------

COUNT_PATIENTS_SQL = """
SELECT COUNT(*) AS total_patients
FROM patients;
"""

COUNT_PATIENTS_TRIGGERS = [
    "count patients",
    "how many patients",
    "total patients",
    "number of patients"
]

# ---- Latest Bill --------------------------------------------

LATEST_BILL_SQL = """
SELECT *
FROM bills
ORDER BY bill_id DESC
LIMIT 1;
"""

LATEST_BILL_TRIGGERS = [
    "latest bill",
    "show latest bill",
    "last bill",
    "most recent bill"
]

# ---- Today's Revenue --------------------------------------------

TODAY_REVENUE_SQL = """
SELECT
IFNULL(SUM(total),0) AS today_revenue
FROM bills
WHERE created_at = DATE('now');
"""

TODAY_REVENUE_TRIGGERS = [
    "today's revenue",
    "todays revenue",
    "revenue today",
    "today revenue"
]

# ---- Top Selling Medicine --------------------------------------------

TOP_MEDICINE_SQL = """
SELECT
medicine_name,
SUM(quantity) AS sold
FROM medicine_sales
GROUP BY medicine_name
ORDER BY sold DESC
LIMIT 1;
"""

TOP_MEDICINE_TRIGGERS = [
    "top selling medicine",
    "best selling medicine",
    "most sold medicine"
]

# ---- Full Inventory --------------------------------------------
# Added as a hardcoded shortcut for the same reason as the others
# above: "Show inventory" is one of the most common commands in
# this app (it's a default suggestion chip), so skipping the LLM
# call for it entirely — not just avoiding a wrong answer, but
# avoiding the round-trip latency altogether — is worth doing for
# UX, not just correctness.

INVENTORY_SQL = """
SELECT * FROM medicines;
"""

INVENTORY_TRIGGERS = [
    "show inventory",
    "medicine inventory",
    "show medicines",
    "list medicines",
    "all medicines",
    "medicine stock",
    "show stock",
]

# Order matters: more specific triggers are checked first so a
# query like "today's revenue" doesn't get swallowed by a looser
# match further down the list.
HARDCODED_REPORTS = [
    (DASHBOARD_TRIGGERS, DASHBOARD_SQL),
    (COUNT_PATIENTS_TRIGGERS, COUNT_PATIENTS_SQL),
    (LATEST_BILL_TRIGGERS, LATEST_BILL_SQL),
    (TODAY_REVENUE_TRIGGERS, TODAY_REVENUE_SQL),
    (TOP_MEDICINE_TRIGGERS, TOP_MEDICINE_SQL),
    (INVENTORY_TRIGGERS, INVENTORY_SQL),
]

# =====================================================
# PATIENT EXISTENCE + MEDICINE/BILL HISTORY (deterministic JOIN)
# =====================================================
# Despite having this EXACT query as a required few-shot example
# further down in the prompt, the LLM still failed it during
# testing — it returned two separate SELECT statements instead of
# one JOIN query, which execute_sql() correctly rejected ("You can
# only execute one statement at a time"). Same lesson as the
# dashboard: for a well-known pattern, build the SQL ourselves
# instead of trusting the LLM to follow one example among ~30.

PATIENT_HISTORY_TRIGGERS = [
    "check if",
    "is there",
    "is registered",
    "does exist",
    "what medicines",
    "which medicines",
    "medicines has",
    "medicines taken",
    "medicine history",
    "patient history",
    "purchase history",
    "bought",
    "purchased",
    "what has",
    "low on stock",
    "low in stock",
]

# Words that are never a patient's name, even if capitalized —
# mostly sentence-starters and question words that happen to be
# capitalized because they open the sentence.
_NAME_STOPWORDS = {
    "check", "is", "are", "there", "show", "what", "which",
    "medicines", "medicine", "history", "find", "does", "exist",
    "registered", "and", "the", "a", "an", "he", "she", "his",
    "her", "has", "have", "taken", "purchase", "purchased",
    "bought", "for", "of", "please",
}


def _extract_patient_name(user_query):
    """
    Heuristic: the first capitalized, alphabetic word in the query
    that isn't a known stopword. Good enough for "Check if Sujal
    is there..." style queries; returns None if nothing looks like
    a name, so the caller can fall back to the LLM path.
    """
    for word in user_query.strip().split():
        cleaned = word.strip(",.?!'\"")

        # Strip a possessive suffix ('s / ’s) BEFORE the isalpha
        # check — "Sujal's" has the apostrophe in the middle of the
        # word, not at either edge, so the strip() call above never
        # touches it, and "Sujal's".isalpha() is False. Without
        # this, any possessive phrasing ("Sujal's details", "Raj's
        # bill") silently fails to extract a name at all, and the
        # whole deterministic path falls through as if no name was
        # ever mentioned.
        for suffix in ("'s", "\u2019s"):  # straight ' and curly '
            if cleaned.endswith(suffix):
                cleaned = cleaned[:-len(suffix)]
                break

        if not cleaned or not cleaned.isalpha():
            continue
        if cleaned.lower() in _NAME_STOPWORDS:
            continue
        if cleaned[0].isupper():
            return cleaned
    return None


def _try_patient_history_sql(user_query):

    lower_query = user_query.lower()

    if not any(trigger in lower_query for trigger in PATIENT_HISTORY_TRIGGERS):
        return None

    name = _extract_patient_name(user_query)

    if not name:
        return None

    safe_name = name.replace("'", "''")

    print(f"[SQL Agent] Patient history pattern matched (name={name!r}) -> skipping LLM")

    # Includes the patient's own latest bill (via a correlated
    # subquery, not the system-wide "latest bill" shortcut — that
    # one previously hijacked compound questions like "Sujal's
    # details, medicines, latest bill, and low stock" by returning
    # whichever patient was billed most recently system-wide) and
    # each purchased medicine's current stock level, so a single
    # question covering patient info + purchase history + billing
    # + stock status can be answered in one query instead of three.
    return f"""
SELECT
p.name,
p.age,
p.gender,
p.doctor,
ms.medicine_name,
ms.quantity,
ms.sale_date,
m.stock AS current_stock,
b.total AS latest_bill_total,
b.created_at AS latest_bill_date
FROM patients p
LEFT JOIN medicine_sales ms
    ON LOWER(p.name) = LOWER(ms.patient_name)
LEFT JOIN medicines m
    ON LOWER(ms.medicine_name) = LOWER(m.medicine_name)
LEFT JOIN bills b
    ON LOWER(p.name) = LOWER(b.patient_name)
    AND b.bill_id = (
        SELECT MAX(bill_id) FROM bills
        WHERE LOWER(patient_name) = LOWER(p.name)
    )
WHERE LOWER(p.name) = LOWER('{safe_name}');
""".strip()

PROMPT = f"""
You are an Expert SQLite SQL Generator.

Database Schema

{SCHEMA}

Rules

1. Return ONLY SQL.
2. SQLite syntax only.
3. No markdown.
4. No explanation.
5. Never generate DROP TABLE.
6. Always use WHERE for UPDATE and DELETE.
7. Never delete all rows.
8. Never update all rows.
9. Use LOWER() for text comparison.
10. Generate exactly ONE SQL statement.
11. NEVER use JOINs to combine several SEPARATE aggregate totals
    from unrelated tables into one row (e.g. total patient count +
    total revenue + total stock all at once) — this produces a
    Cartesian product and multiplies the totals. Use independent
    scalar subqueries instead, one per aggregate value.

    DO use a JOIN when the user is asking about a genuine
    relationship between a specific patient and their own
    records — e.g. "what medicines has X taken", "X's purchase
    history", "X's bills". Link patients.name to
    medicine_sales.patient_name or bills.patient_name (case
    insensitive) with LEFT JOIN, so the patient still shows up
    even if they have no purchases/bills yet.

12. CRITICAL — never invent a value for an UPDATE. If the user asks
    to update/change/set a field but the message doesn't actually
    say what the new value should be (e.g. "Update Dhananjay
    Doctor", "Change Rahul's gender", "Set Sujal's age" with no
    value given anywhere), do NOT guess one — patient names,
    numbers, or anything else. Instead, output exactly this one
    word and nothing else:

    NEEDS_VALUE

    Only generate a real UPDATE statement when the new value is
    explicitly present in the message, e.g. "Update Dhananjay's
    doctor to Dr Mehta" (value = "Dr Mehta") or "Set Sujal's age to
    25" (value = 25).

You support

- SELECT
- INSERT
- UPDATE
- DELETE

Examples

User:
Show all patients

SQL:
SELECT * FROM patients;

User:
Show Rahul

SQL:
SELECT *
FROM patients
WHERE LOWER(name)=LOWER('Rahul');

User:
Delete Rahul

SQL:
DELETE FROM patients
WHERE LOWER(name)=LOWER('Rahul');

User:
Delete bill 15

SQL:
DELETE FROM bills
WHERE bill_id=15;

User:
Update Rahul age to 26

SQL:
UPDATE patients
SET age=26
WHERE LOWER(name)=LOWER('Rahul');

User:
Change Rahul doctor to Dr Sharma

SQL:
UPDATE patients
SET doctor='Dr Sharma'
WHERE LOWER(name)=LOWER('Rahul');

User:
Increase Crocin stock by 20

SQL:
UPDATE medicines
SET stock=stock+20
WHERE LOWER(medicine_name)=LOWER('Crocin');

User:
Set Dolo stock to 100

SQL:
UPDATE medicines
SET stock=100
WHERE LOWER(medicine_name)=LOWER('Dolo');

User:
Show all bills

SQL:
SELECT *
FROM bills;

User:
Show Rahul bill

SQL:
SELECT *
FROM bills
WHERE LOWER(patient_name)=LOWER('Rahul')
ORDER BY bill_id DESC
LIMIT 1;

User:
Total sales

SQL:
SELECT
IFNULL(SUM(total),0) AS total_sales
FROM bills;

User:
Total medicines sold

SQL:
SELECT
IFNULL(SUM(quantity),0) AS total_medicines_sold
FROM medicine_sales;

User:
How many bills were generated today

SQL:
SELECT COUNT(*) AS bills_today
FROM bills
WHERE created_at=DATE('now');

User:
Show medicines

SQL:
SELECT *
FROM medicines;

User:
Low stock medicines

SQL:
SELECT *
FROM medicines
WHERE stock<50;

User:
Who is the top patient

SQL:
SELECT
patient_name,
SUM(total) AS spent
FROM bills
GROUP BY patient_name
ORDER BY spent DESC
LIMIT 1;

User:
Show expired medicines

SQL:
SELECT *
FROM medicines
WHERE expiry_date<DATE('now');

User:
Who generated the highest bill

SQL:
SELECT *
FROM bills
ORDER BY total DESC
LIMIT 1;

User:
Show revenue for this month

SQL:
SELECT
IFNULL(SUM(total),0) AS monthly_revenue
FROM bills
WHERE strftime('%Y-%m',created_at)=strftime('%Y-%m','now');

User:
Show top 5 patients by spending

SQL:
SELECT
patient_name,
SUM(total) AS spent
FROM bills
GROUP BY patient_name
ORDER BY spent DESC
LIMIT 5;

User:
Show patient count by doctor

SQL:
SELECT
doctor,
COUNT(*) AS patient_count
FROM patients
GROUP BY doctor
ORDER BY patient_count DESC;

User:
Check if Sujal is there and what medicines he has taken

SQL:
SELECT
p.name,
p.age,
p.gender,
p.doctor,
ms.medicine_name,
ms.quantity,
ms.sale_date
FROM patients p
LEFT JOIN medicine_sales ms
ON LOWER(p.name) = LOWER(ms.patient_name)
WHERE LOWER(p.name) = LOWER('Sujal');

User:
What medicines has Sujal taken

SQL:
SELECT
p.name,
p.age,
p.gender,
p.doctor,
ms.medicine_name,
ms.quantity,
ms.sale_date
FROM patients p
LEFT JOIN medicine_sales ms
ON LOWER(p.name) = LOWER(ms.patient_name)
WHERE LOWER(p.name) = LOWER('Sujal');

User:
Show Sujal's purchase history

SQL:
SELECT
p.name,
p.age,
p.gender,
p.doctor,
ms.medicine_name,
ms.quantity,
ms.sale_date
FROM patients p
LEFT JOIN medicine_sales ms
ON LOWER(p.name) = LOWER(ms.patient_name)
WHERE LOWER(p.name) = LOWER('Sujal');

User:
Show Sujal's bills and medicines

SQL:
SELECT
p.name,
b.total,
b.created_at,
ms.medicine_name,
ms.quantity
FROM patients p
LEFT JOIN bills b ON LOWER(p.name) = LOWER(b.patient_name)
LEFT JOIN medicine_sales ms ON LOWER(p.name) = LOWER(ms.patient_name)
WHERE LOWER(p.name) = LOWER('Sujal');

User:
Show patients who bought Crocin

SQL:
SELECT DISTINCT
ms.patient_name
FROM medicine_sales ms
WHERE LOWER(ms.medicine_name) = LOWER('Crocin');

User:
Which patient spent the most

SQL:
SELECT
patient_name,
SUM(total) AS spent
FROM bills
GROUP BY patient_name
ORDER BY spent DESC
LIMIT 1;
"""


def generate_sql(user_query):

    lower_query = user_query.lower().strip()

    # Check for a named-patient question FIRST. This must come
    # before the generic HARDCODED_REPORTS loop below — a question
    # like "Sujal's details, medicines, latest bill, and low stock"
    # contains the substring "latest bill", which previously made
    # it match the system-wide LATEST_BILL_SQL shortcut and return
    # whichever patient was billed most recently, ignoring that
    # Sujal was named specifically. A named patient always takes
    # priority over a generic system-wide report.
    history_sql = _try_patient_history_sql(user_query)

    if history_sql:
        return history_sql

    # Deterministic shortcuts for fixed/standard system-wide
    # reports — see HARDCODED_REPORTS above. Only genuinely novel
    # questions reach the LLM below.
    for triggers, sql in HARDCODED_REPORTS:
        if any(trigger in lower_query for trigger in triggers):
            print(f"[SQL Agent] Hardcoded report matched (trigger set: {triggers[0]!r}) -> skipping LLM")
            return sql.strip()

    response = llm.invoke(
        PROMPT + "\n\nUser: " + user_query
    )

    sql = response.content.strip()

    # If the LLM flagged this as an ambiguous update (see rule 12
    # in PROMPT above), pass that signal straight through as-is —
    # don't run it through the cleanup/statement-splitting below,
    # which assumes real SQL text.
    if sql.upper() == NEEDS_VALUE_SENTINEL:
        return NEEDS_VALUE_SENTINEL

    sql = sql.replace("```sql", "")
    sql = sql.replace("```", "")
    sql = sql.strip()

    # Defensive: even after the rules above, if the LLM ever
    # returns multiple semicolon-separated statements for some
    # other, un-hardcoded query, keep only the first one rather
    # than letting execute_sql reject the whole response outright.
    statements = [s.strip() for s in sql.split(";") if s.strip()]

    if statements:
        sql = statements[0] + ";"

    return sql