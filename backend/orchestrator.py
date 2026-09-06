print("######## ORCHESTRATOR LOADED — STRUCTURED-CARDS-V3 — DOWNLOADABLE-COMPARISONS ########")

import json
import urllib.parse

from llm import llm

from agents.context_agent import context_agent
from agents.patient_agent import patient_agent
from agents.billing_agent import billing_agent
from agents.inventory_agent import inventory_agent
from agents.report_agent import report_agent
from agents.sales_agent import sales_agent
from agents.sql_agent import generate_sql, NEEDS_VALUE_SENTINEL

from tools.sql_tool import execute_sql
from tools.response import card
from tools.name_match import fuzzy_correct_patient_names
from tools.db_tool import search_patient

from memory import (
    set_last_patient,
    get_last_patient,
    set_last_doctor,
    get_last_doctor,
    set_last_medicine,
    get_last_medicine,
    set_last_bill,
    get_last_bill
)

from conversation_state import (
    start_task,
    save,
    get,
    clear
)


def clean_json(text):
    text = text.replace("```json", "")
    text = text.replace("```", "")
    return text.strip()


# =====================================================
# LANGUAGE NORMALIZATION  (unchanged from before)
# =====================================================

def normalize_to_english(user_query):
    if all(ord(ch) < 128 for ch in user_query):
        return user_query

    prompt = f"""
Translate the following text into English.

It may be in Hindi, Marathi, or a mix of an Indian language and
English (code-mixed). Keep patient names and medicine names as
close to their original pronunciation as possible, transliterated
into Latin script — do not translate names, only transliterate
them. Keep all numbers exactly as written.

The text comes from speech-to-text transcription, which sometimes
mishears a common English command word and writes it out
phonetically in Devanagari script instead of recognizing it as
English — for example "शौ" is very likely a mishearing of the
English word "Show", not an actual Hindi/Marathi word. If a short
word at the start of the sentence doesn't make sense as an actual
Hindi/Marathi/name word but sounds like a common English command
("show", "add", "update", "delete", "check", "find"), assume it IS
that English word and use it, rather than transliterating the
mishearing literally.

Return ONLY the translated English text, nothing else — no
explanation, no quotes around it.

Text:
{user_query}
"""

    try:
        response = llm.invoke(prompt)
        translated = response.content.strip()
        print(f"[Normalize] {user_query!r} -> {translated!r}")
        return translated
    except Exception as e:
        print(f"[Normalize] Failed, using original text — {e}")
        return user_query


# =====================================================
# GENDER GUESS-AND-CONFIRM  (unchanged from before)
# =====================================================

def guess_gender_from_name(name):

    prompt = f"""
You are guessing the likely gender associated with a first name.

Reply with ONLY ONE WORD: Male, Female, or Other.
If you are unsure, or the name is unisex, or gender cannot be
reasonably guessed from it, reply Other.

Name: {name}
"""

    try:
        response = llm.invoke(prompt)
        guess = response.content.strip().split()[0].strip(".,!").title()

        if guess not in ["Male", "Female", "Other"]:
            return "Other"

        return guess

    except Exception:
        return "Other"


def handle_gender_step(data, user_query):
    guess = data.get("_gender_guess")

    if guess is None:
        guess = guess_gender_from_name(data["name"])
        save("_gender_guess", guess)

        return (
            f"👤 I'm guessing **{guess}** for {data['name']} — "
            f"is that right? (yes / or tell me Male, Female, or Other)"
        )

    cleaned = user_query.strip().lower()

    affirmative = {
        "yes", "y", "yeah", "yep", "yup",
        "correct", "right", "confirm", "confirmed"
    }

    gender_map = {
        "male": "Male", "m": "Male",
        "female": "Female", "f": "Female",
        "other": "Other", "o": "Other",
    }

    if cleaned in affirmative:
        save("gender", guess)
        return None

    if cleaned in gender_map:
        save("gender", gender_map[cleaned])
        return None

    return (
        f"👤 Please answer yes, or tell me Male, Female, or Other "
        f"for {data['name']}."
    )


# =====================================================
# PRONOUN RESOLUTION FOR "it" / "this" / "that"  (unchanged)
# =====================================================

PRONOUN_WORDS = ["it", "this", "that"]

DOCUMENT_SPECIFIC_HINTS = [
    "month", "doctor", "dr ", "compare", "comparison",
    "patients", "sales", "invoice", "prescription",
]


