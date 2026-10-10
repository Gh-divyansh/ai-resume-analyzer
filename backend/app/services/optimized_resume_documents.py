"""Format-preserving DOCX/PDF optimization that preserves original document structure."""
from io import BytesIO
import re

try:
    import pymupdf as fitz
except ImportError:
    import fitz
from docx import Document
from docx.shared import Inches, Pt


class DocumentPreservationError(RuntimeError):
    """Raised when a layout-preserving edit cannot be proven safe."""


def _normalise_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _document_paragraphs(doc: Document):
    """Yield every editable paragraph without rebuilding document structure."""
    yield from doc.paragraphs
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs
    for section in doc.sections:
        for container in (section.header, section.footer):
            yield from container.paragraphs
            for table in container.tables:
                for row in table.rows:
                    for cell in row.cells:
                        yield from cell.paragraphs


def _find_text_in_paragraph(paragraph, search_text: str) -> bool:
    """Check if paragraph contains the search text (case-insensitive, whitespace-normalized)."""
    para_text = paragraph.text.strip()
    search_normalized = " ".join(search_text.strip().split())
    para_normalized = " ".join(para_text.split())
    return search_normalized.lower() in para_normalized.lower() or para_normalized.lower() in search_normalized.lower()


def _replace_text_in_paragraph(paragraph, old_text: str, new_text: str) -> bool:
    """Apply one bounded bullet replacement without changing paragraph geometry.

    We only edit a complete, single-run paragraph.  A partial or multi-run
    match can silently destroy emphasis, fields, links, or tab stops, so it is
    deliberately not treated as a candidate for a layout-preserving edit.
    """
    if _normalise_text(paragraph.text) != _normalise_text(old_text):
        return False
    if len(paragraph.runs) != 1:
        raise DocumentPreservationError("A proposed rewrite spans formatted runs and cannot be safely edited in place.")
    if len(_normalise_text(new_text)) > len(_normalise_text(old_text)):
        raise DocumentPreservationError("A proposed rewrite is longer than its source bullet and could reflow the document.")
    paragraph.runs[0].text = new_text
    return True


def render_docx_preserving_format(original_docx_bytes: bytes, optimized_resume: dict, improvements: list[dict]) -> bytes:
    """
    Generate optimized DOCX by preserving original document structure and replacing only improved text.
    
    Args:
        original_docx_bytes: Original uploaded DOCX file bytes
        optimized_resume: Structured resume with optimized content
        improvements: List of {"original": str, "improved": str} replacements
    
    Returns:
        Optimized DOCX bytes with preserved formatting
    """
    if not improvements:
        # No content change means the exact original file is the only
        # format-preserving optimized DOCX.
        Document(BytesIO(original_docx_bytes))
        return original_docx_bytes

    doc = Document(BytesIO(original_docx_bytes))
    
    # Apply each improvement by finding and replacing text
    for improvement in improvements:
        original_text = improvement["original"]
        improved_text = improvement["improved"]
        
        replaced = False
        for paragraph in _document_paragraphs(doc):
            if _replace_text_in_paragraph(paragraph, original_text, improved_text):
                replaced = True
                break
        if not replaced:
            raise DocumentPreservationError("A proposed rewrite could not be mapped to one original document paragraph.")
    
    # Save to bytes
    output = BytesIO()
    doc.save(output)
    rendered = output.getvalue()
    validated = Document(BytesIO(rendered))
    for improvement in improvements:
        if not any(_normalise_text(paragraph.text) == _normalise_text(improvement["improved"]) for paragraph in _document_paragraphs(validated)):
            raise DocumentPreservationError("A rewritten DOCX bullet was missing after save validation.")
    return rendered


