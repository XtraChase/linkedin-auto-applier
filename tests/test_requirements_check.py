import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from requirements_check import title_blocker, hard_blockers


def test_title_blocker():
    assert title_blocker("Senior BIM Coordinator")
    assert title_blocker("VDC Director")
    assert title_blocker("BIM Project Manager")
    assert title_blocker("CAD Drafter") is None
    assert title_blocker("Revit Technician") is None


def test_license_and_clearance_blockers():
    assert "requires a PE license" in hard_blockers("Licensed Professional Engineer (PE license) required.")
    assert "requires an architect license" in hard_blockers("You are a licensed architect with Revit skills.")
    assert "requires a security clearance" in hard_blockers("Must hold an active Secret clearance.")
    assert hard_blockers("Revit drafter for residential plans. Portfolio welcome.") == []


def test_years_blocker_only_for_requirements():
    assert any("8+" in r for r in hard_blockers("Required: 8-12 years of experience in BIM/VDC."))
    assert hard_blockers("Minimum 3 years of experience with AutoCAD.") == []
    assert hard_blockers("We have over 40 years of experience serving builders.") == []       # company brag, not a requirement
    assert hard_blockers("10+ years of experience is a plus, but not required.") == []         # preferred, not required