def try_resolve_pronoun_to_patient_report(user_query):
    """
    Returns a (url, label) tuple if this query is a pronoun-only
    request that can be confidently resolved to the last-discussed
    patient's report, or None if it should fall through to normal
    DOCUMENT-branch handling.
    """
    lower_query = user_query.lower().strip()
    words = lower_query.replace("?", "").split()

    has_pronoun = any(w in PRONOUN_WORDS for w in words)
    if not has_pronoun:
        return None

    if any(hint in lower_query for hint in DOCUMENT_SPECIFIC_HINTS):
        return None

    patient = get_last_patient()
    if not patient:
        return None

    url = f"/api/report/pdf?type=patient&name={urllib.parse.quote(patient)}"
    label = f"Download {patient}'s Patient Report (PDF)"
    return url, label


# =====================================================
# NEW — SHARED UPLOADED-DOCUMENT COMPARISON BUILDER
# =====================================================
# Used by BOTH the chat answer (DOCUMENT_QA branch below) and the
# PDF download route (/api/documents/compare-uploaded in app.py),
# so the on-screen comparison and the downloaded PDF always show
# the exact same content instead of drifting apart from two
# separate LLM calls with slightly different prompts.
#
# Returns a real structured table (narrative + columns + rows)
# instead of freeform prose, which is what makes both the chat card
# and the PDF render an actual table instead of raw markdown pipes.

def build_uploaded_comparison(all_docs, user_query):
    """
    all_docs: list of {"filename", "text", "pages"} dicts, as
    returned by tools.document_store.get_all_uploaded_documents().

    Returns (narrative, columns, rows):
      narrative -> short plain-English summary string
      columns   -> ["Aspect", <filename 1>, <filename 2>, ...]
      rows      -> list of [aspect_name, value_for_doc_1, value_for_doc_2, ...]
    """
    docs_block = ""
    for i, doc in enumerate(all_docs, start=1):
        docs_block += (
            f"\n\n===== DOCUMENT {i}: {doc['filename']} "
            f"({doc['pages']} pages) =====\n{doc['text']}"
        )

    filenames = [d["filename"] for d in all_docs]

    prompt = f"""
You are comparing multiple uploaded documents. Use ONLY the
information in the documents below — do not guess or invent
anything not present in them.

Return ONLY valid JSON in this exact shape, nothing else:

{{
  "narrative": "2-4 sentence plain-English summary of the key similarities and differences",
  "rows": [
    {{"aspect": "Recipient", "values": ["value from doc 1", "value from doc 2"]}},
    {{"aspect": "Another aspect", "values": ["...", "..."]}}
  ]
}}

Each "values" array must have exactly {len(all_docs)} entries, in
the same order as the documents listed below. Choose whichever
aspects actually matter for comparing THESE specific documents —
do not force a fixed generic list. If something can't be
determined for a given document, use "Not specified" for that
value rather than guessing.
{docs_block}

User's question:
{user_query}
"""

    response = llm.invoke(prompt)

    try:
        data = json.loads(clean_json(response.content))
        narrative = (data.get("narrative") or "").strip()
        rows = [
            [r.get("aspect", "")] + list(r.get("values", []))
            for r in data.get("rows", [])
        ]
        columns = ["Aspect"] + filenames
        return narrative, columns, rows
    except Exception as e:
        print("[build_uploaded_comparison] JSON parse failed, falling back to plain text —", e)
        # Fallback: no structured table, just the raw model answer
        # as the narrative, with an empty table.
        return response.content.strip(), ["Aspect"] + filenames, []


