import pytest

from job_lookup import build_job, history_row, parse_job_link, parse_job_meta


@pytest.mark.parametrize("text, expected", [
    ("https://www.linkedin.com/jobs/view/4123456789/", "4123456789"),
    ("https://www.linkedin.com/jobs/view/4123456789", "4123456789"),
    ("https://www.linkedin.com/jobs/view/cad-drafter-at-acme-4123456789/?refId=abc&trackingId=x", "4123456789"),
    ("linkedin.com/jobs/view/4123456789/", "4123456789"),
    ("https://www.linkedin.com/comm/jobs/view/4123456789/?trk=email", "4123456789"),
    ("https://www.linkedin.com/jobs/search/?keywords=cad&currentJobId=4123456789&f_AL=true", "4123456789"),
    ("https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4123456789", "4123456789"),
    ("https://uk.linkedin.com/jobs/view/4123456789/", "4123456789"),
    ("  <https://www.linkedin.com/jobs/view/4123456789/>  ", "4123456789"),
    ("4123456789", "4123456789"),
    ("", ""), ("   ", ""), ("hello", ""), ("123", ""),
    ("https://www.linkedin.com/in/someone/", ""),
    ("https://www.linkedin.com/jobs/search/?keywords=cad", ""),
    ("https://example.com/jobs/view/4123456789/", ""),                               # another website is never accepted
    ("https://linkedin.com.evil.example/jobs/view/4123456789/", ""),
    ("https://notlinkedin.com/jobs/view/4123456789/", ""),
])
def test_parse_job_link(text, expected):
    assert parse_job_link(text) == expected


def test_parse_job_meta_prefers_structured_data_then_titles():
    ld = {"ld": {"title": "CAD Drafter", "company": "Acme Co", "location": "Remote, US"}, "og": "", "doc": ""}
    assert parse_job_meta(ld) == {"title": "CAD Drafter", "company": "Acme Co", "location": "Remote, US"}
    og = {"ld": {}, "og": "Acme Co hiring CAD Drafter in Bozeman, MT | LinkedIn", "doc": ""}
    assert parse_job_meta(og) == {"title": "CAD Drafter", "company": "Acme Co", "location": "Bozeman, MT"}
    doc = {"ld": {}, "og": "", "doc": "CAD Drafter | Acme Co | LinkedIn"}
    assert parse_job_meta(doc) == {"title": "CAD Drafter", "company": "Acme Co", "location": ""}
    mixed = {"ld": {"title": "Real Title"}, "og": "Acme Co hiring Other in X | LinkedIn", "doc": ""}
    assert parse_job_meta(mixed)["title"] == "Real Title" and parse_job_meta(mixed)["company"] == "Acme Co"
    assert parse_job_meta(None) == {"title": "", "company": "", "location": ""}
    assert parse_job_meta({"ld": {}, "og": "", "doc": "LinkedIn"}) == {"title": "", "company": "", "location": ""}


def test_history_row_returns_newest_match(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("job_id,title,company,location,link,status,time\n5,Old,A,Remote,x,scored,t1\n5,New,A2,Remote,x,opened,t2\n6,Other,B,Remote,x,scored,t3\n", encoding="utf-8")
    assert history_row("5", str(p))["title"] == "New"
    assert history_row("99", str(p)) == {}
    assert history_row("5", str(tmp_path / "missing.csv")) == {}


def test_build_job_prefers_cache_then_history_and_has_safe_defaults():
    j = build_job("5", {"title": "CAD Drafter", "company": "Acme", "score": 72, "reason": "fits", "description": "d"}, {"title": "x", "company": "y", "location": "Remote"})
    assert (j["title"], j["company"], j["score"], j["location"], j["term"]) == ("CAD Drafter", "Acme", 72, "Remote", "CAD Drafter")
    bare = build_job("7")
    assert bare["title"] == "" and bare["score"] is None and bare["term"] == "CAD Drafter" and bare["description"] == ""
