"""Главное окно: боковое меню, разделы, сохранение настроек, смена темы."""
import sys

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMainWindow, QPushButton, QScrollArea, QStackedWidget,
                               QVBoxLayout, QWidget)

from ui.pages.analytics import AnalyticsPage
from ui.pages.cards import CardsPage
from ui.pages.copper import CopperPage
from ui.pages.custom_tol import CustomTolPage
from ui.pages.dies import DiesPage
from ui.pages.draw import DrawPage
from ui.pages.mass import MassPage
from ui.pages.mills import MillsPage
from ui.pages.reference import ReferencePage
from ui.pages.route import RoutePage
from ui.pages.tolerance import TolerancePage
from ui.hud import HudRule, paint_grid
from ui.theme import (FONT, FONT_MAX, FONT_MIN, THEMES, T, build_qss, refresh_glows, rescale_all,
                      sized)
from ui.anim import ANIM, SECTION_MS, AnimatedTabWidget, NavIndicator, crossfade

APP_TITLE = "Калькулятор волочения — v1.0"

# Разделы бокового меню и их подвкладки. Новая подвкладка добавляется одной строкой.
SECTIONS = [
    ("Волочение", [("Маршрут", RoutePage), ("Станы", MillsPage), ("Один проход", DrawPage),
                   ("Допуски и волоки", TolerancePage), ("Свои допуски", CustomTolPage)]),
    ("Техкарты", [("Техкарты", CardsPage)]),
    ("Материалы", [("Масса и упаковка", MassPage), ("Омеднение", CopperPage)]),
    ("Аналитика", [("Аналитика", AnalyticsPage)]),
    ("Справочник", [("Справочник", ReferencePage)]),
    ("Журнал фильер", [("Журнал фильер", DiesPage)]),
]
PAGES = [item for _, items in SECTIONS for item in items]


class Section(QWidget):
    """Раздел бокового меню: метка модуля, заголовок, линия HUD и подвкладки."""

    def __init__(self, title, pages, index=0):
        super().__init__()
        self.setObjectName("section")
        self.pages = pages
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 26, 36, 26)
        lay.setSpacing(4)
        k = QLabel(f"МОДУЛЬ {index + 1:02d}  //  {title.upper()}")
        k.setProperty("role", "kicker")
        lay.addWidget(k)
        t = QLabel(title)
        t.setObjectName("pageTitle")
        lay.addWidget(t)
        lay.addWidget(HudRule())
        lay.addSpacing(8)
        if len(pages) == 1:
            self.tabs = None
            lay.addWidget(pages[0][1], 1)
        else:
            self.tabs = AnimatedTabWidget(ms=230)
            self.tabs.setObjectName("sectionTabs")
            for name, page in pages:
                self.tabs.addTab(page, name)
            lay.addWidget(self.tabs, 1)

    def current(self):
        return self.pages[self.tabs.currentIndex()][1] if self.tabs else self.pages[0][1]

    def paintEvent(self, event):
        p = QPainter(self)
        paint_grid(p, self.rect())
        p.end()


