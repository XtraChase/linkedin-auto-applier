"""
Glass look for the desktop app.

  * Windows 11: a real blurred "acrylic" backdrop behind the window (DWM system backdrop), with a dark title bar.
  * Everywhere else, or if the backdrop is unavailable: the same gradient glass, just without the live blur.
  * Panels, inputs and buttons are translucent white over that backdrop with soft borders and rounded corners.
"""
import ctypes, sys
from ctypes import wintypes

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

ACCENT_A = "rgba(86, 204, 242, 0.55)"      # cyan
ACCENT_B = "rgba(139, 109, 255, 0.50)"     # violet

STYLESHEET = f"""
* {{ font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif; font-size: 10pt; color: #eef2ff; }}
QMainWindow, QDialog {{ background: transparent; }}
QDialog {{ background: rgba(22, 26, 46, 0.96); }}
QWidget#glassRoot {{ background: transparent; }}
QLabel {{ background: transparent; }}
QLabel#title {{ font-size: 21pt; font-weight: 600; letter-spacing: 0.5px; }}
QLabel#subtitle {{ color: rgba(238, 242, 255, 0.62); }}
QLabel#status {{ background: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.16); border-radius: 12px; padding: 10px 14px; font-size: 11pt; }}

QGroupBox {{ background: rgba(255, 255, 255, 0.07); border: 1px solid rgba(255, 255, 255, 0.17); border-radius: 16px;
            margin-top: 18px; padding: 16px 14px 12px 14px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 18px; padding: 0 8px; color: rgba(238, 242, 255, 0.85); font-weight: 600; }}

QTabWidget::pane {{ border: none; background: transparent; top: 10px; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{ background: rgba(255, 255, 255, 0.07); border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 13px;
               padding: 8px 20px; margin-right: 8px; color: rgba(238, 242, 255, 0.72); }}
QTabBar::tab:hover:!selected {{ background: rgba(255, 255, 255, 0.14); }}
QTabBar::tab:selected {{ color: white; border: 1px solid rgba(255, 255, 255, 0.38);
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT_A}, stop:1 {ACCENT_B}); }}

QPushButton {{ background: rgba(255, 255, 255, 0.10); border: 1px solid rgba(255, 255, 255, 0.24); border-radius: 11px; padding: 8px 18px; }}
QPushButton:hover {{ background: rgba(255, 255, 255, 0.19); border-color: rgba(255, 255, 255, 0.40); }}
QPushButton:pressed {{ background: rgba(255, 255, 255, 0.06); }}
QPushButton:disabled {{ color: rgba(238, 242, 255, 0.32); background: rgba(255, 255, 255, 0.04); border-color: rgba(255, 255, 255, 0.08); }}
QPushButton#primary {{ font-weight: 600; border: 1px solid rgba(255, 255, 255, 0.45);
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(60, 200, 225, 0.75), stop:1 rgba(110, 120, 255, 0.70)); }}
QPushButton#primary:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(90, 220, 240, 0.9), stop:1 rgba(130, 140, 255, 0.85)); }}
QPushButton#primary:disabled {{ background: rgba(255, 255, 255, 0.05); border-color: rgba(255, 255, 255, 0.10); }}
QPushButton#rowbtn {{ padding: 3px 10px; margin: 2px 4px; min-height: 0; }}
QPushButton#danger {{ background: rgba(255, 95, 120, 0.30); border-color: rgba(255, 140, 160, 0.55); }}
QPushButton#danger:hover {{ background: rgba(255, 95, 120, 0.50); }}
QPushButton#danger:disabled {{ background: rgba(255, 255, 255, 0.04); border-color: rgba(255, 255, 255, 0.08); }}

QLineEdit, QSpinBox, QComboBox {{ background: rgba(8, 12, 28, 0.38); border: 1px solid rgba(255, 255, 255, 0.17); border-radius: 9px; padding: 6px 10px;
    selection-background-color: rgba(110, 168, 255, 0.55); }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{ border: 1px solid rgba(120, 210, 255, 0.75); }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; border: none; background: transparent; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: rgba(26, 30, 52, 0.98); border: 1px solid rgba(255, 255, 255, 0.2); selection-background-color: rgba(110, 168, 255, 0.45); outline: none; }}
QPlainTextEdit {{ background: rgba(8, 12, 28, 0.42); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 14px; padding: 8px;
    selection-background-color: rgba(110, 168, 255, 0.55); }}

QTableWidget {{ background: rgba(8, 12, 28, 0.34); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 14px; gridline-color: rgba(255, 255, 255, 0.05);
    alternate-background-color: rgba(255, 255, 255, 0.03); outline: none; }}
QTableWidget::item {{ padding: 4px 6px; }}
QTableWidget::item:selected {{ background: rgba(110, 168, 255, 0.34); color: white; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: rgba(255, 255, 255, 0.09); padding: 7px 8px; border: none; border-bottom: 1px solid rgba(255, 255, 255, 0.16); color: rgba(238, 242, 255, 0.88); }}
QTableCornerButton::section {{ background: transparent; border: none; }}

QCheckBox {{ spacing: 9px; background: transparent; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 6px; border: 1px solid rgba(255, 255, 255, 0.35); background: rgba(8, 12, 28, 0.35); }}
QCheckBox::indicator:checked {{ border-color: rgba(255, 255, 255, 0.6);
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(60, 200, 225, 0.9), stop:1 rgba(110, 120, 255, 0.9)); }}

QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(255, 255, 255, 0.24); border-radius: 5px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(255, 255, 255, 0.40); }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: rgba(255, 255, 255, 0.24); border-radius: 5px; min-width: 28px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QToolTip {{ background: rgba(26, 30, 52, 0.97); color: #eef2ff; border: 1px solid rgba(255, 255, 255, 0.25); border-radius: 8px; padding: 6px; }}
"""


