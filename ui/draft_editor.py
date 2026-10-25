"""Редактор обжатий: столбец — обжатие на проходе, его можно потянуть мышью.

Цвет ползунка — близость к допустимому обжатию за проход для группы сталей (из справочника групп,
то есть из литературы): бирюзовый — запас, жёлтый — близко, оранжевый — у предела, красный — выше.
Полоса под столбцами — использование прочности: какая доля прочности проволоки уходит на
напряжение волочения (σвол / σв = 1 / запас прочности); предел — 1 / 1,4 ≈ 71 % (Радионова и др.).
"""
from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from core.thermal import T_AGING
from core.util import fmt
from ui.anim import ANIM
from ui.hud import paint_hud
from ui.theme import DISPLAY_FAMILIES, T, px, scale

ORANGE = "#FF8A1F"


def _mix(a, b, t):
    ca, cb = QColor(a), QColor(b)
    t = max(0.0, min(1.0, t))
    return QColor(int(ca.red() + (cb.red() - ca.red()) * t),
                  int(ca.green() + (cb.green() - ca.green()) * t),
                  int(ca.blue() + (cb.blue() - ca.blue()) * t))


def zone_color(x):
    """x — доля от предела (1,0 = на пределе). До 70 % — бирюзовый, к 90 % — жёлтый,
    к 100 % — оранжевый, выше — красный."""
    if x <= 0.70:
        return QColor(T["line"])
    if x <= 0.90:
        return _mix(T["line"], T["accent"], (x - 0.70) / 0.20)
    if x <= 1.00:
        return _mix(T["accent"], ORANGE, (x - 0.90) / 0.10)
    return _mix(ORANGE, T["warn"], (x - 1.00) / 0.05)


def zone_text(x):
    if x <= 0.70:
        return "норма"
    if x <= 0.90:
        return "заметная нагрузка"
    if x <= 1.00:
        return "у предела"
    return "выше предела"


