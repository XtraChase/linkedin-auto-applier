"""
Start the desktop app:   .venv\\Scripts\\python.exe desktop_app.py   (or double-click start_app.bat, or the packaged .exe)

The packaged .exe is also its own worker: the app starts the bot as a second copy of the exe with
    LinkedInAutoApplier.exe --run-script hybrid_apply [options]
    LinkedInAutoApplier.exe --run-code "<python>"
which is how the Run tab and the Settings tab buttons work without a separate Python install.
"""
import os, runpy, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _fix_stdio():
    """A windowed exe may start with no stdout/stdin; use the pipes the app gave us."""
    for name, fd, mode in (("stdout", 1, "w"), ("stderr", 2, "w"), ("stdin", 0, "r")):
        if getattr(sys, name) is None:
            try:
                setattr(sys, name, open(fd, mode, encoding="utf-8", errors="replace", buffering=1 if mode == "w" else -1, closefd=False))
            except OSError:
                pass
    for name in ("stdout", "stderr"):          # send every line out at once: the Run tab shows progress live, not in a lump at the end
        stream = getattr(sys, name, None)
        try:
            stream.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
        except Exception:
            pass


def _selftest(report_path):
    """Check the Run tab's machinery: start a worker copy of this program through BotRunner and read its output.
    Writes the result to report_path (a windowed exe has no console). Exit code 0 = works."""
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
    from desktop.runner import BotRunner
    app = QCoreApplication([])
    import time
    runner, lines, loop, stamps = BotRunner(), [], QEventLoop(), {}
    runner.line.connect(lambda t: (lines.append(t), stamps.setdefault(t, time.time())))
    runner.finished.connect(lambda code: loop.quit())
    QTimer.singleShot(90000, loop.quit)
    t0 = time.time()
    # the worker prints, waits 5 s, prints again: the first line must reach the app long before the second one
    runner.start("-c", ["import sys,time; print('worker says hello'); time.sleep(5); print('frozen:', getattr(sys, 'frozen', False))"])
    loop.exec()
    streamed = "worker says hello" in stamps and (stamps["worker says hello"] - t0) < 4.5
    lines.append("streamed live: " + str(streamed))
    ok = "worker says hello" in lines and streamed
    if report_path:
        open(report_path, "w", encoding="utf-8").write(("OK" if ok else "FAILED") + "\n" + "\n".join(lines) + "\n")
    return 0 if ok else 1


def main():
    import app_paths
    app_paths.setup()                       # work from the data folder; its config/ package is importable
    if len(sys.argv) >= 3 and sys.argv[1] == "--run-script":
        _fix_stdio()
        name = sys.argv[2]
        sys.argv = [name + ".py"] + sys.argv[3:]
        try:
            runpy.run_module(name, run_name="__main__", alter_sys=True)
        except SystemExit:
            raise
        except BaseException as e:               # say what went wrong in one plain line the app can show
            import traceback
            traceback.print_exc()
            first = (getattr(e, "msg", None) or str(e) or "").strip().splitlines()
            detail = first[0] if first else ""
            print(f"\nERROR: {type(e).__name__}: {detail}", flush=True)
            return 1
        return 0
    if len(sys.argv) >= 3 and sys.argv[1] == "--run-code":
        _fix_stdio()
        exec(compile(sys.argv[2], "<code>", "exec"), {"__name__": "__main__"})
        return 0
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest":
        return _selftest(sys.argv[2] if len(sys.argv) > 2 else None)
    import init_config
    init_config.create_missing()            # first run: create config files from the bundled examples
    from desktop.main_window import run
    return run()


if __name__ == "__main__":
    sys.exit(main())
