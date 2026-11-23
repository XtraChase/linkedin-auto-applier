import os, shutil, sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def test_cover_letter_pdf_is_a_real_one_page_pdf(tmp_path):
    from cover_letter_pdf import make_pdf
    text = "Dear Hiring Team,\n\n" + ("I draft construction drawings in Revit and AutoCAD. " * 12 + "\n\n") * 4 + "Sincerely,\n\nTest Person"
    path = make_pdf(text, {"id": "t1", "company": "Example & Sons <Architects>"}, str(tmp_path))
    data = open(path, "rb").read()
    assert data.startswith(b"%PDF") and len(data) > 1500
    assert os.path.basename(path).endswith(".pdf") and "Example_Sons_Architects" in os.path.basename(path)


@pytest.fixture(scope="module")
def chrome():
    pytest.importorskip("selenium")
    from selenium import webdriver
    o = webdriver.ChromeOptions()
    o.add_argument("--headless=new"); o.add_argument("--blink-settings=scriptEnabled=false"); o.add_argument("--window-size=1400,1200")
    try:
        d = webdriver.Chrome(options=o)
    except Exception as e:
        pytest.skip(f"Chrome not available: {type(e).__name__}")
    yield d
    d.quit()


class FakeAI:
    def cover_letter(self, maxlen=0):
        return "Dear Hiring Team,\n\nI would like to apply.\n\nSincerely,\nTest Person"


def load(d):
    d.get("file:///" + os.path.join(FIX, "form_cover_letter_upload.html").replace("\\", "/"))


def test_filler_tells_resume_and_cover_letter_uploads_apart(chrome):
    import form_filler as ff
    load(chrome)
    pg = chrome.execute_script(ff.ENUM_JS)
    kinds = sorted(f["kind"] for f in pg["files"])
    assert kinds == ["cover", "resume"]


def test_filler_writes_a_pdf_and_uploads_it_into_the_cover_letter_input_only(chrome):
    import form_filler as ff
    load(chrome)
    f = ff.Filler(chrome, log=lambda *a: None, ai=FakeAI(), job={"id": "uploadtest", "title": "CAD Drafter", "company": "Example Co"})
    pg = chrome.execute_script(ff.ENUM_JS)
    failed = f.handle_uploads(pg)
    assert failed == []
    names = chrome.execute_script("return [...document.querySelectorAll('input[type=file]')].map(i => [i.id, i.files.length ? i.files[0].name : ''])")
    assert dict(names)["cover-up"].endswith(".pdf") and "Cover_Letter" in dict(names)["cover-up"]
    assert dict(names)["resume-up"] == ""                         # the resume input is left alone
    assert any(a["q"] == "Cover letter (PDF upload)" and a["source"] == "ai" for a in f.answers)
    shutil.rmtree(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "all excels", "cover_letters", "uploadtest"), ignore_errors=True)


def test_without_ai_or_with_cover_letters_off_the_user_is_asked_to_upload(chrome):
    import form_filler as ff
    load(chrome)
    f = ff.Filler(chrome, log=lambda *a: None, ai=None, job={"id": "noai"})
    pg = chrome.execute_script(ff.ENUM_JS)
    assert f.handle_uploads(pg) == ["Cover letter (PDF upload)"]
