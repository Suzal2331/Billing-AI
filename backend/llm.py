import os
import re
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

# CHANGED: llama-3.3-70b-versatile was deprecated by Groq on
# June 17, 2026 and fully shut down shortly after — this is what
# caused "model_not_found" / 404 errors across EVERY agent (this
# file is imported by context classification, SQL generation,
# language translation, everything). Groq's own recommended
# replacement for this model is openai/gpt-oss-120b. Confirmed
# directly against Groq's deprecations page, not guessed.
#
# If this ever happens again with a different model in the future,
# check https://console.groq.com/docs/deprecations first — that
# page is the authoritative source, not any assumption in this
# comment.
MODEL_NAME = "openai/gpt-oss-20b"

# CHANGED: was a hardcoded key directly in this file (visible to
# anyone who sees this source, including every AI assistant this
# project gets pasted into). Reads from .env instead, matching the
# GROQ_API_KEY that's already correctly present there — app.py
# already does this same load_dotenv() pattern for Sarvam's key.
api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    print("⚠️  GROQ_API_KEY not found in .env — LLM calls will fail until this is set.")

_raw_llm = ChatGroq(
    model=MODEL_NAME,
    temperature=0,
    api_key=api_key,
    # Reasoning models like qwen3.6 spend real output tokens on
    # their <think> trace BEFORE producing the actual answer — a
    # low token cap risks the response getting cut off mid-thought,
    # before any real SQL/JSON/classification answer ever gets
    # generated at all. Raised well above whatever the client
    # default is to make that far less likely.
    max_tokens=4096,
)

# =====================================================
# THINK-TAG STRIPPING WRAPPER
# =====================================================
# qwen/qwen3.6-27b is a REASONING model — unlike the previous
# model, its raw response can include the model's chain-of-thought
# wrapped in <think>...</think> tags, ahead of (or around) the
# actual answer. Every single call site across this whole project
# (sql_agent's SQL generation, context_agent's classification,
# orchestrator's patient/billing/sales JSON extraction and
# normalize_to_english translation, app.py's reply translation)
# does the same thing: response = llm.invoke(prompt) then uses
# response.content.strip() directly. None of them expect literal
# "<think>...</think>" text mixed into that content — this is
# exactly what caused "near '<': syntax error" when the SQL
# generator's raw reasoning got treated as if it were SQL.
#
# Rather than pasting the same strip() logic into 6+ separate
# files (and inevitably missing one), this wraps the LLM client
# ONCE, here, so every current AND future llm.invoke() call
# anywhere in the app is automatically protected.

_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class _CleanResponse:
    """Minimal stand-in for langchain's response object — every
    call site in this project only ever reads .content, so that's
    the only attribute this needs to provide."""
    __slots__ = ("content",)

    def __init__(self, content):
        self.content = content


class _ThinkStrippingLLM:
    def __init__(self, real_llm):
        self._real_llm = real_llm

    def invoke(self, *args, **kwargs):
        response = self._real_llm.invoke(*args, **kwargs)
        raw = response.content

        cleaned = _THINK_TAG_RE.sub("", raw).strip()

        # Fallback for an UNTERMINATED <think> block — the response
        # got cut off mid-reasoning (hit the token limit) before the
        # model ever reached a real answer, so there's no matching
        # </think> for the regex above to find, and the raw
        # reasoning text would otherwise leak straight through
        # untouched. Strip everything from the opening tag onward
        # as a last resort; what's left will likely be empty, which
        # correctly surfaces as a normal "no valid response" failure
        # downstream (e.g. execute_sql erroring on empty SQL)
        # instead of nonsense reasoning text being treated as real
        # output.
        if "<think>" in cleaned.lower():
            print("[LLM] Warning: unterminated <think> block — response likely got cut off before a real answer. Consider raising max_tokens further if this keeps happening.")
            cleaned = re.split(r"<think>", cleaned, flags=re.IGNORECASE)[0].strip()

        return _CleanResponse(cleaned)


llm = _ThinkStrippingLLM(_raw_llm)

print(f"LLM Loaded Successfully — model: {MODEL_NAME} (think-tag stripping active)")