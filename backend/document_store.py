"""
tools/document_store.py

Stores every uploaded document's extracted text — not just the
latest one — so multi-document Q&A and comparison can reference all
of them at once.

set_uploaded_document() keeps its original name and signature
(filename, text, pages) on purpose: app.py's upload route calls it
once per uploaded file without needing to know or care that storage
changed from "one slot" to "a list" underneath. Calling it
repeatedly now correctly ADDS each document instead of overwriting
the previous one.
"""

_documents = []


def set_uploaded_document(filename, text, pages):
    """Adds one uploaded document to the store (does not replace
    previous uploads)."""
    _documents.append({
        "filename": filename,
        "text": text,
        "pages": pages,
    })


def get_all_uploaded_documents():
    """Returns a list of {"filename", "text", "pages"} dicts, in the
    order they were uploaded. Empty list if nothing uploaded yet."""
    return list(_documents)


def get_uploaded_document():
    """Back-compat single-document accessor — returns the MOST
    RECENTLY uploaded document as (filename, text, pages), or
    (None, None, None) if nothing has been uploaded yet. Prefer
    get_all_uploaded_documents() for anything comparison-related."""
    if not _documents:
        return None, None, None
    latest = _documents[-1]
    return latest["filename"], latest["text"], latest["pages"]


def clear_uploaded_documents():
    _documents.clear()


# Back-compat alias — earlier code referred to this as
# clear_uploaded_document() (singular).
clear_uploaded_document = clear_uploaded_documents