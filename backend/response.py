"""
tools/response.py

Shared return-shape helper for every agent function.

Every agent (patient_agent, billing_agent, sales_agent,
inventory_agent, report_agent) and orchestrator() itself now
return a dict of the form:

    {
        "text": "...same pre-formatted string as always...",
        "structured": {...} | None
    }

"text" is unchanged from before this upgrade — main.py just prints
it, exactly like it always printed the old bare string.

"structured" is new: when present, it's a dict matching the
frontend's ResponseCard shape (see src/lib/types.ts) — e.g.
{"kind": "patient_registered", "title": "...", "patient": {...}}.
When there's no rich card built for a given reply yet, structured
is None, and the frontend falls back to rendering "text" as a
plain message. This is what lets the upgrade roll out one card
type at a time without breaking anything that isn't converted yet.
"""


def card(text, structured=None):
    return {"text": text, "structured": structured}