import json, os, sys, textwrap

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from desktop import data
from desktop.runner import BotRunner, PROMPT_RE, clean_chunk


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_clean_chunk_drops_driver_noise_and_keeps_partial_line():
    lines, rest = clean_chunk("", "Login successful!\n\tchromedriver!GetHandleVerifier [0x1]\nStacktrace:\n=== Search ===\nDid you sub")
    assert lines == ["Login successful!", "=== Search ==="]
    assert rest == "Did you sub"
    lines, rest = clean_chunk(rest, "mit it? y = yes, Enter = no, q = quit: ")
    assert lines == [] and PROMPT_RE.search(rest)


def test_prompt_patterns():
    assert PROMPT_RE.search("   Did you submit it? y = yes, Enter = no, q = quit: ")
    assert PROMPT_RE.search("   Press Enter to continue to the next job, or q then Enter to quit: ")
    assert not PROMPT_RE.search("Press the button")


def test_runner_streams_output_and_answers_prompts(app, tmp_path):
    script = tmp_path / "fake_bot.py"
    script.write_text(textwrap.dedent("""
        print("starting", flush=True)
        ans = input("   Did you submit it? y = yes, Enter = no, q = quit: ")
        print("got:" + repr(ans), flush=True)
    """), encoding="utf-8")
    r = BotRunner()
    lines, prompts = [], []
    loop = QEventLoop()
    r.line.connect(lines.append)
    r.prompt.connect(lambda t: (prompts.append(t), r.answer("y")))
    r.finished.connect(lambda code: loop.quit())
    QTimer.singleShot(20000, loop.quit)
    r.start(str(script))
    loop.exec()
    assert "starting" in lines
    assert len(prompts) == 1 and "Did you submit it?" in prompts[0]
    assert "got:'y'" in lines


def test_jobs_and_memory_data_layer(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "CACHE", str(tmp_path / "cache.json"))
    monkeypatch.setattr(data, "HISTORY", str(tmp_path / "hist.csv"))
    monkeypatch.setattr(data, "MEMORY", str(tmp_path / "answers.json"))
    (tmp_path / "cache.json").write_text(json.dumps({"1": {"score": 70, "title": "CAD Drafter", "company": "A", "reason": "good"},
                                                      "2": {"score": 40, "title": "Detailer", "company": "B", "reason": "ok"}}))
    (tmp_path / "hist.csv").write_text("job_id,title,company,location,link,status,time\n2,Detailer,B,Remote,x,applied (fit 40),2026-01-01T10:00:00\n")
    jobs = data.load_jobs()
    assert [j["id"] for j in jobs] == ["1", "2"]                      # best fit first
    assert jobs[1]["status"].startswith("applied") and jobs[1]["score"] == 40
    assert jobs[0]["link"].endswith("/jobs/view/1/")

    data.save_memory([{"question": "Do you like CAD?", "answer": "Yes", "kind": "radio"}, {"question": "", "answer": "x"}])
    rows = data.load_memory()
    assert len(rows) == 1 and rows[0]["answer"] == "Yes"


def test_mark_as_submitted_updates_or_adds_the_history_row(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "EXCEL", str(tmp_path))
    monkeypatch.setattr(data, "HISTORY", str(tmp_path / "hist.csv"))
    (tmp_path / "hist.csv").write_text("job_id,title,company,location,link,status,time\n7,Drafter,Acme,Remote,x,stopped at review (closed, not submitted),2026-01-01T10:00:00\n")
    data.set_history_status("7", "applied (marked by you)")
    data.set_history_status("9", "applied (marked by you)", "New Job", "Corp")
    rows = [r.split(",") for r in (tmp_path / "hist.csv").read_text().strip().splitlines()]
    assert rows[1][5] == "applied (marked by you)"
    assert rows[2][0] == "9" and rows[2][1] == "New Job" and rows[2][5].startswith("applied")


def test_current_job_file_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "CURRENT_JOB", str(tmp_path / "current_job.json"))
    assert data.read_current_job() is None
    (tmp_path / "current_job.json").write_text(json.dumps({"id": "5", "title": "CAD Drafter", "link": "https://www.linkedin.com/jobs/view/5/"}))
    assert data.read_current_job()["title"] == "CAD Drafter"


def test_run_tab_tracks_the_current_job_and_enables_the_listing_button(app):
    from desktop.tabs import RunTab
    runner = BotRunner()
    tab = RunTab(runner)
    assert not tab.job_box.isVisibleTo(tab)
    runner.line.emit(">>> Applying to #1: [70] Structural Design Technician | HKA Enterprises")
    assert tab.job_box.isVisibleTo(tab) and not tab.open_btn.isEnabled()          # no link yet
    runner.line.emit("   job-link: https://www.linkedin.com/jobs/view/4488219783/")
    assert tab.open_btn.isEnabled() and tab.job_link.endswith("/4488219783/")
    assert "Structural Design Technician" in tab.job_label.text()


