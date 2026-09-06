print("######## CONTEXT AGENT V4 LOADED — MULTI-DOC-COMPARE ########")

from llm import llm


# =====================================================
# DETERMINISTIC OVERRIDE — compound patient existence /
# history questions  (unchanged from before)
# =====================================================

REPORT_OVERRIDE_PHRASES = [
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
    "delete patient",
    "delete bill",
    "remove patient",
    "update patient",
    "with id",
    "add doctor to",
    "assign doctor to",
    "update doctor",
    "update doctor for",
    "change doctor",
    "change doctor for",
    "set doctor",
]

INVENTORY_OVERRIDE_PHRASES = [
    "show inventory",
    "medicine inventory",
    "show medicines",
    "list medicines",
    "all medicines",
    "medicine stock",
    "show stock",
]

DOCUMENT_OVERRIDE_PHRASES = [
    "pdf",
    "prescription",
    "download invoice",
    "get invoice",
    "give invoice",
    "show invoice",
    "invoice pdf",
    "compare doctors",
    "compare doctor",
    "compare dr",
    "doctor comparison",
    "monthly comparison",
    "comparison report",
    "compare this month",
    "compare months",
]

# CHANGED: added phrases for comparing UPLOADED documents/PDFs to
# each other — this is the new "compare like ChatGPT" feature.
# These must be checked in the SAME pass as the other
# DOCUMENT_QA_TRIGGERS below (before DOCUMENT_OVERRIDE_PHRASES),
# because "compare these pdfs" contains the bare word "pdf(s)",
# which would otherwise incorrectly route to the DOCUMENT branch
# (which generates a NEW report) instead of DOCUMENT_QA (which
# reads and compares the uploaded ones).
DOCUMENT_QA_TRIGGERS = [
    "this document",
    "this pdf",
    "the document",
    "the uploaded",
    "uploaded document",
    "uploaded pdf",
    "in this file",
    "this file says",
    "summarize the document",
    "summarize this pdf",
    "what does this pdf",
    "what does this document",
]

# Words used to flexibly detect "compare my uploaded files" style
# requests, WITHOUT requiring one exact phrase. This is the fix for
# queries like "Compare these document" (singular, no "s") not
# matching a fixed phrase list — any sentence that mentions BOTH a
# comparison word AND a document-ish word routes here, regardless
# of singular/plural, word order, or exact phrasing. Deliberately
# checked using "document"/"pdf"/"file" as substrings, so
# "documents", "pdfs", "files" all match too without listing every
# variant separately.
COMPARE_WORDS = ["compare", "comparison", "difference", "different", "versus", " vs "]
DOCUMENT_WORDS = ["document", "pdf", "file"]


