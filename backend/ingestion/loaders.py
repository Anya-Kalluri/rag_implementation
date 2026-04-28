import fitz
from docx import Document
from pptx import Presentation
import pandas as pd
from bs4 import BeautifulSoup
import requests
import pytesseract
from PIL import Image
import json

from backend.config.settings import TESSERACT_CMD


if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


def load_pdf(file):
    doc = fitz.open(stream=file.read(), filetype="pdf")
    return " ".join([p.get_text() for p in doc])


def load_docx(file):
    doc = Document(file)
    return " ".join([p.text for p in doc.paragraphs])


def load_pptx(file):
    prs = Presentation(file)
    text = []
    for s in prs.slides:
        for shape in s.shapes:
            if hasattr(shape, "text"):
                text.append(shape.text)
    return " ".join(text)


def load_csv(file):
    return pd.read_csv(file).to_string()


def load_image(file):
    try:
        image = Image.open(file)
        return pytesseract.image_to_string(image)
    except pytesseract.TesseractNotFoundError as e:
        raise RuntimeError(
            "OCR is not available because the Tesseract executable was not found. "
            "Install Tesseract OCR and optionally set TESSERACT_CMD in .env."
        ) from e

def load_json(file):
    return json.dumps(json.load(file), indent=2, ensure_ascii=False)


def load_text(file):
    content = file.read()
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    return content


def load_html(file):
    soup = BeautifulSoup(load_text(file), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator=" ")


def load_excel(file):
    sheets = pd.read_excel(file, sheet_name=None)
    text = []
    for sheet_name, dataframe in sheets.items():
        text.append(f"Sheet: {sheet_name}")
        text.append(dataframe.to_string(index=False))
    return "\n\n".join(text)


def load_url(url):
    try:
        res = requests.get(url, timeout=10)

        if res.status_code != 200:
            return ""

        soup = BeautifulSoup(res.text, "html.parser")

        # remove scripts/styles
        for tag in soup(["script", "style"]):
            tag.decompose()

        text = soup.get_text(separator=" ")

        return text

    except Exception as e:
        return ""