class DraftEditor(QWidget):
    dragged = Signal(int, float)      # проход, новая вытяжка
    released = Signal()
    unpinned = Signal(int)

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setMinimumHeight(px(330))
        self.rows, self.forces, self.thermal = [], [], []
        self.crit_lam, self.gmin, self.pinned = 1.3, 1.4, set()
        self.hover = None
        self.drag = None
        self._frozen_max = None
        self._prog = 1.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(480)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._step)

    def _step(self, v):
        self._prog = float(v)
        self.update()

    # ---------- данные ----------
    def set_data(self, rows, forces, thermal, crit_lam, gmin, pinned):
        grow = bool(rows) and len(rows) != len(self.rows) and self.drag is None
        self.rows, self.forces, self.thermal = rows, forces, thermal
        self.crit_lam, self.gmin, self.pinned = crit_lam, gmin, set(pinned)
        if grow and ANIM["on"] and self.isVisible():
            self._anim.stop()
            self._prog = 0.0
            self._anim.start()
        elif self._anim.state() != QVariantAnimation.State.Running:
            self._prog = 1.0
        if not rows:
            self.hover = self.drag = None
        self.update()

    # ---------- геометрия ----------
    def _crit(self):
        return (1 - 1 / self.crit_lam) * 100

    def _scale_max(self):
        if self._frozen_max is not None:
            return self._frozen_max
        reds = [r["red"] for r in self.rows] or [10]
        top = max(self._crit() * 1.45, max(reds) * 1.15, 10)
        step = 5 if top <= 40 else 10
        return step * (int(top / step) + 1)

    def _layout(self):
        W, H = self.width(), self.height()
        left, right, top = px(52), px(18), px(46)
        strip_h, labels_h = px(54), px(40)
        plot = QRectF(left, top, W - left - right, H - top - strip_h - labels_h - px(18))
        strip = QRectF(left, plot.bottom() + px(26), plot.width(), strip_h)
        return plot, strip

    def _slot(self, i, plot):
        n = len(self.rows)
        w = plot.width() / n
        return plot.left() + w * i, w

    def _index_at(self, x):
        plot, _ = self._layout()
        if not self.rows or not plot.left() <= x <= plot.right():
            return None
        i = int((x - plot.left()) / (plot.width() / len(self.rows)))
        return min(max(i, 0), len(self.rows) - 1)

    def _y_of(self, red, plot):
        return plot.bottom() - red / self._scale_max() * plot.height()

    # ---------- мышь ----------
    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or not self.rows:
            return
        i = self._index_at(e.position().x())
        if i is None:
            return
        self.drag = i
        self._frozen_max = self._scale_max()        # шкала не прыгает, пока тянем
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self._emit_drag(e.position().y())

    def mouseMoveEvent(self, e):
        if self.drag is not None:
            self._emit_drag(e.position().y())
            return
        i = self._index_at(e.position().x())
        if i != self.hover:
            self.hover = i
            self.update()
        self.setCursor(Qt.CursorShape.SizeVerCursor if i is not None
                       else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, e):
        if self.drag is not None:
            self.hover = self.drag
            self.drag = None
            self._frozen_max = None
            self.released.emit()
            self.update()

    def mouseDoubleClickEvent(self, e):
        i = self._index_at(e.position().x())
        if i is not None and i in self.pinned:
            self.unpinned.emit(i)

    def leaveEvent(self, e):
        if self.drag is None:
            self.hover = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()

    def _emit_drag(self, y):
        plot, _ = self._layout()
        red = (plot.bottom() - y) / plot.height() * self._scale_max()
        red = min(max(red, 1.0), 44.0)
        self.dragged.emit(self.drag, 1 / (1 - red / 100))

    # ---------- рисование ----------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_hud(p, self.rect())
        font = p.font()
        font.setFamilies(DISPLAY_FAMILIES)
        font.setPointSizeF(8.5 * scale())
        p.setFont(font)
        W = self.width()
        if not self.rows:
            p.setPen(QColor(T["muted"]))
            p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter,
                       "РЕДАКТОР ОБЖАТИЙ ПОЯВИТСЯ ПОСЛЕ РАСЧЁТА")
            p.end()
            return
        plot, strip = self._layout()
        crit, smax, n = self._crit(), self._scale_max(), len(self.rows)

        # заголовок и легенда
        p.setPen(QColor(T["muted"]))
        p.drawText(QRectF(plot.left(), px(12), plot.width(), 18), Qt.AlignmentFlag.AlignLeft,
                   "ОБЖАТИЕ ПО ПРОХОДАМ, %  ·  ТЯНИ СТОЛБЕЦ МЫШЬЮ")
        lx = W - px(18)
        for text, col in (("выше предела", T["warn"]), ("у предела", ORANGE),
                          ("близко", T["accent"]), ("норма", T["line"])):
            tw = p.fontMetrics().horizontalAdvance(text)
            lx -= tw
            p.setPen(QColor(T["muted"]))
            p.drawText(QPointF(lx, px(24)), text)
            lx -= px(14)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(col))
            p.drawRect(QRectF(lx, px(16), px(9), px(9)))
            lx -= px(14)

        # сетка и шкала
        step = 5 if smax <= 40 else 10
        v = 0
        while v <= smax + 1e-9:
            yy = self._y_of(v, plot)
            p.setPen(QPen(QColor(T["grid"]), 1))
            p.drawLine(QPointF(plot.left(), yy), QPointF(plot.right(), yy))
            p.setPen(QColor(T["tertiary"]))
            p.drawText(QRectF(0, yy - 8, plot.left() - px(8), 16),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{v:g}")
            v += step

        # зона у предела и линия предела группы
        y_crit, y_90 = self._y_of(crit, plot), self._y_of(crit * 0.9, plot)
        zone = QColor(T["warn"])
        zone.setAlpha(22)
        p.fillRect(QRectF(plot.left(), y_crit, plot.width(), y_90 - y_crit), zone)
        p.setPen(QPen(QColor(T["warn"]), 1.4, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(plot.left(), y_crit), QPointF(plot.right(), y_crit))
        p.setPen(QColor(T["warn"]))
        p.drawText(QRectF(plot.left(), y_crit - px(17), plot.width() - px(4), 14),
                   Qt.AlignmentFlag.AlignRight,
                   f"ПРЕДЕЛ ЗА ПРОХОД ДЛЯ ГРУППЫ {fmt(crit, 1)} %")

        # отжиги
        for i, r in enumerate(self.rows):
            if r.get("anneal"):
                x0, _ = self._slot(i, plot)
                p.setPen(QPen(QColor(T["accent"]), 1.2, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(x0, plot.top()), QPointF(x0, strip.bottom()))
                p.setPen(QColor(T["accent"]))
                p.drawText(QPointF(x0 + px(4), plot.top() + px(10)), "ОТЖИГ")

        # столбцы обжатия с ползунками
        show_all = n <= 16
        for i, r in enumerate(self.rows):
            x0, w = self._slot(i, plot)
            bw = w * 0.58
            cx = x0 + w / 2
            ratio = r["red"] / crit
            col = zone_color(ratio)
            y_top = self._y_of(r["red"] * self._prog, plot)
            active = i in (self.hover, self.drag)
            g = QLinearGradient(QPointF(cx, y_top), QPointF(cx, plot.bottom()))
            c1, c2 = QColor(col), QColor(col)
            c1.setAlpha(210 if active else 170)
            c2.setAlpha(40)
            g.setColorAt(0, c1)
            g.setColorAt(1, c2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawRect(QRectF(cx - bw / 2, y_top, bw, plot.bottom() - y_top))
            # ползунок: свечение, если наведён или тянется
            hw, hh = max(bw * 1.25, px(14)), px(7)
            if active:
                glow = QColor(col)
                glow.setAlpha(70)
                p.setBrush(glow)
                p.drawRoundedRect(QRectF(cx - hw / 2 - px(4), y_top - hh / 2 - px(4),
                                         hw + px(8), hh + px(8)), px(5), px(5))
            p.setBrush(col)
            p.drawRoundedRect(QRectF(cx - hw / 2, y_top - hh / 2, hw, hh), px(3), px(3))
            if i in self.pinned:          # закреплённый проход — ромбик над ползунком
                p.setBrush(QColor(T["text"]))
                d = px(4)
                p.drawPolygon(QPolygonF([QPointF(cx, y_top - hh - d * 2),
                                         QPointF(cx + d, y_top - hh - d),
                                         QPointF(cx, y_top - hh), QPointF(cx - d, y_top - hh - d)]))
            if show_all or active:
                p.setPen(QColor(T["text"]) if active else QColor(T["muted"]))
                p.drawText(QRectF(cx - px(28), y_top - hh - px(26), px(56), 14),
                           Qt.AlignmentFlag.AlignCenter, fmt(r["red"], 1))

        # полоса использования прочности
        p.setPen(QColor(T["muted"]))
        p.drawText(QRectF(plot.left(), strip.top() - px(18), plot.width(), 14),
                   Qt.AlignmentFlag.AlignLeft,
                   f"ИСПОЛЬЗОВАНИЕ ПРОЧНОСТИ ПРОВОЛОКИ, %  ·  ПРЕДЕЛ {fmt(100 / self.gmin, 0)} % "
                   f"(ЗАПАС {fmt(self.gmin, 2)})")
        lim = 1 / self.gmin
        p.setPen(QPen(QColor(T["warn"]), 1, Qt.PenStyle.DashLine))
        y_lim = strip.bottom() - lim * strip.height()
        p.drawLine(QPointF(strip.left(), y_lim), QPointF(strip.right(), y_lim))
        p.setPen(Qt.PenStyle.NoPen)
        for i, f in enumerate(self.forces):
            x0, w = self._slot(i, plot)
            bw = w * 0.58
            load = 1 / f["gamma"]
            h = min(load, 1.0) * strip.height() * self._prog
            p.setBrush(zone_color(load / lim))
            p.drawRect(QRectF(x0 + w / 2 - bw / 2, strip.bottom() - h, bw, h))
        p.setPen(QColor(T["tertiary"]))
        step_n = max(1, n // 18)
        for i in range(0, n, step_n):
            x0, w = self._slot(i, plot)
            p.drawText(QRectF(x0, strip.bottom() + px(4), w, 14), Qt.AlignmentFlag.AlignCenter,
                       str(i + 1))

        k = self.drag if self.drag is not None else self.hover
        if k is not None and k < n:
            self._paint_info(p, k, plot)
        p.end()

    def _paint_info(self, p, k, plot):
        r, f = self.rows[k], self.forces[k]
        t = self.thermal[k] if k < len(self.thermal) else None
        crit = self._crit()
        ratio = r["red"] / crit
        load = 1 / f["gamma"] / (1 / self.gmin)
        lines = [
            (f"ПРОХОД {k + 1}" + ("  ·  ЗАКРЕПЛЁН" if k in self.pinned else ""), T["text"]),
            (f"Диаметр {fmt(r['d_in'], 3)} → {fmt(r['d_out'], 3)} мм", T["muted"]),
            (f"Обжатие {fmt(r['red'], 1)} % из {fmt(crit, 1)} % — {zone_text(ratio)}",
             zone_color(ratio).name()),
            (f"Вытяжка {fmt(r['lam'], 3)}", T["muted"]),
            (f"Запас прочности {fmt(f['gamma'], 2)} (не ниже {fmt(self.gmin, 2)})",
             zone_color(load).name()),
            (f"Усилие {fmt(f['P'] / 1000, 2)} кН  ·  мощность {fmt(f['power'], 1)} кВт",
             T["muted"]),
        ]
        if t:
            lines.append((f"Температура на выходе {fmt(t['t_out'], 0)} °C",
                          zone_color(t["t_out"] / T_AGING).name()))
        if r.get("anneal"):
            lines.append(("Перед проходом — отжиг", T["accent"]))
        fm = p.fontMetrics()
        lh = fm.height() + px(3)
        bw = max(fm.horizontalAdvance(s) for s, _ in lines) + px(24)
        bh = lh * len(lines) + px(16)
        x0, w = self._slot(k, plot)
        bx = x0 + w + px(10)
        if bx + bw > self.width() - px(8):
            bx = x0 - bw - px(10)
        by = plot.top() + px(6)
        box = QRectF(bx, by, bw, bh)
        bg = QColor(T["surface"])
        bg.setAlpha(240)
        p.setPen(QPen(QColor(T["accent"]), 1))
        p.setBrush(bg)
        p.drawRect(box)
        for j, (s, c) in enumerate(lines):
            p.setPen(QColor(c))
            p.drawText(QPointF(bx + px(12), by + px(8) + lh * j + fm.ascent()), s)
