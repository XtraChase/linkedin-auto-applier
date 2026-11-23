from job_lookup import build_job, history_row


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