def render_pdf_preserving_format(original_pdf_bytes: bytes, optimized_resume: dict, improvements: list[dict]) -> bytes:
    """
    Generate optimized PDF by preserving original document structure and replacing only improved text.
    
    For text-based PDFs, this replaces only a single source text rectangle when
    the replacement fits inside that exact rectangle. Complex, wrapped, and
    image-based PDFs fail closed rather than being reconstructed.
    
    Args:
        original_pdf_bytes: Original uploaded PDF file bytes
        optimized_resume: Structured resume with optimized content
        improvements: List of {"original": str, "improved": str} replacements
    
    Returns:
        Optimized PDF bytes with preserved formatting where possible
    """
    raise DocumentPreservationError(
        "PDF in-place optimization is disabled. PDF uploads receive an optimized DOCX instead."
    )

    original = fitz.open(stream=original_pdf_bytes, filetype="pdf")
    original_geometry = [page.rect for page in original]
    original_text_pages = [bool(page.get_text().strip()) for page in original]
    pdf = fitz.open(stream=original_pdf_bytes, filetype="pdf")
    try:
        if not improvements:
            return original_pdf_bytes
        for improvement in improvements:
            original_text = improvement["original"]
            improved_text = improvement["improved"]
            locations = []
            for page_index, page in enumerate(pdf):
                rects = page.search_for(original_text)
                if rects:
                    locations.extend((page_index, rect) for rect in rects)
            if len(locations) != 1:
                raise DocumentPreservationError("A proposed rewrite cannot be located as one unambiguous PDF text block.")
            page_index, rect = locations[0]
            page = pdf[page_index]
            matched_line = next(
                (line for block in page.get_text("dict").get("blocks", []) if block.get("type") == 0
                 for line in block.get("lines", []) if fitz.Rect(line["bbox"]).intersects(rect)),
                None,
            )
            span = matched_line.get("spans", [None])[0] if matched_line else None
            if not span or not matched_line:
                raise DocumentPreservationError("The PDF text block has no safe font information.")
            line_rect = fitz.Rect(matched_line["bbox"])
            replacement_width = fitz.get_text_length(improved_text, fontname="helv", fontsize=span["size"])
            if replacement_width > line_rect.width + 0.5:
                raise DocumentPreservationError("A proposed rewrite does not fit in its original PDF text line.")
            page.add_redact_annot(rect, fill=(1, 1, 1))
            page.apply_redactions()
            # Write at the source span baseline rather than reflowing through
            # a new text box. Width was measured against the original line.
            page.insert_text(span["origin"], improved_text, fontsize=span["size"], fontname="helv")

        output = pdf.tobytes(garbage=4, deflate=True)
    finally:
        original.close()
        pdf.close()
    _validate_preserved_pdf(original_pdf_bytes, output, original_geometry, original_text_pages, improvements)
    return output


def _validate_preserved_pdf(original_bytes: bytes, output: bytes, original_geometry, original_text_pages, improvements: list[dict]) -> None:
    """Fail closed on structural or text-boundary defects after PDF editing."""
    pdf = fitz.open(stream=output, filetype="pdf")
    try:
        if pdf.page_count != len(original_geometry):
            raise DocumentPreservationError("PDF page count changed during layout-preserving optimization.")
        for index, page in enumerate(pdf):
            if page.rect != original_geometry[index]:
                raise DocumentPreservationError("PDF page geometry changed during optimization.")
            if original_text_pages[index] and not page.get_text().strip():
                raise DocumentPreservationError("An original PDF page became blank during optimization.")
            for x0, y0, x1, y1, *_ in page.get_text("words"):
                word_rect = fitz.Rect(x0, y0, x1, y1)
                if not page.rect.contains(word_rect):
                    raise DocumentPreservationError("PDF text was clipped outside its original page boundary.")
        combined = _normalise_text("\n".join(page.get_text() for page in pdf))
        for improvement in improvements:
            if _normalise_text(improvement["improved"]) not in combined:
                raise DocumentPreservationError("A rewritten PDF bullet was missing after save validation.")
    finally:
        pdf.close()


def _render_pdf_fallback(original_pdf_bytes: bytes, optimized_resume: dict) -> bytes:
    """
    Fallback PDF generation that attempts to preserve original page size and basic layout.
    
    This is used when in-place editing is not possible (image-based PDFs, complex layouts, etc.)
    """
    # Open original to extract page size
    original_pdf = fitz.open(stream=original_pdf_bytes, filetype="pdf")
    original_page_rect = original_pdf[0].rect if original_pdf.page_count > 0 else fitz.Rect(0, 0, 595, 842)
    original_pdf.close()
    
    # Generate new PDF with original page size
    pdf = fitz.open()
    page = pdf.new_page(width=original_page_rect.width, height=original_page_rect.height)
    
    # Use reasonable margins based on original page size
    margin = 48
    y = margin
    
    # Render optimized content with simple layout
    def add_text(text: str, bold: bool = False):
        nonlocal y, page
        font_size = 13 if bold else 10
        height = 16 if bold else 12
        
        result = page.insert_textbox(
            fitz.Rect(margin, y, original_page_rect.width - margin, original_page_rect.height - margin),
            text,
            fontsize=font_size,
            fontname="helv",
            fontfile=None,
            align=0
        )
        
        if result < 0 or y > original_page_rect.height - 100:
            # Need new page
            page = pdf.new_page(width=original_page_rect.width, height=original_page_rect.height)
            y = margin
            page.insert_textbox(
                fitz.Rect(margin, y, original_page_rect.width - margin, original_page_rect.height - margin),
                text,
                fontsize=font_size,
                fontname="helv"
            )
        
        y += height + 4
    
    # Add content
    if optimized_resume.get("name"):
        add_text(optimized_resume["name"], bold=True)
    if optimized_resume.get("title"):
        add_text(optimized_resume["title"])
    if optimized_resume.get("summary"):
        add_text("Summary", bold=True)
        add_text(optimized_resume["summary"])
    if optimized_resume.get("skills"):
        add_text("Skills", bold=True)
        add_text(", ".join(optimized_resume["skills"]))
    if optimized_resume.get("experience"):
        add_text("Experience", bold=True)
        for exp in optimized_resume["experience"]:
            header = " | ".join(filter(None, [exp.get("role"), exp.get("company"), exp.get("duration")]))
            add_text(header)
            for bullet in exp.get("responsibilities", []):
                add_text(f"• {bullet}")
    if optimized_resume.get("education"):
        add_text("Education", bold=True)
        for edu in optimized_resume["education"]:
            line = " | ".join(filter(None, [edu.get("degree"), edu.get("institution"), edu.get("duration")]))
            add_text(line)
    if optimized_resume.get("projects"):
        add_text("Projects", bold=True)
        for proj in optimized_resume["projects"]:
            if proj.get("name"):
                add_text(proj["name"])
            if proj.get("description"):
                add_text(proj["description"])
    
    output = pdf.tobytes()
    pdf.close()
    return output


