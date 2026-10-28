"""Всплывающие уведомления в углу окна: «сохранено», «готово», предупреждения.
Появляются плавно, исчезают сами через несколько секунд или по щелчку; несколько — стопкой."""
from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QVBoxLayout,
                               QWidget)

from ui.anim import ANIM
from ui.theme import T, px

KINDS = {"ok": ("✓", "ok"), "warn": ("!", "accent"), "error": ("✕", "warn"), "info": ("i", "line")}
OK_COLOR = "#2ECC8F"
_shown = []          # уведомления на экране, снизу вверх


class Toast(QFrame):
    def __init__(self, host, text, kind="ok", detail=None, ms=4200):
        super().__init__(host)
        self.setObjectName("toast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        icon, color_key = KINDS.get(kind, KINDS["info"])
        color = OK_COLOR if color_key == "ok" else T[color_key]
        lay = QHBoxLayout(self)
        lay.setContentsMargins(px(14), px(11), px(16), px(11))
        lay.setSpacing(px(10))
        ic = QLabel()
        ic.setPixmap(_badge(icon, color))
        lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(px(2))
        t = QLabel(text)
        t.setObjectName("toastTitle")
        t.setWordWrap(True)
        col.addWidget(t)
        if detail:
            d = QLabel(detail)
            d.setObjectName("toastText")
            d.setWordWrap(True)
            col.addWidget(d)
        lay.addLayout(col, 1)
        self.setFixedWidth(px(360))
        self.adjustSize()
        self.fx = QGraphicsOpacityEffect(self)
        self.fx.setOpacity(0.0)
        self.setGraphicsEffect(self.fx)
        self._closing = False
        QTimer.singleShot(ms, self.close_soft)

    def mousePressEvent(self, event):
        self.close_soft()

    def show_at(self, pos):
        self.move(pos + QPoint(0, px(16)))
        self.show()
        self.raise_()
        if not ANIM["on"]:
            self.fx.setOpacity(1.0)
            self.move(pos)
            return
        self._a1 = QPropertyAnimation(self.fx, b"opacity", self)
        self._a1.setDuration(220)
        self._a1.setEndValue(1.0)
        self._a2 = QPropertyAnimation(self, b"pos", self)
        self._a2.setDuration(260)
        self._a2.setEndValue(pos)
        self._a2.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._a1.start()
        self._a2.start()

    def close_soft(self):
        if self._closing:
            return
        self._closing = True
        if not ANIM["on"]:
            self._gone()
            return
        self._a3 = QPropertyAnimation(self.fx, b"opacity", self)
        self._a3.setDuration(220)
        self._a3.setEndValue(0.0)
        self._a3.finished.connect(self._gone)
        self._a3.start()

    def _gone(self):
        if self in _shown:
            _shown.remove(self)
        self.deleteLater()
        _relayout()


def _badge(glyph, color):
    """Круглый значок уведомления: кольцо и символ."""
    from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
    size = px(26)
    pm = QPixmap(size * 2, size * 2)       # вдвое крупнее — чёткий на любом масштабе
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(color), 2))
    p.drawEllipse(1, 1, size - 2, size - 2)
    f = QFont()
    f.setBold(True)
    f.setPixelSize(int(size * 0.5))
    p.setFont(f)
    p.drawText(0, 0, size, size, Qt.AlignmentFlag.AlignCenter, glyph)
    p.end()
    return pm


def _relayout():
    """Стопка снизу вверх в правом нижнем углу окна."""
    alive = []
    for t in _shown:
        try:
            t.isVisible()
            alive.append(t)
        except RuntimeError:            # виджет уже удалён
            pass
    _shown[:] = alive
    y = None
    for t in _shown:
        host = t.parentWidget()
        if y is None:
            y = host.height() - px(24)
        y -= t.height()
        t.target = QPoint(host.width() - t.width() - px(24), y)
        if t.isVisible():
            t.move(t.target)
        y -= px(10)


def notify(widget, text, kind="ok", detail=None, ms=4200):
    """Уведомление в окне, к которому относится widget. kind: ok, warn, error, info."""
    host = widget.window() if isinstance(widget, QWidget) else widget
    toast = Toast(host, text, kind, detail, ms)
    _shown.append(toast)
    _relayout()
    toast.show_at(toast.target)
    return toast
