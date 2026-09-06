"""
app.py

Minimal Flask API bridging the React chat UI to the existing
Python orchestrator. This is intentionally thin — it does not
change any agent logic, it just exposes orchestrator() over HTTP.

Setup (one-time):
    pip install flask flask-cors

Run:
    python app.py

The React dev server (usually http://localhost:5173) should point
its API calls at http://localhost:5000 — see the updated api.ts.
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import io
import os
import traceback

from orchestrator import orchestrator, build_uploaded_comparison
from tools.sql_tool import execute_sql
from llm import llm

app = Flask(__name__)

CORS(app)


# =====================================================
# REPLY TRANSLATION  (unchanged from before)
# =====================================================

def translate_reply(text, target_language):
    if not target_language or target_language.lower().startswith("en"):
        return text

    language_names = {
        "hi-in": "Hindi", "mr-in": "Marathi", "bn-in": "Bengali",
        "kn-in": "Kannada", "ml-in": "Malayalam", "od-in": "Odia",
        "pa-in": "Punjabi", "ta-in": "Tamil", "te-in": "Telugu",
        "gu-in": "Gujarati", "en-in": "English",
    }
    language_label = language_names.get(target_language.lower(), target_language)

    prompt = f"""
Translate the following text into {language_label}.

Keep all numbers, patient names, medicine names, doctor names, and
formatting symbols (₹, emoji, the ==== / ---- box-drawing
characters) EXACTLY as they are — only translate the actual
English sentences/words around them.

Return ONLY the translated text, nothing else.

