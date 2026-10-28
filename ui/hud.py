"""Фон панелей и карточек, линия заголовка, фон раздела. Рисуются вручную (QPainter): так
получаются мягкие градиенты и скругления, которых нет в таблице стилей Qt."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QFrame, QWidget

from ui.theme import T, px


def paint_hud(p, rect, cut=None, tick=True, accent=None):
    """Карточка: скруглённый фон с мягким вертикальным градиентом, тонкая рамка и светлый блик
    по верхнему краю. tick — короткая акцентная полоска слева сверху (для карточек результатов)."""
    radius = px(14) if cut is None else cut + px(4)
    r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    g.setColorAt(0, QColor(T["surface2"]))
    g.setColorAt(1, QColor(T["surface"]))
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(T["border"]), 1))
    p.setBrush(g)
    p.drawPath(path)
    hl = QColor(T["text"])
    hl.setAlpha(14)
    p.setPen(QPen(hl, 1))
    p.drawLine(QPointF(r.left() + radius, r.top() + 1), QPointF(r.right() - radius, r.top() + 1))
    if tick:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(accent or T["accent"]))
        p.drawRoundedRect(QRectF(r.left() + px(16), r.top() - 0.5, px(28), px(3)), 1.5, 1.5)


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
        g = QLinearGradient(QPointF(0, y), QPointF(w, y))
        a, b = QColor(T["accent"]), QColor(T["border"])
        b.setAlpha(0)
        g.setColorAt(0, a)
        g.setColorAt(0.12, QColor(T["border"]))
        g.setColorAt(1, b)
        p.setPen(QPen(g, 1.5))
        p.drawLine(QPointF(0, y), QPointF(w, y))
        p.end()


def paint_grid(p, rect):
    """Фон раздела: ровный цвет и мягкое акцентное свечение в верхнем углу."""
    p.fillRect(rect, QColor(T["bg"]))
    glow = QColor(T["accent"])
    glow.setAlpha(18 if T["bg"].lower() < "#808080" else 30)
    g = QRadialGradient(QPointF(rect.right() - rect.width() * 0.15, rect.top()),
                        max(rect.width(), rect.height()) * 0.55)
    g.setColorAt(0, glow)
    glow.setAlpha(0)
    g.setColorAt(1, glow)
    p.fillRect(rect, g)
