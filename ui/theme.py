"""Цветовые темы и таблица стилей. Текущая тема хранится в словаре T."""

# Две темы на стыке Apple и Cyberpunk 2077:
#  «Ночь» — почти чёрный фон (не чистый чёрный, как советует Apple), неоновый жёлтый акцент,
#           бирюзовый для данных, инфракрасный красный для предупреждений (палитра CP2077);
#  «День» — светлая сдержанная тема в духе Apple с тем же жёлтым акцентом на кнопках.
THEMES = {
    "dark": dict(bg="#0D0F12", surface="#14181D", surface2="#1A1F25", text="#ECEEF0",
                 muted="#8C96A0", tertiary="#5A636D", border="#262D35", accent="#F3E600",
                 accent_hover="#FFF34D", accent_text="#0D0F12", accent_soft="#2A2810",
                 side="#08090B", side_text="#7D8791", side_active="#13171B", side_title="#FFFFFF",
                 warn="#FF4D6A", warn_soft="#2B1219", anneal="#2A2810", ok_soft="#10251B",
                 pill_text="#F3E600",
                 grid="#1C2228",
                 line="#00E1F0", glow_alpha=120),
    "light": dict(bg="#F5F5F7", surface="#FFFFFF", surface2="#F2F2F5", text="#1D1D1F",
                  muted="#6E6E73", tertiary="#A1A1A6", border="#DCDCE1", accent="#E8C500",
                  accent_hover="#F5D61A", accent_text="#1D1D1F", accent_soft="#FFF6C7",
                  side="#ECECEF", side_text="#5C5C61", side_active="#E0E0E5", side_title="#1D1D1F",
                  warn="#D70032", warn_soft="#FDE8EC", anneal="#FFF6C7", ok_soft="#E5F4EA",
                  pill_text="#1D1D1F",
                  grid="#E6E6EB",
                  line="#0089A3", glow_alpha=60),
}
T = dict(THEMES["dark"])  # текущая тема

DISPLAY = '"Bahnschrift SemiCondensed", "Bahnschrift", "Segoe UI Variable Display", "Segoe UI", Arial'
TEXT = '"Segoe UI Variable Text", "Segoe UI", "Noto Sans", Arial'
DISPLAY_FAMILIES = ["Bahnschrift SemiCondensed", "Bahnschrift", "Segoe UI"]

# Размер шрифта: базовый кегль, от него масштабируются все остальные размеры интерфейса
FONT = {"base": 12}
FONT_MIN, FONT_MAX = 9, 18
_scaled = []   # (виджет, метод, ширина при кегле 10) — пересчитываются при смене шрифта


def scale():
    return FONT["base"] / 10


def px(n):
    """Размер в пикселях, пропорциональный шрифту (n — значение для кегля 10)."""
    return int(round(n * scale()))


def sized(widget, method, n):
    """Задаёт ширину, которая будет меняться вместе со шрифтом: method — 'fixed', 'min', 'max'."""
    _scaled.append((widget, method, n))
    _apply(widget, method, n)
    return widget


def _apply(widget, method, n):
    getattr(widget, {"fixed": "setFixedWidth", "min": "setMinimumWidth",
                     "max": "setMaximumWidth"}[method])(px(n))


def rescale_all():
    for widget, method, n in list(_scaled):
        try:
            _apply(widget, method, n)
        except RuntimeError:          # виджет уже удалён
            _scaled.remove((widget, method, n))


def _check_icon(color):
    """Галочка для отмеченных флажков: SVG во временной папке (таблица стилей Qt берёт картинку
    только из файла). Путь — с прямыми слешами, так его понимает и Windows."""
    import os
    import tempfile
    folder = os.path.join(tempfile.gettempdir(), "kalkulyator_volocheniya")
    path = os.path.join(folder, f"check_{color.lstrip('#')}.svg")
    if not os.path.exists(path):
        try:
            os.makedirs(folder, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
                         f'<path d="M3.5 8.4l3 3 6-6.6" fill="none" stroke="{color}" '
                         f'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>')
        except OSError:
            return ""
    return path.replace("\\", "/")


