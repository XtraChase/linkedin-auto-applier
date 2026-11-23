"""Main window: a glass header and five tabs."""
import os, sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QTabWidget, QVBoxLayout, QWidget)

from desktop import theme
from desktop.runner import BotRunner
from desktop.tabs import AnswersTab, JobsTab, ProfileTab, RunTab, SettingsTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LinkedIn Auto Applier")
        self.resize(1120, 780)
        self.setMinimumSize(940, 660)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.runner = BotRunner(self)
        self.root = theme.GlassRoot()
        self.setCentralWidget(self.root)

        title = QLabel("LinkedIn Auto Applier"); title.setObjectName("title")
        sub = QLabel("Finds the jobs that fit you and fills the application. It stops at Submit so you decide, unless you turn on auto-submit.")
        sub.setObjectName("subtitle")
        head = QVBoxLayout(); head.setSpacing(2); head.addWidget(title); head.addWidget(sub)

        self.run_tab, self.jobs_tab, self.answers_tab = RunTab(self.runner), JobsTab(), AnswersTab()
        self.profile_tab, self.settings_tab = ProfileTab(), SettingsTab()
        self.tabs = QTabWidget(); self.tabs.setDocumentMode(True)
        for w, name in ((self.run_tab, "Run"), (self.jobs_tab, "Jobs"), (self.answers_tab, "Answers"),
                        (self.profile_tab, "Profile"), (self.settings_tab, "Settings")):
            self.tabs.addTab(w, name)
        try:                                      # APP_START_TAB=1 opens the Jobs tab first (handy for screenshots)
            import os; self.tabs.setCurrentIndex(int(os.environ.get("APP_START_TAB", "0")))
        except ValueError:
            pass
        self.jobs_tab.apply_requested.connect(self._auto_apply)
        self.run_tab.run_finished.connect(self.jobs_tab.refresh)
        self.run_tab.run_finished.connect(self.answers_tab.refresh)

        lay = QVBoxLayout(self.root); lay.setContentsMargins(26, 20, 26, 20); lay.setSpacing(10)
        lay.addLayout(head); lay.addWidget(self.tabs, 1)

    def _auto_apply(self, job_id, title, company):
        """Jobs tab 'Auto apply': start the single-job run and show the Run tab so you can follow it."""
        self.tabs.setCurrentWidget(self.run_tab)
        self.run_tab.start_job(job_id, title, company)

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_backdrop_done", False):
            self._backdrop_done = True
            self.root.set_backdrop(theme.apply_backdrop(self))

    def closeEvent(self, event):
        if self.runner.is_running():
            ans = QMessageBox.question(self, "A run is in progress", "Stop the run and close the app? The bot's Chrome window will be closed too.")
            if ans != QMessageBox.Yes:
                event.ignore(); return
            self.runner.stop()
        event.accept()


def _icon_file():
    """The multi-size icon if it has been made (make_icon.py), else the original."""
    import app_paths
    multi = os.path.join(app_paths.assets_dir(), "LinkedInAutoApplierIcon_multi.ico")
    return multi if os.path.exists(multi) else os.path.join(app_paths.assets_dir(), "LinkedInAutoApplierIcon.ico")


def run():
    app = QApplication.instance() or QApplication(sys.argv)
    import app_paths
    from PySide6.QtGui import QIcon
    if sys.platform == "win32":                 # own taskbar identity, so the taskbar shows this app's icon (not Python's)
        try:
            import ctypes; ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("XtraChase.LinkedInAutoApplier")
        except Exception:
            pass
    icon_path = _icon_file()
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    theme.apply(app)
    win = MainWindow()
    win.show()
    return app.exec()