def context_agent(user_query):

    query = user_query.lower().strip()

    print("CONTEXT RECEIVED:", user_query)

    if any(phrase in query for phrase in REPORT_OVERRIDE_PHRASES):
        print("[Context Agent] Deterministic override matched -> REPORT")
        return "REPORT"

    if any(phrase in query for phrase in INVENTORY_OVERRIDE_PHRASES):
        print("[Context Agent] Deterministic override matched -> INVENTORY")
        return "INVENTORY"

    if any(phrase in query for phrase in DOCUMENT_QA_TRIGGERS):
        print("[Context Agent] Deterministic override matched -> DOCUMENT_QA")
        return "DOCUMENT_QA"

    # Flexible compare-documents check — catches "compare these
    # document(s)", "difference between these files", "compare my
    # pdfs", etc. regardless of exact wording, since it only needs
    # ONE word from each list rather than an exact full phrase.
    if (
        any(word in query for word in COMPARE_WORDS)
        and any(word in query for word in DOCUMENT_WORDS)
    ):
        print("[Context Agent] Flexible compare-documents match -> DOCUMENT_QA")
        return "DOCUMENT_QA"

    if any(phrase in query for phrase in DOCUMENT_OVERRIDE_PHRASES):
        print("[Context Agent] Deterministic override matched -> DOCUMENT")
        return "DOCUMENT"

    prompt = f"""
You are the Context Classification Agent of a Hospital Medical Billing AI.

Your job is to understand WHAT THE USER WANTS TO DO.

The system has these agents:

PATIENT
BILLING
REPORT
INVENTORY
SALES


==================================================
PATIENT = ONLY PATIENT REGISTRATION
==================================================

Use PATIENT ONLY when the user wants to CREATE / REGISTER / ADD
a new patient.

Examples:

Register patient Rahul
Add Rahul as a patient
Create patient Amit
Register Bhagwat
Add new patient Sujal
Register patient Mihir age 21 male doctor Dr Charu

Hindi/Marathi:

Sujal ko register karo
Naya patient add karo
रुग्ण जोडा
नवीन पेशंट नोंदवा


IMPORTANT:
"Show patient"
"Find patient"
"Check patient"
"Is patient there"
"Patient history"

are NOT PATIENT.


==================================================
BILLING = CREATE A NEW BILL
==================================================

Use BILLING only when the user wants to CREATE/GENERATE
a new bill or invoice.

Examples:

Generate bill
Create bill
Make invoice
Generate bill for Rahul
Create invoice for Amit
Bill banao


IMPORTANT:
"Show bill"
"Previous bill"
"Latest bill"
"Bill history"

are REPORT, not BILLING.


==================================================
REPORT = SEARCH / HISTORY / ANALYSIS
==================================================

Use REPORT when the user wants to READ, SEARCH, CHECK,
ANALYZE or retrieve existing information.

Examples:

Show Sujal
Find Sujal
Check if Sujal is there
Is Sujal registered?
Does Sujal exist?
Show Sujal's history
Show Sujal's bills
What medicines has Sujal taken?
Which doctor treated Sujal?
Check if Sujal is there and what medicines he has taken
Show all patients
Show all bills
Show latest bill
Show previous bill
Hospital dashboard
Revenue report
Count patients
Top selling medicine
Which patient spent the most?
Which patients bought Crocin?
Show total medicine sales
How many medicines were sold today?
Show medicine sales report

VERY IMPORTANT:

"Show sales", "total sales", "how many were sold", "medicine
sales report" are REQUESTS FOR INFORMATION about sales that
already happened — these are REPORT, never SALES. SALES is only
for when the user wants a NEW sale to happen right now.

If a query contains BOTH:

patient existence/search
AND
medicine/bill/history information

the answer is REPORT.

Example:

"Check if Sujal is there and what medicines he has taken"

MUST be:

REPORT


==================================================
INVENTORY = MEDICINE STOCK INFORMATION
==================================================

Use INVENTORY when the user asks about medicine STOCK,
availability, expiry or inventory.

Examples:

Show Crocin stock
How much Crocin is available?
Do we have Crocin?
Show low stock medicines
Which medicines are expired?
Show all medicines
Increase Crocin stock by 20
Decrease Dolo stock by 5


==================================================
SALES = SELL / DISPENSE MEDICINE
==================================================

Use SALES when the user wants to sell or dispense medicine.

Examples:

Sell 2 Crocin
Sell medicine
Give 5 Crocin
Dispense Crocin
Sell 3 Dolo

IMPORTANT:
"Show sales", "total sales", "medicine sales report", "how many
were sold" are REPORT, NOT SALES — those are questions asking
about past sales, not a request to sell anything right now.


==================================================
IMPORTANT DECISION RULES
==================================================

1. REGISTER / ADD / CREATE PATIENT -> PATIENT

2. SEARCH / FIND / CHECK / SHOW PATIENT -> REPORT

3. CREATE / GENERATE BILL -> BILLING

4. SHOW / SEARCH / HISTORY / ANALYZE existing data -> REPORT

5. STOCK / AVAILABILITY / EXPIRY -> INVENTORY

6. SELL / DISPENSE MEDICINE -> SALES

7. If the user asks about a patient's medicines,
   bills, doctor, history or existence -> REPORT.

8. NEVER classify a question containing
   "check if", "is there", "find", "show", "what medicines",
   "history", "which doctor" as PATIENT.

9. Do NOT ask follow-up questions.
   Only classify the request.


==================================================
USER QUERY
==================================================

{user_query}

Return ONLY ONE WORD:

PATIENT
BILLING
REPORT
INVENTORY
SALES
"""

    try:

        response = llm.invoke(prompt)

        answer = response.content.strip().upper()

        answer = answer.replace("`", "")
        answer = answer.split()[0] if answer.split() else "REPORT"

        allowed = [
            "PATIENT",
            "BILLING",
            "REPORT",
            "INVENTORY",
            "SALES",
            "DOCUMENT",
            "DOCUMENT_QA"
        ]

        if answer not in allowed:
            answer = "REPORT"

        return answer

    except Exception as e:

        print("Context Agent Error:", e)

        return "REPORT"