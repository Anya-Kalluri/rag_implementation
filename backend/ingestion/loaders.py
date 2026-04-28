import fitz
from docx import Document
from pptx import Presentation
import pandas as pd
from bs4 import BeautifulSoup
import requests
import pytesseract
from PIL import Image
import json


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
    return pytesseract.image_to_string(Image.open(file))

def load_json(file):
    return json.dumps(json.load(file))


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