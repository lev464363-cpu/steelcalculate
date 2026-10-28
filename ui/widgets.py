"""Общие элементы интерфейса: поля ввода, карточки, таблицы, базовый класс раздела."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QPushButton, QStackedWidget, QTableWidget,
                               QSizePolicy, QStyledItemDelegate, QTableWidgetItem, QTabWidget,
                               QToolButton, QVBoxLayout, QWidget)

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


class Collapsible(QFrame):
    """Раскрывающийся раздел: цветная метка, заголовок, строка-сводка значений и тело с полями.
    Открывается и закрывается щелчком по заголовку, независимо от соседних разделов."""

    def __init__(self, title, color, open_=False):
        super().__init__()
        self.setObjectName("section")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.title, self.color = title, color
        self.head = QToolButton()
        self.head.setObjectName("sectionHead")
        self.head.setCursor(Qt.CursorShape.PointingHandCursor)
        self.head.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.head.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.head.setIcon(_dot_icon(color))
        self.head.clicked.connect(lambda: self.set_open(not self.is_open))
        lay.addWidget(self.head)
        self.summary = QLabel("")
        self.summary.setObjectName("sectionSummary")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)
        self.body = QWidget()
        self.grid = QGridLayout(self.body)
        self.grid.setContentsMargins(14, 2, 14, 12)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(6)
        lay.addWidget(self.body)
        self.is_open = None
        self.set_open(open_)

    def set_open(self, on):
        if on == self.is_open:
            return
        self.is_open = on
        self.body.setVisible(on)
        self.summary.setVisible(not on and bool(self.summary.text()))
        self.setProperty("open", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self._head_text()

    def _head_text(self):
        # цветная метка — иконкой; ▾ / ▸ — раздел открыт / свёрнут
        self.head.setText(f"{self.title}   {'▾' if self.is_open else '▸'}")

    def set_summary(self, text):
        self.summary.setText(text)
        self.summary.setVisible(not self.is_open and bool(text))


def _dot_icon(color):
    from PySide6.QtGui import QIcon, QPixmap
    pm = QPixmap(px(12), px(12))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(1, 1, px(10), px(10))
    p.end()
    return QIcon(pm)


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
            if isinstance(w, Collapsible):
                w.set_open(True)         # поле в свёрнутом разделе — раскрыть
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


def compact_combo(combo, chars=24):
    """Ширина списка не растёт под самое длинное название (иначе раздвигается вся страница);
    полный текст виден в раскрытом списке и в подсказке."""
    from PySide6.QtWidgets import QComboBox
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(chars)
    combo.view().setMinimumWidth(px(420))
    if not getattr(combo, "_tip_hooked", False):
        combo.currentTextChanged.connect(combo.setToolTip)
        combo._tip_hooked = True
    combo.setToolTip(combo.currentText())


def fill_groups(combo, tooltips=False):
    """Список групп сталей (встроенные и свои марки) с разделителями по семействам.
    Выбор сохраняется; сигнал о смене — только если выбранной группы больше нет.
    Возвращает True, если выбор изменился."""
    from core.data import GROUPS
    compact_combo(combo)
    cur = combo.currentText()
    names = [combo.itemText(i) for i in range(combo.count()) if combo.itemText(i)]
    if names == list(GROUPS) and cur in GROUPS:
        return False
    combo.blockSignals(True)
    combo.clear()
    family = None
    for name, grp in GROUPS.items():
        if grp.get("family") != family:
            if family is not None:
                combo.insertSeparator(combo.count())
            family = grp.get("family")
        combo.addItem(name)
        if tooltips:
            combo.setItemData(combo.count() - 1, f"{family}\n{name}", Qt.ItemDataRole.ToolTipRole)
    changed = cur not in GROUPS
    if not changed:
        combo.setCurrentText(cur)
    combo.blockSignals(False)
    if changed:
        combo.currentIndexChanged.emit(combo.currentIndex())
    return changed


SHARE_ROLE = Qt.ItemDataRole.UserRole + 1     # доля 0…1 и цвет полоски: (доля, "#rrggbb")


class ShareBarDelegate(QStyledItemDelegate):
    """Ячейка с полоской доли под текстом (структура себестоимости)."""

    def paint(self, painter, option, index):
        data = index.data(SHARE_ROLE)
        if data:
            share, color = data
            r = option.rect.adjusted(px(6), px(7), -px(6), -px(7))
            c = QColor(color)
            c.setAlpha(70)
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(c)
            w = max(px(3), r.width() * min(max(share, 0.0), 1.0))
            painter.drawRoundedRect(r.x(), r.y(), w, r.height(), px(4), px(4))
            painter.restore()
        super().paint(painter, option, index)


def dot_icon(color):
    return _dot_icon(color)
