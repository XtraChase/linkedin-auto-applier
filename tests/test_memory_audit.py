import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from answer_memory import Memory, normalize
from answer_audit import risk_flags, summarize


def test_normalize_ignores_case_punctuation_and_star():
    assert normalize("How many years of Revit experience do you have?*") == "how many years of revit experience do you have"


def test_memory_roundtrip_and_option_check(tmp_path):
    m = Memory(str(tmp_path / "answers.json"))
    assert m.learn("Do you like CAD?", "Yes", "radio") is True
    assert m.learn("Do you like CAD?", "Yes", "radio") is False          # unchanged answer is not a new learning
    m2 = Memory(str(tmp_path / "answers.json"))                           # persisted to disk
    assert m2.get("do you like cad", "radio", ["Yes", "No"]) == "Yes"
    assert m2.get("do you like cad", "radio", ["Maybe", "No"]) is None   # must be one of the options
    m2.forget("Do you like CAD?")
    assert m2.get("Do you like CAD?", "radio", ["Yes", "No"]) is None


def test_config_answers_are_not_flagged():
    assert risk_flags("How many years of Revit experience?", "5", "config") == []


def test_default_years_and_ai_claims_are_flagged():
    f = risk_flags("How many years of experience do you have in electrical BIM design?", "3", "default-years")
    assert any("default years" in x for x in f) and any("years" in x for x in f)
    f = risk_flags("Do you have experience with Revit, Navisworks, Bluebeam, and Microsoft Office software?", "Yes", "ai")
    assert any("list of tools" in x for x in f)


def test_prefilled_background_question_is_flagged():
    f = risk_flags("Are you willing to take a drug test?", "Yes", "kept")
    assert any("pre-filled" in x for x in f) and any("background" in x for x in f)


def test_summarize_puts_flagged_first():
    rows = [{"q": "Phone", "a": "1", "source": "config", "flags": []},
            {"q": "Years of X", "a": "3", "source": "default-years", "flags": ["claims years of experience"]}]
    out = []
    summarize(rows, out.append)
    text = "\n".join(out)
    assert text.index("Needs your eyes") < text.index("From your config")
