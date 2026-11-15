"""Light and dark themes: a Fusion palette plus a small stylesheet."""

from __future__ import annotations

from dataclasses import dataclass

from pathlib import Path

from PySide6.QtCore import QTemporaryDir, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from . import icons

# Stylesheets can only load images from files, so the combo box arrow is
# written here once per theme. Removed automatically when the app exits.
_asset_dir: QTemporaryDir | None = None


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str
    surface: str
    raised: str
    border: str
    text: str
    muted: str
    accent: str
    accent_hover: str
    accent_text: str
    success: str
    danger: str
    warning: str


DARK = Theme(
    name="dark",
    bg="#101216",
    surface="#181b21",
    raised="#22262e",
    border="#2c313b",
    text="#e8eaef",
    muted="#98a0ae",
    accent="#7b6cf6",
    accent_hover="#8f82f8",
    accent_text="#ffffff",
    success="#46b987",
    danger="#ee6b73",
    warning="#e2a644",
)

LIGHT = Theme(
    name="light",
    bg="#f4f5f8",
    surface="#ffffff",
    raised="#eef0f4",
    border="#dcdfe6",
    text="#171a21",
    muted="#636b7a",
    accent="#5a48e0",
    accent_hover="#4a39c8",
    accent_text="#ffffff",
    success="#1f8f5f",
    danger="#cc3944",
    warning="#a86a08",
)


def system_theme() -> Theme:
    scheme = QGuiApplication.styleHints().colorScheme()
    return LIGHT if scheme == Qt.ColorScheme.Light else DARK


def by_name(name: str) -> Theme:
    return {"dark": DARK, "light": LIGHT}.get(name) or system_theme()


def _palette(t: Theme) -> QPalette:
    p = QPalette()
    roles = QPalette.ColorRole
    for role, color in {
        roles.Window: t.bg,
        roles.WindowText: t.text,
        roles.Base: t.surface,
        roles.AlternateBase: t.raised,
        roles.Text: t.text,
        roles.Button: t.raised,
        roles.ButtonText: t.text,
        roles.ToolTipBase: t.raised,
        roles.ToolTipText: t.text,
        roles.PlaceholderText: t.muted,
        roles.Highlight: t.accent,
        roles.HighlightedText: t.accent_text,
        roles.Link: t.accent,
        roles.Mid: t.border,
        roles.Dark: t.border,
        roles.Light: t.raised,
    }.items():
        p.setColor(role, QColor(color))
    for role in (roles.Text, roles.WindowText, roles.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(t.muted))
    return p


_QSS = """
QWidget {{ font-size: 13px; }}
QToolTip {{ background: {raised}; color: {text}; border: 1px solid {border}; padding: 4px 6px; }}

#title {{ font-size: 20px; font-weight: 700; }}
#sectionTitle {{ font-size: 15px; font-weight: 600; }}
#mediaTitle {{ font-size: 15px; font-weight: 600; }}
#itemTitle {{ font-weight: 600; }}
#muted {{ color: {muted}; }}
#error {{ color: {danger}; }}
#warning {{ color: {warning}; }}
#success {{ color: {success}; }}
#chip {{
    color: {muted}; background: {raised}; border-radius: 9px;
    padding: 2px 8px; font-size: 11px; font-weight: 600;
}}

#card {{ background: {surface}; border: 1px solid {border}; border-radius: 12px; }}
#thumb {{ background: {raised}; border-radius: 8px; }}

QLineEdit {{
    background: {surface}; border: 1px solid {border}; border-radius: 8px;
    padding: 0 12px; min-height: 38px; selection-background-color: {accent};
}}
QLineEdit:focus {{ border-color: {accent}; }}

QComboBox {{
    background: {raised}; border: 1px solid {border}; border-radius: 8px;
    padding: 0 10px; min-height: 32px;
}}
QComboBox:hover, QComboBox:focus {{ border-color: {accent}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url("{chevron}"); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{
    background: {surface}; border: 1px solid {border}; outline: none;
    selection-background-color: {accent}; selection-color: {accent_text};
}}

QPushButton {{
    background: {raised}; border: 1px solid {border}; border-radius: 8px;
    padding: 0 14px; min-height: 32px;
}}
QPushButton:hover {{ border-color: {accent}; }}
QPushButton:focus {{ border-color: {accent}; }}
QPushButton:disabled {{ color: {muted}; border-color: {border}; }}

QPushButton#primary {{
    background: {accent}; border-color: {accent}; color: {accent_text};
    font-weight: 600; min-height: 38px; padding: 0 20px;
}}
QPushButton#primary:hover {{ background: {accent_hover}; border-color: {accent_hover}; }}
QPushButton#primary:disabled {{ background: {raised}; border-color: {border}; color: {muted}; }}

QPushButton#flat {{ background: transparent; border-color: transparent; color: {muted}; }}
QPushButton#flat:hover {{ color: {text}; background: {raised}; }}

QPushButton#iconButton {{
    background: transparent; border: 1px solid transparent; border-radius: 8px;
    padding: 0; min-height: 32px; min-width: 32px; max-width: 32px;
}}
QPushButton#iconButton:hover, QPushButton#iconButton:focus {{ background: {raised}; border-color: {border}; }}

QPushButton#segment {{ border-radius: 0; padding: 0 16px; }}
QPushButton#segment[first="true"] {{ border-top-left-radius: 8px; border-bottom-left-radius: 8px; }}
QPushButton#segment[last="true"] {{
    border-top-right-radius: 8px; border-bottom-right-radius: 8px; border-left: none;
}}
QPushButton#segment:checked {{
    background: {accent}; border-color: {accent}; color: {accent_text}; font-weight: 600;
}}

QCheckBox {{ spacing: 8px; }}

QProgressBar {{
    background: {raised}; border: none; border-radius: 3px;
    min-height: 6px; max-height: 6px;
}}
QProgressBar::chunk {{ background: {accent}; border-radius: 3px; }}
QProgressBar[state="done"]::chunk {{ background: {success}; }}
QProgressBar[state="failed"]::chunk {{ background: {danger}; }}
QProgressBar[state="paused"]::chunk {{ background: {muted}; }}

QScrollArea {{ background: transparent; border: none; }}
#queueBody {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {muted}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""


def apply(app: QApplication, theme: Theme) -> None:
    app.setStyle("Fusion")
    app.setPalette(_palette(theme))
    global _asset_dir
    if _asset_dir is None:
        _asset_dir = QTemporaryDir()
    chevron = Path(_asset_dir.path()) / f"chevron-{theme.name}.svg"
    chevron.write_bytes(icons.svg("chevron", theme.muted))
    app.setStyleSheet(_QSS.format(chevron=chevron.as_posix(), **theme.__dict__))
