"""The five tabs of the desktop app: Run, Jobs, Answers, Profile, Settings."""
import os, re, sys

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QScrollArea,
                               QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

import app_settings
import secure_store
from job_lookup import parse_job_link
from desktop import data
from desktop import preflight
from desktop.runner import BotRunner, ROOT

MONO = QFont("Consolas", 9)


def open_folder(path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


# ====================================================================================== Run
STATUS_RULES = [                                   # (text in the bot's output, status line to show)
    ("Logging in", "Signing in to LinkedIn..."),
    ("Searching", "Searching LinkedIn..."),
    ("RANKED", "Jobs ranked. Opening the best fit..."),
    (">>> Applying to", "Opening the next job..."),
    ("Form open", "Filling in the application..."),
    ("AUTO-SUBMIT HELD BACK", "WAITING FOR YOU: this application needs a look before it is submitted (see the log)"),
    ("AUTO-SUBMIT: submitting", "Submitting automatically..."),
    ("SUBMIT PAGE reached", "WAITING FOR YOU: read the answers, then click 'Submit application' in the Chrome window (or close the form to skip)"),
    ("STOPPED:", "Stopped: LinkedIn needs you (see the log)"),
    ("Daily cap reached", "Daily application cap reached"),
    ("Done.", "Finished"),
]


class JobDetailsDialog(QDialog):
    """The posting the bot is applying to (read from LinkedIn when the job was scored), so you can read it before you submit."""
    def __init__(self, job, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Job details")
        self.resize(780, 640)
        lay = QVBoxLayout(self)
        if not job:
            lay.addWidget(QLabel("No job details yet. They appear once the bot opens an application."))
        else:
            head = QLabel(f'<b style="font-size:15pt">{job.get("title", "")}</b><br>{job.get("company", "")}  |  {job.get("location", "")}')
            head.setTextFormat(Qt.RichText); head.setWordWrap(True); lay.addWidget(head)
            if job.get("fit") is not None:
                why = QLabel(f'<b>Fit {job["fit"]}</b>: {job.get("reason", "")}'); why.setWordWrap(True); lay.addWidget(why)
            text = QPlainTextEdit(); text.setReadOnly(True)
            about = job.get("about") or ""
            text.setPlainText((job.get("description") or "(the posting text was not captured)") + (f"\n\n----- About the company -----\n{about}" if about else ""))
            lay.addWidget(text, 1)
        row = QHBoxLayout()
        if job and job.get("link"):
            openb = QPushButton("Open on LinkedIn"); openb.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(job["link"]))); row.addWidget(openb)
        row.addStretch(1)
        close = QPushButton("Close"); close.clicked.connect(self.accept); row.addWidget(close)
        lay.addLayout(row)


