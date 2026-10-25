"""Элементы в стиле HUD: панели со срезанными углами, акцентные метки, линия заголовка, сетка фона.
Рисуются вручную (QPainter): таблица стилей Qt не умеет срезанные углы."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QWidget

from ui.theme import T, px


def hud_path(r, cut):
    """Контур со срезанными верхним правым и нижним левым углами."""
    path = QPainterPath()
    path.moveTo(r.left(), r.top())
    path.lineTo(r.right() - cut, r.top())
    path.lineTo(r.right(), r.top() + cut)
    path.lineTo(r.right(), r.bottom())
    path.lineTo(r.left() + cut, r.bottom())
    path.lineTo(r.left(), r.bottom() - cut)
    path.closeSubpath()
    return path


def paint_hud(p, rect, cut=None, tick=True, accent=None):
    """Фон с лёгким вертикальным градиентом, тонкая рамка и акцентная метка в левом верхнем углу."""
    cut = px(12) if cut is None else cut
    r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
    path = hud_path(r, cut)
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    g.setColorAt(0, QColor(T["surface2"]))
    g.setColorAt(1, QColor(T["surface"]))
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(T["border"]), 1))
    p.setBrush(g)
    p.drawPath(path)
    if tick:
        a = QColor(accent or T["accent"])
        p.setPen(QPen(a, 2))
        p.drawLine(QPointF(r.left() + 1, r.top() + 1), QPointF(r.left() + px(26), r.top() + 1))
        p.drawLine(QPointF(r.left() + 1, r.top() + 1), QPointF(r.left() + 1, r.top() + px(10)))
        # маленький маркер на срезанном углу
        p.setPen(QPen(QColor(T["tertiary"]), 1))
        p.drawLine(QPointF(r.right() - cut + px(4), r.top() + px(2)),
                   QPointF(r.right() - px(2), r.top() + cut - px(4)))


class HudPanel(QFrame):
    """Панель для форм ввода."""

    def __init__(self, tick=True):
        super().__init__()
        self.setObjectName("panel")
        self._tick = tick

    def paintEvent(self, event):
        p = QPainter(self)
        paint_hud(p, self.rect(), tick=self._tick)
        p.end()


class HudRule(QWidget):
    """Линия под заголовком раздела: акцентный сегмент слева и метки справа."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(px(10))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, y = self.width(), self.height() / 2
        p.setPen(QPen(QColor(T["border"]), 1))
        p.drawLine(QPointF(0, y), QPointF(w, y))
        p.setPen(QPen(QColor(T["accent"]), 2))
        p.drawLine(QPointF(0, y), QPointF(px(64), y))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T["tertiary"]))
        for i in range(3):
            x = w - px(8) - i * px(10)
            p.drawRect(QRectF(x, y - px(2), px(4), px(4)))
        p.end()


def paint_grid(p, rect):
    """Едва заметная техническая сетка на фоне раздела."""
    p.fillRect(rect, QColor(T["bg"]))
    c = QColor(T["grid"])
    c.setAlpha(110)
    p.setPen(QPen(c, 1))
    step = px(40)
    x = rect.left()
    while x < rect.right():
        p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        x += step
    y = rect.top()
    while y < rect.bottom():
        p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        y += step
