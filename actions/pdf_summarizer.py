from pathlib import Path

from actions.ollama_text import OllamaTextModel

PDF_SUMMARY_PROMPT = """You are a highly intelligent personal AI assistant.

Your role is to analyze and summarize any PDF document uploaded by the user in a way that is clear, practical, and useful for decision-making.

Follow this framework:

1. Understand the Context
   - Detect document type (academic, legal, invoice, research, notes, story, technical, report, etc.).
   - Adapt tone and depth accordingly.
   - If the document seems study-related, prioritize conceptual clarity.
   - If it is professional, prioritize action points and risks.

2. Provide Layered Summaries

   SECTION 1: Quick Overview (3–5 lines)
   → A fast understanding of what this document is about.

   SECTION 2: Structured Summary
   → Organized with headings.
   → Highlight key arguments, facts, data, or clauses.
   → Extract names, dates, amounts, deadlines if present.

   SECTION 3: Important Highlights
   → Critical insights
   → Warnings or risks (if any)
   → Key numbers/statistics

   SECTION 4: Actionable Insights
   → What should the user do next?
   → Any decisions required?
   → Any follow-up questions to consider?

3. Accuracy Rules
   - Do NOT fabricate missing information.
   - If something is unclear, state "Not clearly specified in the document."
   - Stay concise but complete.

4. Adaptability
   - If the user says "summarize in 5 lines", override default and shorten.
   - If the user says "explain deeply", provide expanded conceptual breakdown.
   - If the PDF is very long, focus on main sections rather than minor details.

5. Optional Enhancements
   - Provide important keywords.
   - Suggest potential exam questions (if academic).
   - Simplify complex jargon when needed.

Maintain a helpful, intelligent, and efficient assistant tone."""


def _resolve_path(raw: str) -> Path:
    value = (raw or "").strip().strip('"').strip("'")
    shortcuts = {
        "desktop": Path.home() / "Desktop",
        "downloads": Path.home() / "Downloads",
        "documents": Path.home() / "Documents",
        "home": Path.home(),
    }
    low = value.lower()
    if low in shortcuts:
        return shortcuts[low]
    return Path(value).expanduser()


def _extract_pdf_text(pdf_path: Path) -> str:
    from pypdf import PdfReader  # type: ignore

    reader = PdfReader(str(pdf_path))
    chunks: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            chunks.append(text.strip())
    return "\n\n".join(chunks).strip()


def pdf_summarizer(parameters=None, player=None, response=None, speak=None):
    params = parameters or {}
    path_raw = str(params.get("path", "")).strip()
    style = str(params.get("style", "concise")).strip().lower()
    user_instruction = str(params.get("instruction", "")).strip()

    if not path_raw:
        return "Please provide a PDF path. Example: summarize pdf C:\\Users\\User\\Documents\\file.pdf"

    pdf_path = _resolve_path(path_raw)
    if pdf_path.is_dir():
        return f"Expected a PDF file path, got a folder: {pdf_path}"
    if not pdf_path.exists():
        return f"PDF not found: {pdf_path}"
    if pdf_path.suffix.lower() != ".pdf":
        return f"File is not a PDF: {pdf_path.name}"

    try:
        text = _extract_pdf_text(pdf_path)
    except Exception as exc:
        return f"Could not read PDF: {exc}"

    if not text:
        return "No extractable text found in this PDF. It may be scanned/image-only."

    max_chars = 22000
    source = text[:max_chars]
    truncated_note = ""
    if len(text) > max_chars:
        truncated_note = (
            f"\n\nNote: Source text truncated for summarization ({max_chars} of {len(text)} chars)."
        )

    if style not in {"concise", "detailed", "bullet"}:
        style = "concise"

    style_note = ""
    if style == "bullet":
        style_note = "User preference: use concise bullet points where possible."
    elif style == "detailed":
        style_note = "User preference: explain deeply with more detail."
    else:
        style_note = "User preference: concise summary."

    prompt = (
        f"{PDF_SUMMARY_PROMPT}\n\n"
        f"{style_note}\n"
        f"{'Additional user instruction: ' + user_instruction if user_instruction else ''}\n\n"
        f"PDF file name: {pdf_path.name}\n\n"
        f"PDF text:\n{source}"
    )

    try:
        model = OllamaTextModel("llama3:8b")
        summary = model.generate_content(prompt).text.strip()
    except Exception as exc:
        return f"Could not summarize PDF with model: {exc}"

    if not summary:
        return "I could not generate a summary from this PDF."
    return f"PDF Summary ({pdf_path.name}):\n{summary}{truncated_note}"