class RunTab(QWidget):
    run_finished = Signal()

    def __init__(self, runner: BotRunner):
        super().__init__()
        self.runner = runner
        s = app_settings.load()

        self.max_jobs = QSpinBox(); self.max_jobs.setMaximumWidth(120); self.max_jobs.setRange(1, 25); self.max_jobs.setValue(int(s["max_jobs"]))
        self.min_fit = QSpinBox(); self.min_fit.setMaximumWidth(120); self.min_fit.setRange(0, 100); self.min_fit.setValue(int(s["min_fit"]))
        self.candidates = QSpinBox(); self.candidates.setMaximumWidth(120); self.candidates.setRange(5, 100); self.candidates.setValue(int(s["candidates"]))
        self.list_only = QCheckBox("List and rank only (open no forms)")
        self.retry_low = QCheckBox("Score earlier low-fit jobs again")
        self.no_ai = QCheckBox("No AI answers (use only my saved answers)")
        self.auto_submit = QCheckBox("Submit automatically and move on to the next form")
        self.auto_submit.setToolTip("OFF by default. When ON the bot clicks Submit for you instead of waiting. You are responsible for every application it sends.")
        self.pause_review = QCheckBox("Still stop and wait for me when an answer needs a look"); self.pause_review.setChecked(True)
        self.pause_review.setToolTip("Recommended. Holds back an application with blank questions, guessed years, or AI-written answers about credentials, work status or background")
        self.pause_review.setEnabled(False)

        spins = QHBoxLayout(); spins.setSpacing(10)
        for label, w in (("Forms to open", self.max_jobs), ("Minimum fit (0-100)", self.min_fit), ("Jobs to score", self.candidates)):
            spins.addWidget(QLabel(label)); spins.addWidget(w); spins.addSpacing(18)
        spins.addStretch(1)
        box = QGroupBox("This run")
        inner = QVBoxLayout(box); inner.setSpacing(8); inner.addLayout(spins)
        checks = QGridLayout(); checks.setHorizontalSpacing(28); checks.setVerticalSpacing(6)
        checks.addWidget(self.list_only, 0, 0); checks.addWidget(self.retry_low, 0, 1)
        checks.addWidget(self.no_ai, 1, 0); checks.addWidget(self.auto_submit, 1, 1)
        checks.addWidget(self.pause_review, 2, 1)
        checks.setColumnStretch(2, 1)
        inner.addLayout(checks)

        self.start_btn = QPushButton("Start"); self.start_btn.setObjectName("primary"); self.start_btn.setDefault(True)
        self.stop_btn = QPushButton("Stop"); self.stop_btn.setObjectName("danger"); self.stop_btn.setEnabled(False)
        self.status = QLabel("Ready. By default the bot never clicks Submit: you do, in the Chrome window (unless you turn on auto-submit).")
        self.status.setWordWrap(True); self.status.setObjectName("status")

        self.ask = QLabel(""); self.ask.setWordWrap(True)
        self.yes_btn = QPushButton("I submitted it"); self.no_btn = QPushButton("Not submitted, continue")
        self.quit_btn = QPushButton("Quit the run")
        bar = QHBoxLayout()
        for b in (self.yes_btn, self.no_btn, self.quit_btn): bar.addWidget(b)
        self.ask_box = QGroupBox("The bot is asking")
        al = QVBoxLayout(self.ask_box); al.addWidget(self.ask); al.addLayout(bar)
        self.ask_box.setVisible(False)

        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setFont(MONO); self.log.setMaximumBlockCount(6000)

        # the job being applied to right now, with buttons to read the posting before you submit
        self.job_link = ""
        self.job_label = QLabel(""); self.job_label.setWordWrap(True)
        self.open_btn = QPushButton("Open job listing")
        self.details_btn = QPushButton("Read job details here")
        self.open_btn.setToolTip("Opens the LinkedIn posting in a new tab of your default browser")
        jb = QHBoxLayout(); jb.addWidget(self.open_btn); jb.addWidget(self.details_btn); jb.addStretch(1)
        self.job_box = QGroupBox("Current application")
        jl = QVBoxLayout(self.job_box); jl.addWidget(self.job_label); jl.addLayout(jb)
        self.job_box.setVisible(False)

        top = QHBoxLayout(); top.addWidget(box, 1)
        side = QVBoxLayout(); side.addWidget(self.start_btn); side.addWidget(self.stop_btn); side.addStretch(1)
        top.addLayout(side)
        self.log.setMinimumHeight(200)
        body = QWidget(); body.setAutoFillBackground(False)
        root = QVBoxLayout(body); root.setContentsMargins(0, 0, 6, 0)
        root.addLayout(top); root.addWidget(self.status); root.addWidget(self.job_box); root.addWidget(self.ask_box); root.addWidget(self.log, 1)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame); scroll.setWidget(body)   # scrolls instead of squashing on a small window
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }"); scroll.viewport().setAutoFillBackground(False)
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.addWidget(scroll)
        self.open_btn.clicked.connect(self.open_listing)
        self.details_btn.clicked.connect(self.show_details)

        self.start_btn.clicked.connect(self.start)
        self.auto_submit.clicked.connect(self._auto_submit_clicked)
        self.stop_btn.clicked.connect(self.runner.stop)
        self.yes_btn.clicked.connect(lambda: self._answer("y"))
        self.no_btn.clicked.connect(lambda: self._answer(""))
        self.quit_btn.clicked.connect(lambda: self._answer("q"))
        runner.line.connect(self._on_line)
        runner.prompt.connect(self._on_prompt)
        runner.started.connect(lambda: self._running(True))
        runner.finished.connect(self._on_finished)

    def args(self):
        a = ["--max-jobs", str(self.max_jobs.value()), "--min-fit", str(self.min_fit.value()), "--candidates", str(self.candidates.value())]
        if self.list_only.isChecked(): a.append("--list-only")
        if self.retry_low.isChecked(): a.append("--retry-low")
        if self.no_ai.isChecked(): a.append("--no-ai")
        if self.auto_submit.isChecked() and not self.list_only.isChecked():
            a.append("--auto-submit")
            if not self.pause_review.isChecked(): a.append("--no-review-pause")
        return a

    def _auto_submit_clicked(self, on):
        """Turning automatic submission on needs a clear yes: the bot then sends applications without you reading them."""
        if on:
            ans = QMessageBox.warning(
                self, "Submit automatically?",
                "With this ON the bot clicks 'Submit application' for you and moves on to the next job, without waiting for you to read it.\n\n"
                "The answers are written by an AI from your facts and can be wrong, and a submitted application cannot be taken back. "
                "You are responsible for everything it sends.\n\nTurn automatic submit on for this run?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ans != QMessageBox.Yes:
                self.auto_submit.setChecked(False); on = False
        self.pause_review.setEnabled(on)

    RUN_FIELDS = ("max_jobs", "min_fit", "candidates")
    RUN_FLAGS = ("list_only", "retry_low", "no_ai")          # auto_submit is deliberately NOT remembered: it must be turned on each time

    def state(self):
        s = {k: getattr(self, k).value() for k in self.RUN_FIELDS}
        s.update({k: getattr(self, k).isChecked() for k in self.RUN_FLAGS})
        return s

    def restore(self, s):
        for k in self.RUN_FIELDS:
            if isinstance(s.get(k), int): getattr(self, k).setValue(s[k])
        for k in self.RUN_FLAGS:
            if isinstance(s.get(k), bool): getattr(self, k).setChecked(s[k])

    def _preflight_ok(self, no_ai=False):
        """Tell the user about missing setup (AI key, facts, resume) before Chrome opens; they may start anyway."""
        problems = preflight.check(no_ai=no_ai)
        if not problems:
            return True
        ans = QMessageBox.question(self, "Before you start",
                                   "A few things are not set up yet:\n\n- " + "\n- ".join(problems) + "\n\nStart anyway?",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans != QMessageBox.Yes:
            self.status.setText("Not started: " + problems[0])
            return False
        return True

    def start(self):
        if not self._preflight_ok(self.no_ai.isChecked()): return
        self.log.clear(); self._reset_saved_log()
        self.status.setText("Starting...")
        self.runner.start("hybrid_apply.py", self.args())

    def start_job(self, job_id, title="", company=""):
        """Auto apply to one job from the Jobs tab: fill the form and stop at Submit. Returns False if a run is already going."""
        if self.runner.is_running():
            self.status.setText("A run is already in progress. Stop it or let it finish, then try again.")
            return False
        if not self._preflight_ok(): return False
        self.log.clear(); self._reset_saved_log(); self.job_link = ""
        self.job_label.setText(f"{title}  |  {company}" if title else f"LinkedIn job {job_id}")
        self.job_box.setVisible(True); self.open_btn.setEnabled(False); self.details_btn.setEnabled(False)
        self.status.setText("Starting auto apply for this job...")
        self.runner.start("hybrid_apply.py", ["--job", str(job_id)])
        return True

    def _running(self, on):
        self.start_btn.setEnabled(not on); self.stop_btn.setEnabled(on)
        for w in (self.max_jobs, self.min_fit, self.candidates, self.list_only, self.retry_low, self.no_ai, self.auto_submit): w.setEnabled(not on)
        self.pause_review.setEnabled(not on and self.auto_submit.isChecked())

    def open_listing(self):
        """Open the current job's LinkedIn posting in a new browser tab (your default browser)."""
        if self.job_link:
            QDesktopServices.openUrl(QUrl(self.job_link))

    def show_details(self):
        JobDetailsDialog(data.read_current_job(), self).exec()

    def _on_line(self, text):
        self.log.appendPlainText(text)
        self._save_log_line(text)
        if text.startswith("ERROR:"):
            self.last_error = text
        m = re.search(r">>> Applying to #\d+: \[([^\]]*)\] (.+)$", text)
        if m:
            self.job_label.setText(f"Fit {m.group(1)}:  {m.group(2)}" if m.group(1).strip().isdigit() else m.group(2))
            self.job_link = ""; self.job_box.setVisible(True); self.open_btn.setEnabled(False); self.details_btn.setEnabled(False)
        m = re.search(r"job-link: (https://\S+)", text)
        if m:
            self.job_link = m.group(1)
            self.job_box.setVisible(True); self.open_btn.setEnabled(True); self.details_btn.setEnabled(True)
            if not self.job_label.text():
                self.job_label.setText(self.job_link)
        for needle, status in STATUS_RULES:
            if needle in text:
                self.status.setText(status); break

    def _reset_saved_log(self):
        try:
            os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
            open(os.path.join(ROOT, "logs", "last_run.log"), "w", encoding="utf-8").close()
        except OSError:
            pass

    def _save_log_line(self, text):
        """Keep the latest run's output in logs/last_run.log (local, git-ignored) so it survives a crash or a closed window."""
        try:
            path = os.path.join(ROOT, "logs", "last_run.log")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f: f.write(text + "\n")
        except OSError:
            pass

    def _on_prompt(self, text):
        asking_submit = "submit" in text.lower()
        self.ask.setText(text)
        self.yes_btn.setVisible(asking_submit)
        self.no_btn.setText("Not submitted, continue" if asking_submit else "Continue to the next job")
        self.ask_box.setVisible(True)
        self.status.setText("The bot is waiting for your answer below.")
        QApplication.alert(self.window(), 0)            # flash the taskbar button so you notice from another window

    def _answer(self, text):
        self.ask_box.setVisible(False)
        self.runner.answer(text)
        self.status.setText("Working...")

    def _on_finished(self, code):
        self._running(False); self.ask_box.setVisible(False)
        if "Finished" not in self.status.text() and "Stopped" not in self.status.text():
            err = getattr(self, "last_error", "")
            self.status.setText("Finished." if code == 0 else (f"The run stopped. {err}" if err else f"The run ended (exit code {code}). See the log."))
        self.last_error = ""
        self.run_finished.emit()


# ====================================================================================== Jobs
class JobsTab(QWidget):
    apply_requested = Signal(str, str, str)        # job id, title, company
    link_requested = Signal(str, str, str)         # job id, title, company of a job added from a pasted link (title may be empty)

    def __init__(self):
        super().__init__()
        self.link_edit = QLineEdit(); self.link_edit.setPlaceholderText("Paste a LinkedIn job link here to add it and auto apply...")
        self.link_edit.setClearButtonEnabled(True)
        self.link_btn = QPushButton("Add and auto apply")
        self.link_btn.setToolTip("Adds the job to this list, opens it, fills the form and stops at the Submit page for you to review")
        self.link_msg = QLabel(""); self.link_msg.setObjectName("status")
        link_row = QHBoxLayout(); link_row.addWidget(self.link_edit, 1); link_row.addWidget(self.link_btn)
        self.link_edit.returnPressed.connect(self.add_from_link); self.link_btn.clicked.connect(self.add_from_link)
        self.filter = QComboBox(); self.filter.addItems(["All", "Submitted", "Opened, not submitted", "Skipped or low fit", "Scored only"])
        self.refresh_btn = QPushButton("Refresh")
        self.mark_btn = QPushButton("Mark selected as submitted")
        self.mark_btn.setToolTip("Fix the record if you submitted a job that the log shows as not submitted")
        self.count = QLabel("")
        self.search = QLineEdit(); self.search.setPlaceholderText("Search title, company or notes..."); self.search.setClearButtonEnabled(True); self.search.setMinimumWidth(240)
        top = QHBoxLayout(); top.addWidget(QLabel("Show:")); top.addWidget(self.filter); top.addWidget(self.search); top.addWidget(self.refresh_btn); top.addWidget(self.mark_btn); top.addStretch(1); top.addWidget(self.count)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Fit", "Job", "Company", "Status", "Action", "Why"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        h = self.table.horizontalHeader(); h.setStretchLastSection(True)
        for col, width in ((0, 56), (1, 250), (2, 150), (3, 210), (4, 112)):
            h.setSectionResizeMode(col, QHeaderView.Interactive); self.table.setColumnWidth(col, width)
        self.table.verticalHeader().setVisible(False); self.table.verticalHeader().setDefaultSectionSize(40)
        hint = QLabel("Double-click a job to open it on LinkedIn. Auto apply fills the form and stops at Submit for you to review. Have a job link? Paste it above.")
        lay = QVBoxLayout(self); lay.addLayout(link_row); lay.addWidget(self.link_msg); lay.addLayout(top); lay.addWidget(self.table, 1); lay.addWidget(hint)
        self.link_msg.setVisible(False)
        self._sort = (0, Qt.DescendingOrder)                # best fit first, like the log
        h.setSectionsClickable(True); h.setSortIndicatorShown(True); h.setSortIndicator(0, Qt.DescendingOrder)
        h.sectionClicked.connect(self._sort_by)
        self.search.textChanged.connect(self.refresh)
        self.refresh_btn.clicked.connect(self.refresh); self.filter.currentIndexChanged.connect(self.refresh)
        self.mark_btn.clicked.connect(self.mark_submitted)
        self.table.cellDoubleClicked.connect(self._open)
        self._jobs = []
        self.refresh()

    @staticmethod
    def _bucket(status):
        s = (status or "").lower()
        if s.startswith("applied"): return "Submitted"
        if s.startswith("skipped") or s.startswith("low fit") or s.startswith("could not"): return "Skipped or low fit"
        if s == "scored": return "Scored only"
        return "Opened, not submitted"

    SORT_KEYS = {0: lambda j: j["score"] if j["score"] is not None else -1, 1: lambda j: j["title"].lower(), 2: lambda j: j["company"].lower(),
                 3: lambda j: j["status"].lower(), 5: lambda j: (j.get("reason") or "").lower()}

    def _sort_by(self, col):
        """Click a column header to sort by it; click again to reverse. (The Action column is not sortable.)"""
        if col not in self.SORT_KEYS: return
        order = Qt.AscendingOrder if (self._sort[0] == col and self._sort[1] == Qt.DescendingOrder) else Qt.DescendingOrder
        if col != 0 and self._sort[0] != col: order = Qt.AscendingOrder        # text columns start A to Z; Fit starts high to low
        self._sort = (col, order)
        self.table.horizontalHeader().setSortIndicator(col, order)
        self.refresh()

    def state(self):
        return {"filter": self.filter.currentText(), "search": self.search.text(), "sort": [self._sort[0], 1 if self._sort[1] == Qt.DescendingOrder else 0]}

    def restore(self, s):
        if s.get("filter") in [self.filter.itemText(i) for i in range(self.filter.count())]: self.filter.setCurrentText(s["filter"])
        if isinstance(s.get("search"), str): self.search.setText(s["search"])
        sort = s.get("sort")
        if isinstance(sort, list) and len(sort) == 2 and sort[0] in self.SORT_KEYS:
            self._sort = (sort[0], Qt.DescendingOrder if sort[1] else Qt.AscendingOrder)
            self.table.horizontalHeader().setSortIndicator(*self._sort)
        self.refresh()

    def refresh(self):
        want = self.filter.currentText()
        needle = self.search.text().strip().lower()
        jobs = [j for j in data.load_jobs() if want == "All" or self._bucket(j["status"]) == want]
        if needle:
            jobs = [j for j in jobs if needle in " ".join([j["title"], j["company"], j["status"], j.get("reason") or ""]).lower()]
        col, order = self._sort
        jobs.sort(key=self.SORT_KEYS[col], reverse=(order == Qt.DescendingOrder))
        self._jobs = jobs
        self.table.setRowCount(len(self._jobs))
        for r, j in enumerate(self._jobs):
            why = j.get("reason") or (j["status"].split(":", 1)[1].strip() if ":" in j["status"] else "")
            cells = [str(j["score"]) if j["score"] is not None else "", j["title"], j["company"], j["status"].split(":", 1)[0].strip(), "", why]
            submitted = self._bucket(j["status"]) == "Submitted"
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text); item.setToolTip(j["status"] if c == 3 else (why or text))
                if c == 0: item.setTextAlignment(Qt.AlignCenter)
                if submitted: item.setBackground(QColor(70, 210, 140, 70))
                self.table.setItem(r, c, item)
            if not submitted:                       # every job you have not applied to gets an Auto apply button
                btn = QPushButton("Auto apply"); btn.setObjectName("rowbtn")
                btn.setToolTip("Opens this job, fills the form and stops at the Submit page for you to review")
                btn.clicked.connect(lambda _=False, jj=j: self.apply_requested.emit(str(jj["id"]), jj.get("title", ""), jj.get("company", "")))
                self.table.setCellWidget(r, 4, btn)
            else:
                self.table.removeCellWidget(r, 4)
        self.count.setText(f"{len(self._jobs)} jobs")

    def add_from_link(self):
        """Take the pasted LinkedIn job link, check it, and ask for a single-job auto apply (it stops at Submit)."""
        job_id = parse_job_link(self.link_edit.text())
        if not job_id:
            self._link_note("That does not look like a LinkedIn job link. Copy it from the job page, for example https://www.linkedin.com/jobs/view/1234567890/")
            return
        known = next((j for j in data.load_jobs() if j["id"] == job_id), None)
        if known and self._bucket(known["status"]) == "Submitted":
            ans = QMessageBox.question(self, "Already submitted",
                                       f"This job is already recorded as submitted:\n\n{known['title']} | {known['company']}\n\nOpen it again anyway?",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ans != QMessageBox.Yes:
                return
        self._link_note("")
        self.link_requested.emit(job_id, (known or {}).get("title", ""), (known or {}).get("company", ""))

    def _link_note(self, text):
        self.link_msg.setText(text); self.link_msg.setVisible(bool(text))

    def mark_submitted(self):
        rows = sorted({i.row() for i in self.table.selectedItems()})
        for r in rows:
            if 0 <= r < len(self._jobs):
                j = self._jobs[r]
                data.set_history_status(j["id"], "applied (marked by you)", j.get("title", ""), j.get("company", ""))
        self.refresh()

    def _open(self, row, _col):
        if 0 <= row < len(self._jobs): QDesktopServices.openUrl(QUrl(self._jobs[row]["link"]))


# ====================================================================================== Answers
class AnswersTab(QWidget):
    def __init__(self):
        super().__init__()
        self.mem = QTableWidget(0, 3); self.mem.setHorizontalHeaderLabels(["Question", "My answer", "Type"])
        self.mem.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch); self.mem.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.mem.verticalHeader().setVisible(False)
        add, rm, save = QPushButton("Add"), QPushButton("Delete selected"), QPushButton("Save answers")
        bar = QHBoxLayout(); [bar.addWidget(b) for b in (add, rm, save)]; bar.addStretch(1)
        self.saved_label = QLabel("")
        g1 = QGroupBox("Answers I want reused (matched by question; they beat the AI and my config)")
        l1 = QVBoxLayout(g1); l1.addWidget(self.mem); l1.addLayout(bar); l1.addWidget(self.saved_label)

        self.apps = QComboBox()
        self.log_table = QTableWidget(0, 4); self.log_table.setHorizontalHeaderLabels(["Question", "Answer sent", "Source", "Needs a look because"])
        self.log_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.log_table.verticalHeader().setVisible(False)
        for c in (0, 1, 3): self.log_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.Stretch)
        g2 = QGroupBox("What was filled in on recent applications")
        l2 = QVBoxLayout(g2); l2.addWidget(self.apps); l2.addWidget(self.log_table)

        lay = QVBoxLayout(self); lay.addWidget(g1, 1); lay.addWidget(g2, 1)
        add.clicked.connect(self._add); rm.clicked.connect(self._delete); save.clicked.connect(self._save)
        self.apps.currentIndexChanged.connect(self._show_app)
        self._apps = []
        self.refresh()

    def refresh(self):
        rows = data.load_memory()
        self.mem.setRowCount(len(rows))
        for r, row in enumerate(rows):
            q = QTableWidgetItem(row["question"]); q.setData(Qt.UserRole, row["saved"])
            k = QTableWidgetItem(row["kind"]); k.setFlags(k.flags() & ~Qt.ItemIsEditable)
            self.mem.setItem(r, 0, q); self.mem.setItem(r, 1, QTableWidgetItem(row["answer"])); self.mem.setItem(r, 2, k)
        self._apps = data.recent_applications()
        self.apps.blockSignals(True); self.apps.clear()
        for a in self._apps:
            self.apps.addItem(f'{(a.get("time") or "")[:16]}   {a.get("title") or ""}  |  {a.get("company") or ""}')
        self.apps.blockSignals(False)
        self._show_app()

    def _show_app(self):
        i = self.apps.currentIndex()
        answers = self._apps[i]["answers"] if 0 <= i < len(self._apps) else []
        self.log_table.setRowCount(len(answers))
        for r, a in enumerate(answers):
            vals = [a.get("q", ""), a.get("a", ""), a.get("source", ""), "; ".join(a.get("flags", []))]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v[:400]); item.setToolTip(v)
                if a.get("flags"): item.setBackground(QColor(255, 190, 70, 60))
                self.log_table.setItem(r, c, item)

    def _add(self):
        r = self.mem.rowCount(); self.mem.insertRow(r)
        self.mem.setItem(r, 0, QTableWidgetItem("")); self.mem.setItem(r, 1, QTableWidgetItem("")); self.mem.setItem(r, 2, QTableWidgetItem("text"))
        self.mem.editItem(self.mem.item(r, 0))

    def _delete(self):
        for r in sorted({i.row() for i in self.mem.selectedItems()}, reverse=True): self.mem.removeRow(r)

    def _save(self):
        rows = []
        for r in range(self.mem.rowCount()):
            q, a, k = (self.mem.item(r, c).text() if self.mem.item(r, c) else "" for c in range(3))
            rows.append({"question": q, "answer": a, "kind": k or "text", "saved": self.mem.item(r, 0).data(Qt.UserRole) if self.mem.item(r, 0) else None})
        data.save_memory(rows)
        self.saved_label.setText(f"Saved {len([r for r in rows if r['question'].strip() and r['answer'].strip()])} answers.")


