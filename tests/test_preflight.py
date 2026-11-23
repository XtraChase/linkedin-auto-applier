import os

import pytest

pytest.importorskip("PySide6")
from desktop import preflight


def test_flags_missing_key_template_facts_and_resume(tmp_path):
    prof = tmp_path / "profile.md"; prof.write_text("- Name: First Last\n", encoding="utf-8")
    problems = preflight.check(root=str(tmp_path), profile_path=str(prof), key_present=False)
    assert len(problems) == 3
    assert any("API key" in p for p in problems) and any("template" in p for p in problems) and any("resume" in p.lower() for p in problems)


def test_all_good_and_no_ai_skips_the_key_check(tmp_path):
    prof = tmp_path / "profile.md"; prof.write_text("- Name: Alex Example\n", encoding="utf-8")
    (tmp_path / "all resumes" / "default").mkdir(parents=True); (tmp_path / "all resumes" / "default" / "resume.pdf").write_bytes(b"%PDF")
    assert preflight.check(root=str(tmp_path), profile_path=str(prof), key_present=True) == []
    assert preflight.check(no_ai=True, root=str(tmp_path), profile_path=str(prof), key_present=False) == []


def test_missing_profile_file_is_reported(tmp_path):
    problems = preflight.check(no_ai=True, root=str(tmp_path), profile_path=str(tmp_path / "nope.md"))
    assert any("facts" in p for p in problems)