def build_qss(t):
    def pt(x):
        return round(x * scale(), 1)
    check = _check_icon(t["accent_text"])
    check_img = f'image: url("{check}");' if check else ""
    return f"""
    QWidget {{ font-family: {TEXT}; font-size: {pt(10)}pt; color: {t['text']}; }}
    QMainWindow, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {t['bg']}; }}
    QScrollArea {{ border: none; }}
    QWidget#sidebar {{ background: {t['side']}; border-right: 1px solid {t['border']}; }}
    QLabel#appTitle {{ font-family: {DISPLAY}; color: {t['side_title']}; font-size: {pt(19)}pt;
                      font-weight: 700; padding: 26px 22px 0 22px; }}
    QLabel#appSub {{ font-family: {DISPLAY}; color: {t['accent']}; font-size: {pt(8)}pt;
                    padding: 2px 22px 22px 22px; }}
    QListWidget#nav {{ background: transparent; border: none; outline: 0; }}
    QListWidget#nav::item {{ font-family: {DISPLAY}; color: {t['side_text']}; padding: 11px 20px;
                            border-left: 2px solid transparent; }}
    QListWidget#nav::item:hover {{ color: {t['text']}; background: {t['side_active']}; }}
    QListWidget#nav::item:selected {{ color: {t['side_title']}; background: {t['side_active']}; }}
    QWidget#navIndicator {{ background: {t['accent']}; border-radius: 1px; }}
    QPushButton#themeBtn {{ background: transparent; color: {t['side_text']};
                           border: 1px solid {t['border']}; border-radius: 8px; padding: 7px;
                           margin: 4px 18px; font-family: {DISPLAY}; }}
    QPushButton#themeBtn:hover {{ color: {t['text']}; border-color: {t['accent']}; }}
    QPushButton#themeBtn:disabled {{ color: {t['tertiary']}; border-color: {t['side_active']}; }}
    QLabel#fontLabel {{ color: {t['side_text']}; font-family: {DISPLAY}; font-size: {pt(9)}pt; }}
    QLabel#version {{ color: {t['tertiary']}; font-family: {DISPLAY}; font-size: {pt(8)}pt;
                     padding: 6px 22px 16px 22px; }}

    QLabel#pageTitle {{ font-family: {DISPLAY}; font-size: {pt(25)}pt; font-weight: 600; }}
    QLabel[role="kicker"] {{ font-family: {DISPLAY}; color: {t['accent']}; font-size: {pt(8.5)}pt;
                            font-weight: 600; }}
    QLabel[role="muted"] {{ color: {t['muted']}; }}
    QLabel[role="section"] {{ font-family: {DISPLAY}; font-weight: 600; font-size: {pt(10)}pt;
                             color: {t['muted']}; padding-top: 6px; }}
    QLabel[role="error"] {{ color: {t['warn']}; }}
    QLabel[role="note"] {{ color: {t['muted']}; font-size: {pt(9)}pt; }}
    QFrame#card, QFrame#panel {{ background: transparent; border: none; }}
    QFrame#card QLabel, QFrame#panel QLabel {{ background: transparent; }}
    QLabel[role="cardTitle"] {{ font-family: {DISPLAY}; color: {t['muted']}; font-size: {pt(8.5)}pt;
                               font-weight: 600; }}
    QLabel[role="cardValue"] {{ font-family: {DISPLAY}; font-size: {pt(23)}pt; font-weight: 600;
                               color: {t['text']}; }}
    QLabel[role="cardUnit"] {{ color: {t['muted']}; padding-bottom: 5px; }}

    QLineEdit, QComboBox {{ background: {t['surface2']}; border: 1px solid {t['border']};
                           border-radius: 8px; padding: 6px 10px; min-height: 20px;
                           selection-background-color: {t['accent']};
                           selection-color: {t['accent_text']}; }}
    QLineEdit:hover, QComboBox:hover {{ border-color: {t['tertiary']}; }}
    QLineEdit:focus, QComboBox:focus {{ border: 1px solid {t['accent']}; }}
    QLineEdit:disabled, QComboBox:disabled {{ color: {t['tertiary']}; }}
    QPlainTextEdit, QTextEdit {{ background: {t['surface2']}; border: 1px solid {t['border']};
                                border-radius: 10px; padding: 6px 8px;
                                selection-background-color: {t['accent']};
                                selection-color: {t['accent_text']}; }}
    QPlainTextEdit:focus, QTextEdit:focus {{ border: 1px solid {t['accent']}; }}
    QPlainTextEdit:disabled {{ background: {t['surface']}; color: {t['tertiary']}; }}
    QLineEdit[error="true"] {{ border: 1px solid {t['warn']}; background: {t['warn_soft']}; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox QAbstractItemView {{ background: {t['surface']}; border: 1px solid {t['border']};
                                   selection-background-color: {t['accent_soft']};
                                   selection-color: {t['text']}; outline: 0; }}

    QPushButton {{ background: {t['surface2']}; color: {t['text']}; border: 1px solid {t['border']};
                  border-radius: 10px; padding: 8px 18px; font-family: {DISPLAY}; }}
    QPushButton:hover {{ border-color: {t['accent']}; color: {t['accent']}; }}
    QPushButton:pressed {{ background: {t['accent_soft']}; }}
    QPushButton[primary="true"] {{ background: {t['accent']}; color: {t['accent_text']};
                                  border: none; font-weight: 700; padding: 9px 20px; }}
    QPushButton[primary="true"]:hover {{ background: {t['accent_hover']}; color: {t['accent_text']}; }}

    QTabWidget::pane {{ border: none; background: transparent; }}
    QStackedWidget#qt_tabwidget_stackedwidget, QWidget#refTab {{ background: transparent; }}
    /* внутренние вкладки — «таблетки»; вкладки раздела — с подчёркиванием */
    QTabBar::tab {{ background: transparent; color: {t['muted']}; padding: 6px 9px;
                   border: 1px solid transparent; border-radius: 9px; margin: 2px 1px 6px 0;
                   font-family: {DISPLAY}; }}
    QTabBar::tab:hover {{ color: {t['text']}; background: {t['surface2']}; }}
    QTabBar::tab:selected {{ color: {t['pill_text']}; font-weight: 600; background: {t['accent_soft']};
                            border-color: {t['accent_soft']}; }}
    QTabWidget#sectionTabs > QTabBar::tab {{ font-size: {pt(11)}pt; padding: 10px 18px;
                                            border-radius: 0; margin: 0 2px 0 0;
                                            border: none; border-bottom: 2px solid transparent; }}
    QTabWidget#sectionTabs > QTabBar::tab:hover {{ background: transparent; }}
    QTabWidget#sectionTabs > QTabBar::tab:selected {{ color: {t['text']}; background: transparent;
                                                     border-bottom: 2px solid {t['accent']}; }}
    QTabWidget#sectionTabs > QTabBar {{ border-bottom: 1px solid {t['border']}; }}
    QTabBar QToolButton {{ background: {t['surface2']}; border: 1px solid {t['border']};
                          border-radius: 6px; }}

    QTableWidget {{ background: {t['surface']}; alternate-background-color: {t['surface2']};
                   border: 1px solid {t['border']}; border-radius: 14px; gridline-color: {t['grid']};
                   selection-background-color: {t['accent_soft']}; selection-color: {t['text']};
                   padding: 4px; }}
    QTableWidget::item {{ padding: 4px 8px; border: none; }}
    QHeaderView::section {{ background: {t['surface']}; color: {t['muted']}; border: none;
                           border-bottom: 1px solid {t['border']}; padding: 9px 10px;
                           font-family: {DISPLAY}; font-weight: 600; }}
    QTableWidget::indicator {{ width: 16px; height: 16px; border-radius: 4px;
                              border: 1px solid {t['tertiary']}; background: {t['surface2']}; }}
    QTableWidget::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']};
                                      {check_img} }}
    QTableCornerButton::section {{ background: {t['surface']}; border: none; }}

    QToolBox::tab {{ background: {t['surface2']}; color: {t['muted']}; border: 1px solid {t['border']};
                    border-radius: 8px; padding: 7px 12px; font-family: {DISPLAY}; }}
    QToolBox::tab:selected {{ color: {t['text']}; font-weight: 600; border-color: {t['accent']}; }}
    QToolBox QScrollArea {{ background: transparent; border: none; }}
    QToolBox QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QTextBrowser {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 10px;
                   padding: 12px; }}
    QListWidget {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 10px; }}
    QListWidget::item:selected {{ background: {t['accent_soft']}; color: {t['text']}; }}

    QCheckBox {{ spacing: 10px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px;
                           border: 1px solid {t['tertiary']}; background: {t['surface2']}; }}
    QCheckBox::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']};
                                   {check_img} }}
    QCheckBox::indicator:unchecked:disabled {{ background: {t['surface']}; border-color: {t['border']}; }}
    QToolTip {{ background: {t['surface2']}; color: {t['text']}; border: 1px solid {t['border']};
               border-radius: 8px; padding: 7px 9px; }}

    /* диалоги и всплывающие уведомления */
    QMessageBox, QInputDialog, QDialog {{ background: {t['surface']}; }}
    QMessageBox QLabel, QDialog QLabel {{ background: transparent; }}
    QMessageBox QPushButton, QInputDialog QPushButton {{ min-width: 90px; }}
    QFrame#toast {{ background: {t['surface2']}; border: 1px solid {t['border']};
                   border-radius: 14px; }}
    QFrame#toast QLabel {{ background: transparent; }}
    QLabel#toastTitle {{ font-family: {DISPLAY}; font-weight: 600; }}
    QLabel#toastText {{ color: {t['muted']}; }}

    /* раскрывающиеся разделы (себестоимость) */
    QFrame#section {{ background: {t['surface']}; border: 1px solid {t['border']};
                     border-radius: 12px; }}
    QFrame#section[open="true"] {{ border-color: {t['tertiary']}; }}
    QToolButton#sectionHead {{ background: transparent; border: none; text-align: left;
                              padding: 9px 12px; font-family: {DISPLAY}; font-weight: 600;
                              color: {t['text']}; }}
    QToolButton#sectionHead:hover {{ color: {t['accent']}; }}
    QLabel#sectionSummary {{ color: {t['muted']}; font-size: {pt(9)}pt; padding: 0 12px 8px 34px; }}
    QFrame#section QLabel {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {t['accent']}; }}
    QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {t['border']}; border-radius: 4px; min-width: 30px; }}
    QScrollBar::handle:horizontal:hover {{ background: {t['accent']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    """


# Неоновое свечение главных кнопок: эффекты регистрируются и перекрашиваются при смене темы
_glows = []


def add_glow(widget):
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QGraphicsDropShadowEffect
    eff = QGraphicsDropShadowEffect(widget)
    eff.setOffset(0, 0)
    eff.setBlurRadius(22)
    c = QColor(T["accent"])
    c.setAlpha(T["glow_alpha"])
    eff.setColor(c)
    widget.setGraphicsEffect(eff)
    _glows.append(eff)


def refresh_glows():
    from PySide6.QtGui import QColor
    for eff in list(_glows):
        try:
            c = QColor(T["accent"])
            c.setAlpha(T["glow_alpha"])
            eff.setColor(c)
        except RuntimeError:
            _glows.remove(eff)
