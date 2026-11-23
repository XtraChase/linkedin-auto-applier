import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from form_filler import pick_resume

RESUMES = [
    {"idx": "1", "text": "PDF Resume General.pdf 11/4/2026", "checked": True},
    {"idx": "2", "text": "PDF Resume CAD Drafting.pdf 8/24/2026", "checked": False},
    {"idx": "3", "text": "PDF Resume 3D Artist.pdf 10/31/2025", "checked": False},
]


def test_keeps_linkedin_choice_when_no_rules():
    assert pick_resume("CAD Drafter", RESUMES) is None


def test_preferred_resume_applies_to_every_job():
    assert pick_resume("Anything", RESUMES, preferred="3D Artist") == 2


def test_rules_are_matched_by_job_title_first_match_wins():
    rules = [["drafter|drafting|cad", "CAD Drafting"], ["artist", "3D Artist"]]
    assert pick_resume("AutoCAD Drafter", RESUMES, "", rules) == 1
    assert pick_resume("Environment Artist", RESUMES, "", rules) == 2
    assert pick_resume("Accountant", RESUMES, "", rules) is None


def test_bad_rule_or_missing_resume_is_ignored():
    assert pick_resume("CAD Drafter", RESUMES, "", [["cad", "no such resume"]]) is None
    assert pick_resume("CAD Drafter", RESUMES, "(", []) is None