def render_ats_docx(resume: dict) -> bytes:
    """Render an ATS-friendly DOCX for a PDF source without touching its PDF layout."""
    document = Document()
    section = document.sections[0]
    section.top_margin = section.bottom_margin = Inches(0.7)
    section.left_margin = section.right_margin = Inches(0.75)
    style = document.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(10)
    
    def add_line(text: str, bold: bool = False, size: int = 10):
        paragraph = document.add_paragraph()
        run = paragraph.add_run(text)
        run.bold = bold
        run.font.size = Pt(size)
        paragraph.paragraph_format.space_after = Pt(5)
    
    if resume.get("name"):
        add_line(resume["name"], bold=True, size=15)
    if resume.get("title"):
        add_line(resume["title"])
    if resume.get("summary"):
        add_line("Summary", bold=True, size=11)
        add_line(resume["summary"])
    if resume.get("skills"):
        add_line("Skills", bold=True, size=11)
        add_line(", ".join(resume["skills"]))
    if resume.get("experience"):
        add_line("Experience", bold=True, size=11)
        for exp in resume["experience"]:
            header = " | ".join(filter(None, [exp.get("role", ""), exp.get("company", ""), exp.get("duration", "")]))
            add_line(header)
            for bullet in exp.get("responsibilities", []):
                add_line(f"- {bullet}")
    if resume.get("education"):
        add_line("Education", bold=True, size=11)
        for edu in resume["education"]:
            line = " | ".join(filter(None, [edu.get("degree", ""), edu.get("institution", ""), edu.get("duration", "")]))
            add_line(line)
    if resume.get("projects"):
        add_line("Projects", bold=True, size=11)
        for proj in resume["projects"]:
            if proj.get("name"):
                add_line(proj["name"])
            if proj.get("description"):
                add_line(proj["description"])
    
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


# Kept for internal compatibility with existing document tests. Production
# optimization calls ``render_ats_docx`` explicitly for PDF-source resumes.
def render_docx(resume: dict) -> bytes:
    return render_ats_docx(resume)


def render_pdf(resume: dict) -> bytes:
    """Legacy generic PDF generation (fallback only)."""
    pdf = fitz.open()
    page = pdf.new_page()
    rect = page.rect
    y = 48
    
    def add_text(text: str, bold: bool = False):
        nonlocal y, page
        font_size = 13 if bold else 9.5
        height = 18 if bold else 14
        
        result = page.insert_textbox(
            fitz.Rect(48, y, rect.width - 48, rect.height - 40),
            text,
            fontsize=font_size,
            fontname="helv",
            fontfile=None,
            align=0
        )
        
        if result < 0 or y > rect.height - 70:
            page = pdf.new_page()
            y = 48
            page.insert_textbox(
                fitz.Rect(48, y, rect.width - 48, rect.height - 40),
                text,
                fontsize=font_size,
                fontname="helv"
            )
        
        y += height + 5
    
    if resume.get("name"):
        add_text(resume["name"], bold=True)
    if resume.get("title"):
        add_text(resume["title"])
    if resume.get("summary"):
        add_text("Summary", bold=True)
        add_text(resume["summary"])
    if resume.get("skills"):
        add_text("Skills", bold=True)
        add_text(", ".join(resume["skills"]))
    if resume.get("experience"):
        add_text("Experience", bold=True)
        for exp in resume["experience"]:
            header = " | ".join(filter(None, [exp.get("role", ""), exp.get("company", ""), exp.get("duration", "")]))
            add_text(header)
            for bullet in exp.get("responsibilities", []):
                add_text(f"- {bullet}")
    if resume.get("education"):
        add_text("Education", bold=True)
        for edu in resume["education"]:
            line = " | ".join(filter(None, [edu.get("degree", ""), edu.get("institution", ""), edu.get("duration", "")]))
            add_text(line)
    if resume.get("projects"):
        add_text("Projects", bold=True)
        for proj in resume["projects"]:
            if proj.get("name"):
                add_text(proj["name"])
            if proj.get("description"):
                add_text(proj["description"])
    
    output = pdf.tobytes()
    pdf.close()
    return output
