import fitz
from docx import Document
from pptx import Presentation
import pandas as pd
from bs4 import BeautifulSoup
import requests
import pytesseract
from PIL import Image
import json
import base64
from io import BytesIO
from groq import Groq
import numpy as np
import xml.etree.ElementTree as ET

from backend.config.settings import GROQ_API_KEY, IMAGE_OCR_MODEL, TESSERACT_CMD


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
    def _rapidocr_fallback(image):
        try:
            from rapidocr_onnxruntime import RapidOCR
        except Exception as e:
            raise RuntimeError("rapidocr-onnxruntime is not installed.") from e

        engine = RapidOCR()
        image_array = np.array(image.convert("RGB"))
        result, _ = engine(image_array)
        if not result:
            return ""

        lines = []
        for item in result:
            if len(item) >= 2:
                lines.append(str(item[1]).strip())

        return "\n".join(line for line in lines if line)

    def _groq_vision_ocr(image):
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is missing. Cannot run vision OCR fallback.")

        buffer = BytesIO()
        image.save(buffer, format="PNG")
        image_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")

        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=IMAGE_OCR_MODEL,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all readable text from this image. Return plain text only."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    ],
                }
            ],
        )
        return (response.choices[0].message.content or "").strip()

    try:
        file.seek(0)
        image = Image.open(file)
        return pytesseract.image_to_string(image)
    except pytesseract.TesseractNotFoundError as e:
        rapidocr_error = None
        try:
            file.seek(0)
            image = Image.open(file)
            text = _rapidocr_fallback(image)
            if text:
                return text
        except Exception as re:
            rapidocr_error = re

        try:
            file.seek(0)
            image = Image.open(file)
            text = _groq_vision_ocr(image)
            if text:
                return text
            raise RuntimeError("Vision OCR fallback returned empty text.")
        except Exception as fallback_error:
            raise RuntimeError(
                "OCR is not available locally (Tesseract missing), RapidOCR fallback failed, and vision OCR fallback failed. "
                "Install Tesseract OCR and set TESSERACT_CMD in .env, or set IMAGE_OCR_MODEL to a working vision model."
            ) from (rapidocr_error or fallback_error)

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


def load_xml(file):
    content = load_text(file)
    root = ET.fromstring(content)
    texts = []
    for element in root.iter():
        if element.text and element.text.strip():
            texts.append(element.text.strip())
    return "\n".join(texts)


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
