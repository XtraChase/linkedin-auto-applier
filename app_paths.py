"""
Where the app's files live, whether it runs from source or as the packaged .exe.

  home()        the data folder: config/, all excels/, all resumes/, .chrome_profile/, reports/ ...
                From source it is the project folder. For the .exe it is the first folder at or above the exe that
                already contains config/personals.py (so an exe built inside the project uses the project's data),
                else the exe's own folder (first run creates config from the bundled examples).
                Set the LAA_HOME environment variable to force a folder.
  bundle_dir()  read-only files shipped inside the .exe (the example config files).
"""
import os, sys


def frozen():
    return bool(getattr(sys, "frozen", False))


def bundle_dir():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def assets_dir():
    """Icons and other read-only assets: inside the exe when packaged, else the project's assets folder."""
    return os.path.join(bundle_dir() if frozen() else os.path.dirname(os.path.abspath(__file__)), "assets")


def home():
    forced = os.environ.get("LAA_HOME")
    if forced and os.path.isdir(forced):
        return forced
    if not frozen():
        return os.path.dirname(os.path.abspath(__file__))
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    d = exe_dir
    for _ in range(5):
        if os.path.exists(os.path.join(d, "config", "personals.py")):
            return d
        parent = os.path.dirname(d)
        if parent == d: break
        d = parent
    return exe_dir


def setup():
    """Work from the data folder and make its config/ package importable (it is NOT frozen into the exe, so you can edit it)."""
    h = home()
    os.makedirs(h, exist_ok=True)
    os.chdir(h)
    if h not in sys.path:
        sys.path.insert(0, h)
    return h