# ====================================================================================== Profile
class ProfileTab(QWidget):
    def __init__(self):
        super().__init__()
        self.facts = QPlainTextEdit(); self.facts.setFont(MONO)
        self.cover = QPlainTextEdit(); self.cover.setFont(MONO)
        tabs = QTabWidget()
        tabs.addTab(self._page(self.facts, data.PROFILE, "The AI may use ONLY the facts written here. If a question needs something that is not here, it leaves it blank for you."), "My facts")
        tabs.addTab(self._page(self.cover, data.COVER, "Write your own cover letter. For each job the AI keeps your voice and structure and swaps in the company, role and a company-specific paragraph built from the posting."), "Cover letter")
        lay = QVBoxLayout(self); lay.addWidget(tabs)
        folder = QPushButton("Open the config folder"); folder.clicked.connect(lambda: open_folder(data.CONFIG)); lay.addWidget(folder)
        self.facts.setPlainText(data.read_text(data.PROFILE)); self.cover.setPlainText(data.read_text(data.COVER))

    def _page(self, editor, path, hint):
        w = QWidget(); l = QVBoxLayout(w)
        note = QLabel(hint); note.setWordWrap(True); l.addWidget(note); l.addWidget(editor, 1)
        row = QHBoxLayout(); save = QPushButton("Save"); label = QLabel(""); row.addWidget(save); row.addWidget(label); row.addStretch(1); l.addLayout(row)
        def do_save():
            data.write_text(path, editor.toPlainText()); label.setText(f"Saved {os.path.basename(path)}")
        save.clicked.connect(do_save)
        return w