Text:
{text}
"""

    try:
        response = llm.invoke(prompt)
        return response.content.strip()
    except Exception as e:
        print(f"[Reply Translator] Failed, returning English — {e}")
        return text


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    target_language = data.get("language")

    if not message:
        return jsonify({"reply": "Please type a message."}), 400

    try:
        result = orchestrator(message)
        reply_text = result["text"]
        structured = result.get("structured")
    except Exception as e:
        print("Orchestrator error:")
        traceback.print_exc()
        reply_text = f"❌ Something went wrong: {e}"
        structured = None

    if target_language:
        reply_text = translate_reply(reply_text, target_language)

    return jsonify({
        "reply": reply_text,
        "card": structured,
        "language": target_language or "en",
    })


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# =====================================================
# SPEECH-TO-TEXT — SARVAM SAARAS V3  (unchanged from before)
# =====================================================

from sarvamai import SarvamAI
from dotenv import load_dotenv

load_dotenv()

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

if not SARVAM_API_KEY:
    print("⚠️  SARVAM_API_KEY not found in .env — /api/transcribe will fail until this is set.")
    sarvam_client = None
else:
    sarvam_client = SarvamAI(api_subscription_key=SARVAM_API_KEY)
    print("✅ Sarvam AI loaded successfully")


@app.route("/api/transcribe", methods=["POST"])
def transcribe():

    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400

    if sarvam_client is None:
        return jsonify({"error": "SARVAM_API_KEY is missing — check your .env file"}), 500

    audio_file = request.files["audio"]

    try:
        response = sarvam_client.speech_to_text.transcribe(
            file=(audio_file.filename or "audio.webm", audio_file.read()),
            model="saaras:v3",
            mode="codemix",
            language_code="unknown",
        )

        transcript = getattr(response, "transcript", "")

        detected_language = (
            getattr(response, "language_code", None)
            or getattr(response, "language", None)
        )

        print("🎤 Speech received:", transcript)
        print("🌐 Detected language:", detected_language)
        if not detected_language:
            print("   (Could not find a language field — full response for reference:)")
            print("  ", response)

        return jsonify({"text": transcript, "language": detected_language or "en-IN"})

    except Exception as e:
        print("❌ Sarvam transcription error:", e)
        return jsonify({"error": str(e)}), 500


# =====================================================
# TEXT-TO-SPEECH — SARVAM BULBUL V3  (unchanged from before)
# =====================================================

_TTS_SUPPORTED_LANGUAGES = {
    "hi-in", "bn-in", "kn-in", "ml-in", "mr-in", "od-in",
    "pa-in", "ta-in", "te-in", "gu-in", "en-in",
}


@app.route("/api/speak", methods=["POST"])
def speak():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    language = (data.get("language") or "en-IN").strip()

    if not text:
        return jsonify({"error": "No text provided"}), 400

    if sarvam_client is None:
        return jsonify({"error": "SARVAM_API_KEY is missing — check your .env file"}), 500

    target_language_code = language if language.lower() in _TTS_SUPPORTED_LANGUAGES else "en-IN"

    if len(text) > 2500:
        text = text[:2500]

    try:
        audio = sarvam_client.text_to_speech.convert(
            text=text,
            language_code=target_language_code,
            model="bulbul:v3",
            speaker="anand",
        )

        audio_data = audio.audios[0]

        if isinstance(audio_data, str):
            import base64
            audio_bytes = base64.b64decode(audio_data)
        else:
            audio_bytes = audio_data

        return send_file(
            io.BytesIO(audio_bytes),
            mimetype="audio/wav",
            as_attachment=False,
        )

    except Exception as e:
        print("❌ Sarvam TTS error:", e)
        return jsonify({"error": str(e)}), 500


# =====================================================
# PDF REPORTS — powered by the Document Engine (tools/documents.py)
# =====================================================

from tools.documents import generate_document, compare_documents, render_document

@app.route("/api/report/pdf", methods=["GET"])
def report_pdf():
    report_type = request.args.get("type", "patients")
    name = request.args.get("name", "").strip()

    if report_type == "comparison":
        pdf, error = compare_documents("months", None, None)
        if error:
            return jsonify({"error": error}), 400
        return send_file(pdf, mimetype="application/pdf", as_attachment=True, download_name="monthly_comparison_report.pdf")

    params = {"name": name}
    pdf, error = generate_document(report_type, params)

    if error:
        status = 404 if "No data found" in error or "No patient" in error else 400
        return jsonify({"error": error}), status

    filename = f"{report_type}_{name or 'report'}.pdf".replace(" ", "_")
    return send_file(pdf, mimetype="application/pdf", as_attachment=True, download_name=filename)


@app.route("/api/documents/compare", methods=["GET"])
def documents_compare():
    compare_type = request.args.get("type", "")
    a = request.args.get("a", "").strip()
    b = request.args.get("b", "").strip()

    pdf, error = compare_documents(compare_type, a or None, b or None)

    if error:
        return jsonify({"error": error}), 400

    return send_file(pdf, mimetype="application/pdf", as_attachment=True, download_name=f"{compare_type}_comparison.pdf")


# =====================================================
# NEW — download the uploaded-document comparison as a PDF
# =====================================================
# Reuses build_uploaded_comparison() from orchestrator.py so this
# PDF always matches whatever the chat just showed on screen for
# the same comparison, and reuses render_document() so it gets the
# same letterhead/branding/page numbers as every other PDF in the
# app.

from tools.document_store import get_all_uploaded_documents as _get_all_uploaded_documents

@app.route("/api/documents/compare-uploaded", methods=["GET"])
def documents_compare_uploaded():
    all_docs = _get_all_uploaded_documents()

    if len(all_docs) < 2:
        return jsonify({"error": "Upload at least two documents before comparing."}), 400

    user_query = request.args.get("q", "Compare these documents").strip()
    narrative, columns, rows = build_uploaded_comparison(all_docs, user_query)

    sections = [{"type": "text", "content": narrative}]
    if rows:
        sections.append({
            "type": "table",
            "heading": "Comparison",
            "columns": columns,
            "rows": rows,
        })

    pdf = render_document(
        "Document Comparison Report",
        sections,
        subtitle=", ".join(d["filename"] for d in all_docs),
    )

    return send_file(
        pdf, mimetype="application/pdf", as_attachment=True,
        download_name="document_comparison.pdf",
    )


# =====================================================
# DOCUMENT UPLOAD & Q&A
# =====================================================

from tools.document_store import set_uploaded_document

MAX_DOCUMENT_CHARS = 15000

@app.route("/api/upload-document", methods=["POST"])
def upload_document():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    filename = file.filename or "document.pdf"

    if not filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are supported right now."}), 400

    try:
        import pypdf
        reader = pypdf.PdfReader(file.stream)
        text_parts = [page.extract_text() or "" for page in reader.pages]
        full_text = "\n".join(text_parts).strip()
        page_count = len(reader.pages)
    except Exception as e:
        print("PDF extraction error:", e)
        return jsonify({"error": f"Could not read this PDF: {e}"}), 400

    if not full_text:
        return jsonify({
            "error": "Could not find any readable text in this PDF. If it's a "
                     "scanned image (photo of a document), this app can't read "
                     "it yet — that needs OCR, which isn't built in."
        }), 400

    truncated = len(full_text) > MAX_DOCUMENT_CHARS
    stored_text = full_text[:MAX_DOCUMENT_CHARS]

    set_uploaded_document(filename, stored_text, page_count)

    return jsonify({
        "filename": filename,
        "pages": page_count,
        "truncated": truncated,
        "preview": stored_text[:300],
    })


if __name__ == "__main__":
    print("=" * 60)
    print("Medical Billing AI — API server")
    print("Listening on http://localhost:5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=True)