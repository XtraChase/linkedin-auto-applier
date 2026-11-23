"""
Cover letter as a PDF, for application forms that ask you to UPLOAD one.

make_pdf(text, job, out_dir) writes a one-page-style letter: your name and contact line at the top, the date, then the letter.
The name, city, phone and website come from config/personals.py and config/questions.py. The body is the AI-written letter
(adapted from your own template), exactly as it would be typed into a text box.
"""
import os, re
from datetime import datetime

import app_paths


def _contact_line():
    try:
        from config import personals as P
        from config import questions as Q
    except Exception:
        return "", ""
    name = " ".join(x for x in (P.first_name, getattr(P, "middle_name", ""), P.last_name) if x).strip()
    bits = []
    city = (getattr(P, "current_city", "") or "").strip()
    if city: bits.append(city)
    digits = re.sub(r"\D", "", getattr(P, "phone_number", "") or "")
    if len(digits) == 10: bits.append(f"({digits[:3]}) {digits[3:6]}-{digits[6:]}")
    elif digits: bits.append(digits)
    site = (getattr(Q, "website", "") or "").strip()
    if site: bits.append(site.replace("https://", "").replace("http://", "").rstrip("/"))
    return name, "  |  ".join(bits)


def safe_name(s, limit=40):
    return re.sub(r"[^A-Za-z0-9]+", "_", s or "").strip("_")[:limit] or "Company"


def make_pdf(text, job, out_dir=None):
    """Write the letter to a PDF and return its path. Raises if the PDF library is missing."""
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    name, contact = _contact_line()
    folder = out_dir or os.path.join(app_paths.home(), "all excels", "cover_letters", str((job or {}).get("id") or "job"))
    os.makedirs(folder, exist_ok=True)
    fname = f"{safe_name(name.replace(' ', '_'), 30)}_Cover_Letter_{safe_name((job or {}).get('company'))}.pdf"
    path = os.path.join(folder, fname)

    def esc(s):                                     # reportlab paragraphs are small XML
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    base = ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=13.4, alignment=TA_LEFT, spaceAfter=7)
    head = ParagraphStyle("head", parent=base, fontName="Helvetica-Bold", fontSize=16, leading=20, spaceAfter=2)
    small = ParagraphStyle("small", parent=base, fontSize=9.5, textColor="#444444", spaceAfter=14)
    doc = SimpleDocTemplate(path, pagesize=LETTER, leftMargin=0.85 * inch, rightMargin=0.85 * inch, topMargin=0.7 * inch, bottomMargin=0.7 * inch,
                            title="Cover Letter" + (f" - {name}" if name else ""), author=name)
    story = []
    if name: story.append(Paragraph(esc(name), head))
    if contact: story.append(Paragraph(esc(contact), small))
    story.append(Paragraph(datetime.now().strftime("%B %d, %Y").replace(" 0", " "), base))
    story.append(Spacer(1, 2))
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        block = block.strip()
        if block:
            story.append(Paragraph("<br/>".join(esc(line.strip()) for line in block.splitlines()), base))
    doc.build(story)
    return path