def test_icon_file_is_shipped():
    import app_paths
    assert os.path.exists(os.path.join(app_paths.assets_dir(), "LinkedInAutoApplierIcon.ico"))


def test_main_window_builds_with_all_tabs(app):
    from desktop.main_window import MainWindow
    w = MainWindow()
    assert [w.tabs.tabText(i) for i in range(w.tabs.count())] == ["Run", "Jobs", "Answers", "Profile", "Settings"]
    assert w.run_tab.args()[:2] == ["--max-jobs", str(w.run_tab.max_jobs.value())]
    w.close()


def _fake_jobs(monkeypatch):
    jobs = [{"id": "11", "title": "CAD Drafter", "company": "Acme", "status": "scored", "score": 70, "reason": "good", "link": "x"},
            {"id": "12", "title": "Detailer", "company": "B", "status": "applied (fit 40)", "score": 40, "reason": "", "link": "y"},
            {"id": "13", "title": "BIM Tech", "company": "C", "status": "stopped at review (closed, not submitted)", "score": 55, "reason": "", "link": "z"}]
    monkeypatch.setattr(data, "load_jobs", lambda: jobs)


def test_jobs_tab_has_auto_apply_only_for_jobs_not_applied(app, monkeypatch):
    from desktop.tabs import JobsTab
    from PySide6.QtWidgets import QPushButton
    _fake_jobs(monkeypatch)
    tab = JobsTab()
    btns = [tab.table.cellWidget(r, 4) for r in range(3)]
    assert isinstance(btns[0], QPushButton) and btns[0].text() == "Auto apply"
    assert btns[1] is None                                  # already submitted: no button
    assert isinstance(btns[2], QPushButton)                 # opened but not submitted: can be retried
    got = []
    tab.apply_requested.connect(lambda *a: got.append(a))
    btns[2].click()
    assert got == [("13", "BIM Tech", "C")]
    tab.filter.setCurrentText("Submitted")                  # refreshing must not leave a stale button behind
    assert tab.table.rowCount() == 1 and tab.table.cellWidget(0, 4) is None


def test_run_tab_start_job_runs_one_job_and_refuses_when_busy(app, monkeypatch):
    from desktop.tabs import RunTab
    runner = BotRunner()
    calls = []
    monkeypatch.setattr(runner, "start", lambda script, args=(): calls.append((script, list(args))))
    tab = RunTab(runner)
    monkeypatch.setattr("desktop.preflight.check", lambda **k: [])
    monkeypatch.setattr(runner, "is_running", lambda: False)
    assert tab.start_job("13", "BIM Tech", "C") is True
    assert calls == [("hybrid_apply.py", ["--job", "13"])]
    assert "BIM Tech" in tab.job_label.text() and tab.job_box.isVisibleTo(tab)
    monkeypatch.setattr(runner, "is_running", lambda: True)
    assert tab.start_job("14", "Other", "D") is False and len(calls) == 1
    assert "already in progress" in tab.status.text()
    runner.line.emit(">>> Applying to #1: [-] Some Job | Co")          # jobs with no fit score show without a number
    assert tab.job_label.text() == "Some Job | Co"


def test_main_window_auto_apply_switches_to_run_tab(app, monkeypatch):
    from desktop.main_window import MainWindow
    _fake_jobs(monkeypatch)
    w = MainWindow()
    calls = []
    monkeypatch.setattr("desktop.preflight.check", lambda **k: [])
    monkeypatch.setattr(w.runner, "start", lambda script, args=(): calls.append((script, list(args))))
    monkeypatch.setattr(w.runner, "is_running", lambda: False)
    w.tabs.setCurrentWidget(w.jobs_tab)
    w.jobs_tab.refresh()
    w.jobs_tab.table.cellWidget(0, 4).click()
    assert w.tabs.currentWidget() is w.run_tab
    assert calls == [("hybrid_apply.py", ["--job", "11"])]
    w.close()


def test_auto_submit_is_off_by_default_and_needs_a_confirmed_click(app, monkeypatch):
    from desktop.tabs import RunTab
    from PySide6.QtWidgets import QMessageBox
    tab = RunTab(BotRunner())
    assert not tab.auto_submit.isChecked() and "--auto-submit" not in tab.args()
    assert tab.pause_review.isChecked() and not tab.pause_review.isEnabled()
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.No)       # user says No
    tab.auto_submit.click()
    assert not tab.auto_submit.isChecked() and "--auto-submit" not in tab.args()
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Yes)      # user says Yes
    tab.auto_submit.click()
    assert tab.auto_submit.isChecked() and tab.pause_review.isEnabled()
    a = tab.args()
    assert "--auto-submit" in a and "--no-review-pause" not in a
    tab.pause_review.setChecked(False)
    assert "--no-review-pause" in tab.args()
    tab.list_only.setChecked(True)
    assert "--auto-submit" not in tab.args()                                          # list-only never submits
