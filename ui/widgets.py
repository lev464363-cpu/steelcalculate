"""Общие элементы интерфейса: поля ввода, карточки, таблицы, базовый класс раздела."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QPushButton, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QTabWidget, QToolBox, QVBoxLayout, QWidget)

from core.util import InputError, num
from ui.hud import HudPanel, paint_hud
from ui.theme import add_glow, px, sized


class FieldError(InputError):
    def __init__(self, field, msg):
        super().__init__(msg)
        self.field = field


class NumField(QLineEdit):
    """Поле для числа: подсвечивается красным при ошибке."""

    def __init__(self, name, default="", key=None):
        super().__init__(default)
        self.name = name
        self.key = key
        self._err = False
        sized(self, "min", 110)

    def set_error(self, on, msg=""):
        if on != self._err:
            self._err = on
            self.setProperty("error", "true" if on else "false")
            self.style().unpolish(self)
            self.style().polish(self)
        self.setToolTip(msg if on else "")

    def value(self, allow_zero=False, optional=False):
        txt = self.text().strip()
        if not txt:
            if optional:
                return None
            raise FieldError(self, f"Заполни поле «{self.name}».")
        try:
            v = num(txt)
        except ValueError:
            raise FieldError(self, f"В поле «{self.name}» должно быть число.")
        if v < 0 or (v == 0 and not allow_zero):
            raise FieldError(self, f"«{self.name}» должно быть больше нуля.")
        return v


class Card(QFrame):
    """Карточка результата: подпись прописными, крупное число, единица; фон — панель HUD."""

    def __init__(self, title, unit=""):
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 12)
        lay.setSpacing(4)
        t = QLabel(title.upper())
        t.setProperty("role", "cardTitle")
        t.setWordWrap(True)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.v = QLabel("—")
        self.v.setProperty("role", "cardValue")
        u = QLabel(unit)
        u.setProperty("role", "cardUnit")
        row.addWidget(self.v)
        row.addWidget(u, 0, Qt.AlignmentFlag.AlignBottom)
        row.addStretch()
        lay.addWidget(t)
        lay.addLayout(row)

    def paintEvent(self, event):
        p = QPainter(self)
        paint_hud(p, self.rect(), cut=px(10))
        p.end()

    def set(self, text):
        self.v.setText(text)


def panel():
    return HudPanel()


def label(text, role=None, wrap=False):
    lab = QLabel(text.upper() if role == "section" else text)
    if role:
        lab.setProperty("role", role)
    lab.setWordWrap(wrap)
    return lab


def button(text, primary=False):
    b = QPushButton(text.upper() if primary else text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        b.setProperty("primary", "true")
        add_glow(b)
    return b


def cards_row(cards):
    row = QHBoxLayout()
    row.setSpacing(12)
    for c in cards:
        row.addWidget(c, 1)
    return row


def make_table(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    # высота строк подстраивается под размер шрифта
    t.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    h = t.horizontalHeader()
    h.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    h.setStretchLastSection(True)
    h.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return t


def fill_table(t, rows, colors=None):
    t.setRowCount(len(rows))
    for r, row in enumerate(rows):
        bg, fg = colors[r] if colors and colors[r] else (None, None)
        for c, val in enumerate(row):
            it = QTableWidgetItem(str(val))
            if bg:
                it.setBackground(QBrush(QColor(bg)))
            if fg:
                it.setForeground(QBrush(QColor(fg)))
            t.setItem(r, c, it)


class Page(QWidget):
    title = ""
    hint = ""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("page")
        self.fields = []   # поля, которые сохраняются и вызывают пересчёт
        self.combos = {}   # ключ настроек -> выпадающий список
        self.texts = {}    # ключ настроек -> текстовое поле (сохраняется, без пересчёта)
        self.checks = {}   # ключ настроек -> флажок
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 14, 0, 0)
        outer.setSpacing(12)
        if self.hint:
            outer.addWidget(label(self.hint, "muted", True))
        self.body = QVBoxLayout()
        self.body.setSpacing(14)
        outer.addLayout(self.body, 1)
        self.status = label("", "error", True)
        self.build()
        for f in self.fields:
            f.textChanged.connect(self.safe_recalc)

    def add_field(self, grid, row, text, default, key, col=0):
        f = NumField(text.split(",")[0].split(" (")[0], default, key)
        sized(f, "max", 140)
        lab = QLabel(text)
        lab.setWordWrap(True)
        sized(lab, "min", 150)
        grid.addWidget(lab, row, col)
        grid.addWidget(f, row, col + 1)
        grid.setColumnStretch(col, 1)
        self.fields.append(f)
        return f

    def build(self):
        pass

    def recalc(self):
        pass

    def clear_results(self):
        pass

    def on_theme(self):
        self.safe_recalc()

    def on_show(self):
        """Вызывается, когда раздел открывают в меню."""

    def reveal(self, widget):
        """Открывает внутренние вкладки страницы, на которых лежит поле с ошибкой."""
        w = widget
        while w is not None and w is not self:
            parent = w.parentWidget()
            if isinstance(parent, QStackedWidget) and isinstance(parent.parentWidget(), QTabWidget):
                parent.parentWidget().setCurrentWidget(w)
            box = parent
            for _ in range(4):        # группа «гармошки» лежит в служебной прокрутке QToolBox
                if box is None or box is self:
                    break
                if isinstance(box, QToolBox) and box.indexOf(w) >= 0:
                    box.setCurrentWidget(w)
                    break
                box = box.parentWidget()
            w = parent

    def safe_recalc(self, *args):
        for f in self.fields:
            f.set_error(False)
        try:
            self.recalc()
            self.status.setText("")
        except FieldError as e:
            e.field.set_error(True, str(e))
            self.status.setText(str(e))
            if self.isVisible() and not e.field.isVisible():
                self.reveal(e.field)
            self.clear_results()
        except InputError as e:
            self.status.setText(str(e))
            self.clear_results()
        except (ValueError, ZeroDivisionError, OverflowError):
            self.status.setText("Проверь введённые значения.")
            self.clear_results()


def tab_form(tabs, title):
    """Вкладка с формой: возвращает сетку, куда добавляются подписи и поля."""
    page = QWidget()
    lay = QVBoxLayout(page)
    lay.setContentsMargins(4, 12, 4, 4)
    grid = QGridLayout()
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(7)
    lay.addLayout(grid)
    lay.addStretch()
    tabs.addTab(page, title)
    return grid


def tab_box(tabs, title):
    """Вкладка со свободной вертикальной раскладкой."""
    page = QWidget()
    lay = QVBoxLayout(page)
    lay.setContentsMargins(0, 12, 0, 0)
    lay.setSpacing(12)
    tabs.addTab(page, title)
    return lay
