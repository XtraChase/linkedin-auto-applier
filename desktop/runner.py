"""Runs a bot script as a background process and talks to it: streams its output, notices when it is
waiting for an answer (the "Did you submit it?" prompts), and can stop it together with its Chrome."""
import os, re, sys

from PySide6.QtCore import QObject, QProcess, Signal

from app_paths import home
ROOT = home()

# prompts the bot prints with no trailing newline while it waits for a line of input
PROMPT_RE = re.compile(r"(Did you submit it\?.*:|Press Enter to continue.*:|Press Enter for the next.*:)\s*$")
# the Selenium stack traces that LinkedIn logins print are noise in a log window
NOISE_RE = re.compile(r"^\s*(chromedriver!|KERNEL32!|ntdll!|\(No symbol\)|Stacktrace:|Message:\s*$|Symbols not available)")


def clean_chunk(partial, data):
    """Split new output into (complete cleaned lines, leftover partial line)."""
    text = (partial + data).replace("\r", "")
    *lines, rest = text.split("\n")
    return [ln for ln in lines if not NOISE_RE.match(ln)], rest


class BotRunner(QObject):
    line = Signal(str)          # one cleaned line of output
    prompt = Signal(str)        # the bot is waiting for an answer; text of the question
    started = Signal()
    finished = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc = None
        self._partial = ""

    def is_running(self):
        return self.proc is not None and self.proc.state() != QProcess.NotRunning

    def start(self, script, args=()):
        if self.is_running(): return False
        self._partial = ""
        self.proc = QProcess(self)
        self.proc.setWorkingDirectory(ROOT)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        from PySide6.QtCore import QProcessEnvironment
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8"); env.insert("PYTHONUNBUFFERED", "1")
        self.proc.setProcessEnvironment(env)
        self.proc.readyReadStandardOutput.connect(self._on_output)
        self.proc.finished.connect(lambda code, _status: self._on_finished(code))
        self.proc.errorOccurred.connect(lambda err: self.line.emit(f"[could not start the process: {err}]"))
        if getattr(sys, "frozen", False):          # packaged exe: it runs the script itself (see desktop_app.py)
            if script == "-c":
                argv = ["--run-code", *args]
            else:
                argv = ["--run-script", os.path.splitext(os.path.basename(script))[0], *args]
        else:
            argv = ["-u", script, *args]
        self.proc.start(sys.executable, argv)
        self.started.emit()
        return True

    def _on_output(self):
        data = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        lines, self._partial = clean_chunk(self._partial, data)
        for ln in lines: self.line.emit(ln)
        if self._partial and PROMPT_RE.search(self._partial):
            text = self._partial.strip()
            self._partial = ""
            self.line.emit(text)
            self.prompt.emit(text)

    def _on_finished(self, code):
        if self._partial.strip(): self.line.emit(self._partial)
        self._partial = ""
        self.finished.emit(code)

    def answer(self, text=""):
        """Send a line to the bot (empty string = just press Enter)."""
        if self.is_running():
            self.line.emit(f"> {text or '(Enter)'}")
            self.proc.write((text + "\n").encode("utf-8"))

    def stop(self):
        """Stop the bot and the Chrome it started."""
        if not self.is_running(): return
        pid = int(self.proc.processId())
        if pid:
            QProcess.startDetached("taskkill", ["/PID", str(pid), "/T", "/F"])
        else:
            self.proc.kill()
