"""График маршрута: диаметр по проходам, отжиги и вытяжка."""
from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from core.util import fmt
from ui.anim import ANIM
from ui.hud import paint_hud
from ui.theme import DISPLAY_FAMILIES, T, px, scale


class RouteChart(QWidget):
    def __init__(self):
        super().__init__()
        self.rows, self.d0 = [], None
        self._prog = 1.0
        self.setMinimumHeight(px(200))
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(520)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._step)

    def _step(self, v):
        self._prog = float(v)
        self.update()

    def set_data(self, d0, rows):
        # прорисовка заново — только когда маршрут меняется по существу (число проходов),
        # а не при каждом нажатии клавиши
        redraw = bool(rows) and (len(rows) != len(self.rows))
        self.d0, self.rows = d0, rows
        if redraw and ANIM["on"] and self.isVisible():
            self._anim.stop()
            self._prog = 0.0
            self._anim.start()
        elif not self._anim.state() == QVariantAnimation.State.Running:
            self._prog = 1.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_hud(p, self.rect())
        r = QRectF(self.rect())
        font = p.font()
        font.setFamilies(DISPLAY_FAMILIES)
        font.setPointSizeF(8.5 * scale())
        p.setFont(font)
        if not self.rows:
            p.setPen(QColor(T["muted"]))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "ГРАФИК ПОЯВИТСЯ ПОСЛЕ РАСЧЁТА")
            p.end()
            return

        left, right, top = px(56), px(22), px(34)
        W, H = r.width(), r.height()
        plot = QRectF(left, top, W - left - right, H - top - px(30))
        n = len(self.rows)
        xs = [plot.left() + plot.width() * i / n for i in range(n + 1)]
        ds = [self.d0] + [x["d_out"] for x in self.rows]
        dmax = max(ds) * 1.08

        def y(d):
            return plot.bottom() - d / dmax * plot.height()

        p.setPen(QColor(T["muted"]))
        p.drawText(QRectF(left, px(10), plot.width(), 18), Qt.AlignmentFlag.AlignLeft,
                   "ДИАМЕТР ПО ПРОХОДАМ, ММ")
        grid = QColor(T["grid"])
        for k in range(5):
            val = dmax * k / 4
            yy = y(val)
            p.setPen(QPen(grid, 1))
            p.drawLine(QPointF(plot.left(), yy), QPointF(plot.right(), yy))
            p.setPen(QColor(T["tertiary"]))
            p.drawText(QRectF(0, yy - 8, left - 10, 16),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, fmt(val, 1))

        for i, row in enumerate(self.rows):
            if row["anneal"]:
                xx = xs[i]
                p.setPen(QPen(QColor(T["accent"]), 1.4, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(xx, plot.top()), QPointF(xx, plot.bottom()))
                p.setPen(QColor(T["accent"]))
                p.drawText(QRectF(xx + 5, plot.top(), 90, 16), Qt.AlignmentFlag.AlignLeft, "ОТЖИГ")

        p.save()
        p.setClipRect(QRectF(0, 0, plot.left() + plot.width() * self._prog + px(6), H))
        path = QPainterPath()
        path.moveTo(xs[0], y(ds[0]))
        for i in range(1, n + 1):
            path.lineTo(xs[i], y(ds[i]))
        line = QColor(T["line"])
        # свечение: широкий полупрозрачный след под основной линией
        for width, alpha in ((9, 28), (5, 60)):
            c = QColor(line)
            c.setAlpha(alpha)
            p.setPen(QPen(c, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        p.setPen(QPen(line, 2))
        p.drawPath(path)
        p.setBrush(QColor(T["surface"]))
        for i in range(n + 1):
            p.drawEllipse(QPointF(xs[i], y(ds[i])), 3, 3)

        p.restore()
        p.setPen(QColor(T["tertiary"]))
        step = max(1, n // 15)
        for i in range(0, n + 1, step):          # номера узлов: 0 — заготовка, далее проходы
            p.drawText(QRectF(xs[i] - 14, plot.bottom() + 4, 28, 14),
                       Qt.AlignmentFlag.AlignCenter, str(i))
        p.end()