def orchestrator(user_query):

    user_query = normalize_to_english(user_query)
    user_query = fuzzy_correct_patient_names(user_query)

    # ===============================
    # CONTEXT
    # ===============================

    state = get()
    task = state.get("task", "")

    if task and user_query.strip().lower() in [
        "cancel", "stop", "exit", "nevermind", "never mind", "quit"
    ]:
        clear()
        return card("❌ Cancelled. What would you like to do instead?")

    if task:
        intent = task.upper()
    else:
        intent = context_agent(user_query)

        if not intent:
            intent = "REPORT"
        else:
            intent = intent.upper()

    print(f"\n[Context Agent] -> {intent}")

    # =====================================
    # PATIENT AGENT  (unchanged from before)
    # =====================================

    if intent == "PATIENT":

        state = get()

        if state["task"] == "PATIENT":

            data = state["data"]

            if "name" not in data:
                save("name", user_query.strip())

            elif "age" not in data:
                cleaned = user_query.strip()
                if cleaned.isdigit():
                    save("age", int(cleaned))
                else:
                    return card(f"👤 That doesn't look like a number. What is {data['name']}'s age?")

            elif "gender" not in data:
                question = handle_gender_step(data, user_query)
                if question:
                    return card(question)

            elif "doctor" not in data:
                save("doctor", user_query.strip())

            data = get()["data"]

            if "name" not in data:
                return card("👤 What is the patient's name?")

            if "age" not in data:
                return card(f"👤 What is {data['name']}'s age?")

            if "gender" not in data:
                question = handle_gender_step(data, user_query)
                if question:
                    return card(question)

            if "doctor" not in data:
                return card(f"👨‍⚕ Which doctor is treating {data['name']}?")

            result = patient_agent("register", data)

            set_last_patient(data["name"])

            clear()

            return result

        lower_query = user_query.lower()

        if any(word in lower_query for word in [
            "show", "search", "find", "list"
        ]):

            sql = generate_sql(user_query)
            print("\nGenerated SQL")
            print(sql)

            if sql == NEEDS_VALUE_SENTINEL:
                return card(
                    "❓ You didn't say what the new value should be. "
                    "Please repeat with the new value included — e.g. "
                    "\"Update Dhananjay's doctor to Dr Mehta\"."
                )

            result = execute_sql(sql)

            return report_agent(
                "sql_report",
                {"query": user_query, "result": result}
            )

        prompt = f"""
You are extracting patient details.

Return ONLY valid JSON.

Example

User:
Register Rahul age 25 male doctor Dr Mehta

Output

{{
"name":"Rahul",
"age":25,
"gender":"Male",
"doctor":"Dr Mehta"
}}

User:
{user_query}
"""

        response = llm.invoke(prompt)
        data = json.loads(clean_json(response.content))

        data.setdefault("name", "")
        data.setdefault("age", "")
        data.setdefault("gender", "")
        data.setdefault("doctor", "")

        clear()
        start_task("PATIENT")

        if data["name"]:
            existing = search_patient(data["name"].strip())

            if existing is not None:
                clear()
                return card(f"""
============================================================
               PATIENT ALREADY EXISTS
============================================================

👤 {existing[1]} is already registered (Patient ID #{existing[0]}).

If you meant to change something about them, try phrasing it
as an update instead, e.g.:
  "Update {existing[1]}'s doctor to Dr Sharma"
  "Change {existing[1]}'s age to 30"

============================================================
""")

            save("name", data["name"])

        if data.get("age") not in (None, ""):
            save("age", data["age"])

        if data["gender"]:
            save("gender", data["gender"])

        if data["doctor"]:
            save("doctor", data["doctor"])

        conversation = get()["data"]

        if "name" not in conversation:
            return card("👤 What is the patient's name?")

        if "age" not in conversation:
            return card(f"👤 What is {conversation['name']}'s age?")

        if "gender" not in conversation:
            question = handle_gender_step(conversation, user_query)
            if question:
                return card(question)

        if "doctor" not in conversation:
            return card(f"👨‍⚕ Which doctor is treating {conversation['name']}?")

        result = patient_agent("register", conversation)

        set_last_patient(conversation["name"])

        clear()

        return result

    # =====================================
    # BILLING AGENT  (unchanged from before)
    # =====================================

    elif intent == "BILLING":

        lower_query = user_query.lower()

        if any(text in lower_query for text in [
            "show bill", "show his bill", "show her bill",
            "print bill", "display bill", "latest bill", "previous bill"
        ]):

            patient = get_last_patient()

            if patient:
                return report_agent("get_bill", {"patient_name": patient})

            return card("❌ No previous patient found.")

        prompt = f"""
You are extracting billing details.

Return ONLY valid JSON.

Example

User:
Generate bill consultation 500 medicine 1200 lab 800

Output

{{
"patient_name":"",
"consultation":500,
"medicine":1200,
"lab":800
}}

User:
{user_query}
"""

        response = llm.invoke(prompt)
        data = json.loads(clean_json(response.content))

        data.setdefault("patient_name", "")
        data.setdefault("consultation", 0)
        data.setdefault("medicine", 0)
        data.setdefault("lab", 0)

        if data["patient_name"] == "":
            patient = get_last_patient()
            if patient:
                data["patient_name"] = patient

        if not data["patient_name"]:
            return card("🧾 Who is this bill for? Please include the patient's name.")

        result = billing_agent("create_bill", data)
        set_last_bill(data)

        return result

    # =====================================
    # INVENTORY AGENT  (unchanged from before)
    # =====================================

    elif intent == "INVENTORY":

        medicine_name = None

        ignore_words = [
            "show", "stock", "medicine", "medicines", "inventory",
            "low", "check", "display", "list", "all", "do", "we",
            "have", "of", "the"
        ]

        for word in user_query.split():
            clean_word = word.strip(",.?!").lower()
            if clean_word not in ignore_words:
                medicine_name = word
                break

        if medicine_name:
            set_last_medicine(medicine_name)

        return inventory_agent(user_query)

    # =====================================
    # SALES AGENT  (unchanged from before)
    # =====================================

    elif intent == "SALES":

        prompt = f"""
You are extracting medicine sale details.

Return ONLY valid JSON.

Example

User:
Sold 5 Crocin to Rahul

Output

{{
"patient_name":"Rahul",
"medicine_name":"Crocin",
"quantity":5
}}

User:
Sell 2 Dolo

Output

{{
"patient_name":"",
"medicine_name":"Dolo",
"quantity":2
}}

User:
{user_query}
"""

        response = llm.invoke(prompt)
        data = json.loads(clean_json(response.content))

        data.setdefault("patient_name", "")
        data.setdefault("medicine_name", "")
        data.setdefault("quantity", 1)

        if data["medicine_name"] in ("", None):
            medicine = get_last_medicine()
            if medicine:
                data["medicine_name"] = medicine

        if not data["patient_name"]:
            patient = get_last_patient()
            if patient:
                data["patient_name"] = patient

        return sales_agent(data)

    # =====================================
    # DOCUMENT AGENT — PDF generation & comparison  (unchanged)
    # =====================================

    elif intent == "DOCUMENT":

        resolved = try_resolve_pronoun_to_patient_report(user_query)

        if resolved:
            url, label = resolved
            full_url = f"http://localhost:5000{url}"
            text = f"📄 Your document is ready.\n\n{label}\n{full_url}"
            return card(text, {
                "kind": "document",
                "title": "Document Ready",
                "document": {"url": url, "label": label},
            })

        prompt = f"""
You are extracting what PDF document or comparison the user wants.

Return ONLY valid JSON, one of these exact shapes:

Single patient's prescription (medicines dispensed):
{{"action":"prescription","name":"Sujal"}}

Single patient's bill/invoice:
{{"action":"invoice","name":"Sujal"}}

Single patient's full report:
{{"action":"patient_report","name":"Sujal"}}

Full patient list:
{{"action":"patients"}}

Medicine sales report:
{{"action":"sales"}}

Monthly revenue comparison — default for a vague "comparison
report" / "monthly comparison" request with no other detail:
{{"action":"compare_months"}}

Comparing two named doctors:
{{"action":"compare_doctors","a":"Dr Charu","b":"Dr Shivam"}}

If the query uses a pronoun ("it", "this", "that") with NOTHING
else specific mentioned, and you cannot tell what it refers to,
return:
{{"action":"unclear"}}

User:
{user_query}
"""

        response = llm.invoke(prompt)

        try:
            data = json.loads(clean_json(response.content))
        except Exception:
            data = {"action": "unclear"}

        action = data.get("action", "")

        if action == "unclear":
            return card(
                "📄 I'm not sure what \"it\" refers to here. Could you say "
                "the patient's name, or what you'd like the PDF of?"
            )

        if action == "prescription":
            name = data.get("name", "").strip()
            if not name:
                return card("📄 Whose prescription would you like? Please include a patient name.")
            url = f"/api/report/pdf?type=prescription&name={urllib.parse.quote(name)}"
            label = f"Download {name}'s Prescription (PDF)"

        elif action == "invoice":
            name = data.get("name", "").strip()
            if not name:
                return card("📄 Whose invoice would you like? Please include a patient name.")
            url = f"/api/report/pdf?type=invoice&name={urllib.parse.quote(name)}"
            label = f"Download {name}'s Invoice (PDF)"

        elif action == "patient_report":
            name = data.get("name", "").strip()
            if not name:
                return card("📄 Whose report would you like? Please include a patient name.")
            url = f"/api/report/pdf?type=patient&name={urllib.parse.quote(name)}"
            label = f"Download {name}'s Patient Report (PDF)"

        elif action == "patients":
            url = "/api/report/pdf?type=patients"
            label = "Download Patient List (PDF)"

        elif action == "sales":
            url = "/api/report/pdf?type=sales"
            label = "Download Medicine Sales Report (PDF)"

        elif action == "compare_doctors":
            a, b = data.get("a", "").strip(), data.get("b", "").strip()
            if not a or not b:
                return card("📄 Please name both doctors to compare, e.g. \"Compare Dr Charu and Dr Shivam\".")
            url = f"/api/documents/compare?type=doctors&a={urllib.parse.quote(a)}&b={urllib.parse.quote(b)}"
            label = f"Download {a} vs {b} Comparison (PDF)"

        else:  # compare_months
            url = "/api/report/pdf?type=comparison"
            label = "Download Monthly Comparison Report (PDF)"

        full_url = f"http://localhost:5000{url}"
        text = f"📄 Your document is ready.\n\n{label}\n{full_url}"

        return card(text, {
            "kind": "document",
            "title": "Document Ready",
            "document": {"url": url, "label": label},
        })

    # =====================================
    # DOCUMENT Q&A — answering questions about uploaded PDFs
    # =====================================
    # CHANGED: comparisons now return a real structured 'comparison'
    # card (real table, not markdown pipes) AND a downloadUrl so the
    # same comparison can be downloaded as a professionally
    # formatted PDF via /api/documents/compare-uploaded.

    elif intent == "DOCUMENT_QA":

        from tools.document_store import get_all_uploaded_documents

        all_docs = get_all_uploaded_documents()

        if not all_docs:
            return card(
                "📄 No document has been uploaded yet. Use the attach button "
                "next to the mic to upload one or more PDFs first, then ask "
                "about them."
            )

        lower_query = user_query.lower()

        wants_comparison = any(word in lower_query for word in [
            "compare", "comparison", "difference", "different",
            "similar", "similarities", "versus", " vs "
        ])

        if wants_comparison and len(all_docs) < 2:
            return card(
                f"📄 You've only uploaded one document so far "
                f"({all_docs[0]['filename']}). Upload at least one more PDF "
                f"to compare them."
            )

        if wants_comparison:
            narrative, columns, rows = build_uploaded_comparison(all_docs, user_query)
            names = ", ".join(d["filename"] for d in all_docs)

            download_url = (
                f"/api/documents/compare-uploaded?q={urllib.parse.quote(user_query)}"
            )

            return card(f"📄 (Comparing: {names})\n\n{narrative}", {
                "kind": "comparison",
                "title": "Document Comparison",
                "comparison": {
                    "subtitle": names,
                    "narrative": narrative,
                    "columns": columns,
                    "rows": rows,
                },
                "downloadUrl": download_url,
                "downloadLabel": "Download Comparison as PDF",
            })

        # Non-comparison question — behave like before, answering
        # from the MOST RECENTLY uploaded document only, since that's
        # almost always what "this document" means in a single-doc
        # question.
        latest = all_docs[-1]

        prompt = f"""
You are answering a question about a document the user uploaded.
Answer using ONLY the information in the document text below. If
the answer genuinely isn't in the document, say so clearly rather
than guessing or making something up.

Document filename: {latest['filename']}

Document content:
{latest['text']}

User's question:
{user_query}
"""

        response = llm.invoke(prompt)
        answer = response.content.strip()

        return card(f"📄 (From {latest['filename']})\n\n{answer}")

    # =====================================
    # REPORT / SQL AGENT (CRUD)  (unchanged from before)
    # =====================================

    elif intent == "REPORT":

        sql = generate_sql(user_query)
        print("\nGenerated SQL")
        print(sql)

        if sql == NEEDS_VALUE_SENTINEL:
            return card(
                "❓ You didn't say what the new value should be. "
                "Please repeat with the new value included — e.g. "
                "\"Update Dhananjay's doctor to Dr Mehta\"."
            )

        result = execute_sql(sql)

        if "error" in result:
            return card(f"❌ {result['error']}")

        if result.get("type") == "INSERT":
            return card(f"✅ {result['message']}")

        if result.get("type") == "UPDATE":
            return card(f"✅ {result['message']}")

        if result.get("type") == "DELETE":
            return card(f"✅ {result['message']}")

        return report_agent(
            "sql_report",
            {"query": user_query, "result": result}
        )

    # =====================================
    # FALLBACK  (unchanged from before)
    # =====================================

    else:

        sql = generate_sql(user_query)
        print("\nGenerated SQL")
        print(sql)

        if sql == NEEDS_VALUE_SENTINEL:
            return card(
                "❓ You didn't say what the new value should be. "
                "Please repeat with the new value included — e.g. "
                "\"Update Dhananjay's doctor to Dr Mehta\"."
            )

        result = execute_sql(sql)

        if "error" in result:
            return card(f"❌ {result['error']}")

        if result.get("type") in ["INSERT", "UPDATE", "DELETE"]:
            return card(f"✅ {result['message']}")

        return report_agent(
            "sql_report",
            {"query": user_query, "result": result}
        )