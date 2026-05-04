"""Document parsing — extract text from PDF, DOCX, and other formats."""

from pathlib import Path


def parse_document(file_path: str) -> str:
    """Extract text from a document file. Supports PDF, DOCX, TXT, and Markdown.

    Args:
        file_path: Path to the document file.

    Returns extracted text or an error message.
    """
    p = Path(file_path).expanduser().resolve()
    if not p.exists():
        return f"Error: file not found: {file_path}"

    ext = p.suffix.lower()

    if ext == ".txt" or ext == ".md" or ext == ".markdown":
        try:
            return p.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading {file_path}: {e}"

    if ext == ".pdf":
        return _parse_pdf(p)

    if ext in (".docx", ".doc"):
        return _parse_docx(p)

    return f"Error: unsupported format '{ext}'. Supported: .txt, .md, .pdf, .docx"


def _parse_pdf(p: Path) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(str(p))
        parts = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                parts.append(text)
        result = "\n\n".join(parts)
        return result if result.strip() else "No text extracted from PDF."
    except ImportError:
        return "Error: pypdf not installed. Run: pip install pypdf"
    except Exception as e:
        return f"Error parsing PDF: {e}"


def _parse_docx(p: Path) -> str:
    try:
        import docx
        doc = docx.Document(str(p))
        parts = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(parts) if parts else "No text extracted from DOCX."
    except ImportError:
        return "Error: python-docx not installed. Run: pip install python-docx"
    except Exception as e:
        return f"Error parsing DOCX: {e}"
