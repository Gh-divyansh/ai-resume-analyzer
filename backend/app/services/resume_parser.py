import pymupdf
from docx import Document


# ---------------------------------------------------------
# PDF Parser
# ---------------------------------------------------------

def extract_text_from_pdf(file_path: str) -> str:

    document = pymupdf.open(file_path)

    text = ""

    for page in document:

        text += page.get_text()

    document.close()

    return text


# ---------------------------------------------------------
# DOCX Parser
# ---------------------------------------------------------

def extract_text_from_docx(file_path: str) -> str:

    document = Document(file_path)

    text = ""

    for paragraph in document.paragraphs:

        text += paragraph.text + "\n"

    return text