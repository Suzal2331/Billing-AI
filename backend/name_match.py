"""
tools/name_match.py

Corrects near-miss patient name spellings against what's actually
in the database, BEFORE any classification or SQL generation runs.

Why this exists: voice transcription (even good STT) routinely
gets Indian proper names one character off — "Dhananjaya" instead
of "Dhananjay", "Sujan" instead of "Sujal". An exact-match SQL
WHERE clause then finds nothing, even though the intended patient
obviously exists. This isn't a translation problem (normalize_to_
english() already ran by the time this executes) — it's a
spelling-tolerance problem, so it's solved separately, in Python,
against your actual patient list.

difflib (Python stdlib, no extra dependency) is used to find the
closest real patient name to each word in the query. Only words
that look like they could BE a name (alphabetic, length >= 3, not
a known command word) are checked, and only a strong match (ratio
>= threshold) gets substituted — this is deliberately conservative
to avoid "correcting" an unrelated word into a patient's name by
coincidence.
"""

import difflib

from tools.db_tool import connect_db

# Command/domain words that should never be treated as a possible
# patient name, even if they happen to be somewhat similar to one
# in the DB. Without this, a query like "Show all patients" could
# get "all" or "patients" incorrectly "corrected" into a real
# patient's name if one happened to be spelled similarly.
_STOPWORDS = {
    "show", "add", "update", "delete", "remove", "register", "change",
    "set", "patient", "patients", "doctor", "doctors", "medicine",
    "medicines", "bill", "bills", "stock", "inventory", "the", "is",
    "are", "there", "what", "which", "who", "check", "find", "search",
    "history", "details", "latest", "sell", "dispense", "give",
    "increase", "decrease", "and", "his", "her", "he", "she", "has",
    "have", "taken", "purchased", "bought", "gender", "age", "male",
    "female", "other", "all", "list", "generate", "invoice", "report",
    "dashboard", "hospital", "low", "available", "expired", "revenue",
    "sales", "total", "count", "today", "cancel", "stop", "exit",
    "quit", "yes", "please", "for", "with", "does", "exist",
    "registered", "purchase",
}


def get_all_patient_names():
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("SELECT name FROM patients")
    names = [r[0] for r in cur.fetchall() if r[0]]
    conn.close()
    return names


def fuzzy_correct_patient_names(user_query, threshold=0.72):
    """
    Scans user_query word by word. Any word that isn't an exact
    (case-insensitive) match to a real patient name, isn't a known
    command word, and is close enough (difflib ratio >= threshold)
    to exactly one real patient name gets replaced with that
    patient's correctly-spelled name. Everything else in the
    sentence is left untouched.

    Returns the query unchanged if nothing needed correcting, or if
    the patients table can't be reached for any reason (fails open,
    never blocks the request).
    """
    try:
        real_names = get_all_patient_names()
    except Exception as e:
        print(f"[Fuzzy Name Match] Could not load patient names — {e}")
        return user_query

    if not real_names:
        return user_query

    lower_to_real = {n.lower(): n for n in real_names}

    words = user_query.split()
    corrected_words = []
    changed = False

    for word in words:
        # Keep any trailing punctuation ("Sujal?" -> "Sujal" + "?")
        # so correction doesn't silently eat punctuation.
        cleaned = word.strip(",.?!\"'")
        trailing = word[len(cleaned):]
        lc = cleaned.lower()

        if not cleaned.isalpha() or len(cleaned) < 3 or lc in _STOPWORDS:
            corrected_words.append(word)
            continue

        if lc in lower_to_real:
            # Already spelled exactly right — nothing to do.
            corrected_words.append(word)
            continue

        match = difflib.get_close_matches(
            lc, lower_to_real.keys(), n=1, cutoff=threshold
        )

        if match:
            real_name = lower_to_real[match[0]]
            corrected_words.append(real_name + trailing)
            changed = True
        else:
            corrected_words.append(word)

    if not changed:
        return user_query

    corrected_query = " ".join(corrected_words)
    print(f"[Fuzzy Name Match] {user_query!r} -> {corrected_query!r}")
    return corrected_query