class MainWindow(QMainWindow):
    def __init__(self, settings, theme):
        super().__init__()
        self.settings = settings
        self.theme = theme
        self.setWindowTitle(APP_TITLE)
        self.resize(1400, 880)
        self.setMinimumSize(1050, 640)

        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        side = QWidget()
        side.setObjectName("sidebar")
        sized(side, "fixed", 230)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(0)
        t = QLabel("ВОЛОЧЕНИЕ")
        t.setObjectName("appTitle")
        s = QLabel("WIRE · DRAWING · SUITE")
        s.setObjectName("appSub")
        sv.addWidget(t)
        sv.addWidget(s)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setCursor(Qt.CursorShape.PointingHandCursor)
        sv.addWidget(self.nav, 1)
        fr = QHBoxLayout()
        fr.setContentsMargins(14, 0, 14, 0)
        self.font_minus = QPushButton("A−")
        self.font_plus = QPushButton("A+")
        self.font_label = QLabel()
        self.font_label.setObjectName("fontLabel")
        self.font_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for b in (self.font_minus, self.font_plus):
            b.setObjectName("themeBtn")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip("Размер шрифта")
        fr.addWidget(self.font_minus)
        fr.addWidget(self.font_label, 1)
        fr.addWidget(self.font_plus)
        sv.addLayout(fr)
        self.font_minus.clicked.connect(lambda: self.change_font(-1))
        self.font_plus.clicked.connect(lambda: self.change_font(+1))
        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("themeBtn")
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.clicked.connect(self.toggle_theme)
        sv.addWidget(self.theme_btn)
        self.anim_btn = QPushButton()
        self.anim_btn.setObjectName("themeBtn")
        self.anim_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.anim_btn.setToolTip("Плавные переходы между разделами и вкладками")
        self.anim_btn.clicked.connect(self.toggle_anim)
        sv.addWidget(self.anim_btn)
        ver = QLabel(APP_TITLE.split("—")[-1].strip().upper() + "  ·  ТЕХНОЛОГ")
        ver.setObjectName("version")
        sv.addWidget(ver)
        h.addWidget(side)

        self.stack = QStackedWidget()
        h.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.pages, self.loc, self.sections = [], [], []
        for si, (title, items) in enumerate(SECTIONS):
            built = []
            for ti, (name, page_cls) in enumerate(items):
                page = page_cls(self)
                self.pages.append(page)
                self.loc.append((si, ti))
                built.append((name, page))
            sec = Section(title, built, si)
            if sec.tabs:
                sec.tabs.currentChanged.connect(lambda _i, s=sec: s.current().on_show())
            self.sections.append(sec)
            area_ = QScrollArea()
            area_.setWidgetResizable(True)
            area_.setWidget(sec)
            self.stack.addWidget(area_)
            self.nav.addItem(QListWidgetItem(f"{si + 1:02d}    {title.upper()}"))
        self.nav.currentRowChanged.connect(self.show_section)

        self.restore()
        self.update_theme_btn()
        self.update_font_label()
        self.nav_ind = NavIndicator(self.nav)
        self.nav_ind.update()
        self.update_anim_btn()

    def show_section(self, idx):
        old = self.stack.currentWidget()
        snap = old.grab() if (ANIM["on"] and old is not None and self.stack.currentIndex() != idx
                              and self.isVisible()) else None
        self.stack.setCurrentIndex(idx)
        crossfade(self.stack, snap, self.stack.currentWidget(), SECTION_MS, shift=28)
        if 0 <= idx < len(self.sections):
            self.sections[idx].current().on_show()

    def go_to(self, page):
        """Открывает раздел и подвкладку, где лежит страница."""
        si, ti = self.loc[self.pages.index(page)]
        self.nav.setCurrentRow(si)
        if self.sections[si].tabs:
            self.sections[si].tabs.setCurrentIndex(ti)

    def page_of(self, cls):
        return next(p for p in self.pages if isinstance(p, cls))

    def open_card(self, card):
        """Открывает техкарту в разделе маршрута."""
        route = self.page_of(RoutePage)
        route.load_card(card)
        self.go_to(route)

    def restore(self):
        st = self.settings
        for page in self.pages:
            for key, combo in page.combos.items():
                val = st.value(key)
                if isinstance(val, str):
                    val = getattr(page, "legacy", {}).get(val, val)
                if isinstance(val, str) and combo.findText(val) >= 0:
                    combo.setCurrentText(val)
            for f in page.fields:
                val = st.value(f.key) if f.key else None
                if isinstance(val, str):
                    f.setText(val)
            for key, w in page.texts.items():
                val = st.value(key)
                if isinstance(val, str):
                    w.setText(val)
            for key, box in page.checks.items():
                val = st.value(key)
                if val is not None:
                    box.setChecked(str(val).lower() in ("true", "1"))
            page.safe_recalc()
        geo = st.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        for si, sec in enumerate(self.sections):
            if sec.tabs:
                try:
                    sec.tabs.setCurrentIndex(int(st.value(f"tab/{si}", 0)))
                except (TypeError, ValueError):
                    pass
        try:
            idx = int(st.value("section", 0))
        except (TypeError, ValueError):
            idx = 0
        self.nav.setCurrentRow(min(max(idx, 0), len(self.sections) - 1))

    def closeEvent(self, event):
        st = self.settings
        for page in self.pages:
            for key, combo in page.combos.items():
                st.setValue(key, combo.currentText())
            for f in page.fields:
                if f.key:
                    st.setValue(f.key, f.text())
            for key, w in page.texts.items():
                st.setValue(key, w.text())
            for key, box in page.checks.items():
                st.setValue(key, "true" if box.isChecked() else "false")
        st.setValue("geometry", self.saveGeometry())
        st.setValue("section", self.nav.currentRow())
        for si, sec in enumerate(self.sections):
            if sec.tabs:
                st.setValue(f"tab/{si}", sec.tabs.currentIndex())
        st.setValue("theme", self.theme)
        st.setValue("anim", "true" if ANIM["on"] else "false")
        st.setValue("font", FONT["base"])
        super().closeEvent(event)

    def update_font_label(self):
        self.font_label.setText(f"ШРИФТ {FONT['base']}")
        self.font_minus.setEnabled(FONT["base"] > FONT_MIN)
        self.font_plus.setEnabled(FONT["base"] < FONT_MAX)

    def change_font(self, step):
        FONT["base"] = min(FONT_MAX, max(FONT_MIN, FONT["base"] + step))
        app = QApplication.instance()
        app.setFont(QFont("Segoe UI", FONT["base"]))
        app.setStyleSheet(build_qss(T))
        rescale_all()
        self.update_font_label()
        self.nav_ind.update()
        for page in self.pages:
            page.on_theme()

    def update_anim_btn(self):
        self.anim_btn.setText("АНИМАЦИИ: ВКЛ" if ANIM["on"] else "АНИМАЦИИ: ВЫКЛ")

    def toggle_anim(self):
        ANIM["on"] = not ANIM["on"]
        self.update_anim_btn()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "nav_ind"):
            self.nav_ind.update()

    def update_theme_btn(self):
        self.theme_btn.setText("НОЧНОЙ РЕЖИМ" if self.theme == "light" else "ДНЕВНОЙ РЕЖИМ")

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        T.clear()
        T.update(THEMES[self.theme])
        QApplication.instance().setStyleSheet(build_qss(T))
        refresh_glows()
        self.update_theme_btn()
        for page in self.pages:
            page.on_theme()


def run():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    settings = QSettings("WireDrawing", "DrawingCalc")
    try:
        FONT["base"] = min(FONT_MAX, max(FONT_MIN, int(settings.value("font", FONT["base"]))))
    except (TypeError, ValueError):
        pass
    app.setFont(QFont("Segoe UI", FONT["base"]))
    theme = settings.value("theme", "dark")
    if theme not in THEMES:
        theme = "dark"
    T.clear()
    T.update(THEMES[theme])
    ANIM["on"] = str(settings.value("anim", "true")).lower() in ("true", "1")
    app.setStyleSheet(build_qss(T))
    win = MainWindow(settings, theme)
    win.show()
    sys.exit(app.exec())