class GlassRoot(QWidget):
    """Paints the tinted gradient and soft colour glows that make the panels above it read as frosted glass.
    When the live blur backdrop is active the tint is lighter so the desktop shows through."""
    def __init__(self, backdrop=False):
        super().__init__()
        self.setObjectName("glassRoot")
        self.backdrop = backdrop

    def set_backdrop(self, on):
        self.backdrop = on; self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        a = 0.62 if self.backdrop else 1.0                      # tint strength: lighter over a real blur
        base = QLinearGradient(0, 0, w, h)
        base.setColorAt(0.0, QColor(18, 24, 52, int(235 * a)))
        base.setColorAt(0.55, QColor(24, 34, 70, int(225 * a)))
        base.setColorAt(1.0, QColor(40, 24, 72, int(235 * a)))
        p.fillRect(self.rect(), base)
        for cx, cy, r, color in ((0.10 * w, 0.05 * h, 0.55 * max(w, h), QColor(60, 190, 235, 70)),
                                 (0.95 * w, 0.95 * h, 0.60 * max(w, h), QColor(150, 90, 255, 70))):
            g = QRadialGradient(QPointF(cx, cy), r)
            g.setColorAt(0.0, color); g.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
            p.fillRect(self.rect(), g)
        p.setPen(QColor(255, 255, 255, 38))                     # hairline highlight along the top edge, like a glass edge
        p.drawLine(0, 0, w, 0)


def apply_backdrop(window):
    """Windows 11: blurred acrylic backdrop and dark title bar. Returns True when the backdrop was applied."""
    if sys.platform != "win32":
        return False
    try:
        hwnd = wintypes.HWND(int(window.winId()))
        dwm = ctypes.windll.dwmapi

        def set_attr(attr, value):
            v = ctypes.c_int(value)
            return dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))

        set_attr(20, 1)                                          # DWMWA_USE_IMMERSIVE_DARK_MODE
        ok = set_attr(38, 3) == 0                                # DWMWA_SYSTEMBACKDROP_TYPE = DWMSBT_TRANSIENTWINDOW (acrylic)
        if ok:
            class MARGINS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int), ("t", ctypes.c_int), ("b", ctypes.c_int)]
            dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(MARGINS(-1, -1, -1, -1)))
        return ok
    except Exception:
        return False