# ====================================================================================== Settings
class OutputDialog(QDialog):
    """Runs a script and shows its output (used for the health check and the AI key test)."""
    def __init__(self, title, script, args=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle(title); self.resize(760, 420)
        self.text = QPlainTextEdit(); self.text.setReadOnly(True); self.text.setFont(MONO)
        close = QPushButton("Close")
        lay = QVBoxLayout(self); lay.addWidget(self.text); lay.addWidget(close)
        self.runner = BotRunner(self)
        self.runner.line.connect(self.text.appendPlainText)
        self.runner.finished.connect(lambda code: self.text.appendPlainText(f"\n[finished, exit code {code}]"))
        close.clicked.connect(self.accept)
        self.runner.start(script, args)

    def done(self, r):
        self.runner.stop(); super().done(r)


class SettingsTab(QWidget):
    INTS = [("min_fit", "Minimum fit to apply (0-100)", 0, 100), ("candidates", "Jobs to score per run", 5, 200), ("per_term", "Jobs examined per search title", 1, 50),
            ("ai_terms", "Search titles the AI chooses", 0, 20), ("max_years", "Skip postings requiring this many years or more", 1, 30),
            ("max_jobs", "Forms to open per run", 1, 25), ("daily_cap", "Daily submitted-application cap (0 = none)", 0, 100)]
    BOOLS = [("allow_senior", "Allow Senior / Lead / Manager / Director titles"), ("years_default_fallback", "When my facts have no years figure, answer with my default years"),
             ("persistent_profile", "Keep the bot's Chrome signed in between runs"), ("sort_recent", "Newest postings first")]

    def __init__(self):
        super().__init__()
        s = app_settings.load()
        form = QFormLayout()
        self.ints, self.bools = {}, {}
        for key, label, lo, hi in self.INTS:
            w = QSpinBox(); w.setMaximumWidth(120); w.setRange(lo, hi); w.setValue(int(s[key])); self.ints[key] = w; form.addRow(label, w)
        for key, label in self.BOOLS:
            w = QCheckBox(label); w.setChecked(bool(s[key])); self.bools[key] = w; form.addRow("", w)
        self.cover = QComboBox(); self.cover.addItems(["ai", "off"]); self.cover.setCurrentText(s["cover_letter"]); form.addRow("Cover letters", self.cover)
        self.resume = QLineEdit(s["preferred_resume"]); self.resume.setPlaceholderText("part of a resume file name; empty = keep LinkedIn's choice"); form.addRow("Preferred resume", self.resume)
        self.rules = QPlainTextEdit("\n".join(f"{a} => {b}" for a, b in s["resume_rules"])); self.rules.setFixedHeight(70)
        self.rules.setPlaceholderText("one per line:  job title regex => resume name regex     e.g.  artist => 3D Artist"); form.addRow("Resume rules", self.rules)
        self.blocked = QLineEdit(", ".join(s["blocked_companies"])); self.blocked.setPlaceholderText("companies to never apply to, comma separated"); form.addRow("Blocked companies", self.blocked)
        save = QPushButton("Save settings"); self.saved = QLabel("")
        row = QHBoxLayout(); row.addWidget(save); row.addWidget(self.saved); row.addStretch(1)
        g1 = QGroupBox("Search, answers and safety"); l1 = QVBoxLayout(g1); l1.addLayout(form); l1.addLayout(row)

        self.fields = {}
        sec = QFormLayout()
        for name, label, echo in (("llm_api_key", "AI API key", True), ("linkedin_username", "LinkedIn email (optional)", False), ("linkedin_password", "LinkedIn password (optional)", True)):
            edit = QLineEdit(); edit.setEchoMode(QLineEdit.Password if echo else QLineEdit.Normal)
            status = QLabel(); self.fields[name] = (edit, status)
            r = QHBoxLayout(); r.addWidget(edit, 1); r.addWidget(status); sec.addRow(label, r)
        vault_save = QPushButton("Save to the Windows vault"); vault_note = QLabel("Stored in Windows Credential Manager, never in a file. Leave a box empty to keep what is stored.")
        vault_note.setWordWrap(True)
        g2 = QGroupBox("Secrets"); l2 = QVBoxLayout(g2); l2.addLayout(sec); l2.addWidget(vault_save); l2.addWidget(vault_note)

        tools = QHBoxLayout()
        test_ai = QPushButton("Test the AI key"); health = QPushButton("Check LinkedIn still works"); folder = QPushButton("Open project folder")
        for b in (test_ai, health, folder): tools.addWidget(b)
        tools.addStretch(1)

        inner = QWidget(); lay = QVBoxLayout(inner); lay.addWidget(g1); lay.addWidget(g2); lay.addLayout(tools); lay.addStretch(1)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame); scroll.setWidget(inner)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }"); scroll.viewport().setAutoFillBackground(False); inner.setAutoFillBackground(False)
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.addWidget(scroll)
        save.clicked.connect(self.save); vault_save.clicked.connect(self.save_secrets)
        test_ai.clicked.connect(lambda: OutputDialog("Test the AI key", "-c", ["from modules.ai.connections import create_ai_client; c=create_ai_client(); print('AI answered:', c.model.invoke('Say OK').content if c else 'no client (check provider and key)')"], self).exec())
        health.clicked.connect(lambda: OutputDialog("Check LinkedIn still works", "health_check.py", [], self).exec())
        folder.clicked.connect(lambda: open_folder(ROOT))
        self.refresh_secret_status()

    def values(self):
        v = {k: w.value() for k, w in self.ints.items()}
        v.update({k: w.isChecked() for k, w in self.bools.items()})
        v["cover_letter"] = self.cover.currentText()
        v["preferred_resume"] = self.resume.text().strip()
        v["blocked_companies"] = [x.strip() for x in self.blocked.text().split(",") if x.strip()]
        v["resume_rules"] = [[p.strip() for p in ln.split("=>", 1)] for ln in self.rules.toPlainText().splitlines() if "=>" in ln]
        return v

    def save(self):
        merged = app_settings.load(); merged.update(self.values()); app_settings.save(merged)
        self.saved.setText("Saved. New settings apply the next time you press Start.")

    def refresh_secret_status(self):
        for name, (edit, status) in self.fields.items():
            ok = bool(secure_store.get(name))
            status.setText("stored" if ok else "not set"); status.setStyleSheet("color: #7dffb0" if ok else "color: rgba(238,242,255,0.45)")

    def save_secrets(self):
        for name, (edit, _status) in self.fields.items():
            if edit.text().strip():
                secure_store.set(name, edit.text().strip()); edit.clear()
        self.refresh_secret_status()
