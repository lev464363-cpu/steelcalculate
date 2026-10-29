"""Вкладка «Деформация» в результатах маршрута: модель очага деформации по проходам,
разрез волоки с раскраской по накопленной деформации, профили по сечению, связка с DEFORM."""
import math
import os

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QGridLayout, QHBoxLayout, QInputDialog,
                               QLabel, QMessageBox, QSlider, QVBoxLayout, QWidget)

from core import deform_link as dl
from core.deform_model import route_deformation
from core.dies import bearing_share
from core.route_plan import plan_route
from core.util import InputError, fmt
from ui.popup import notify
from ui.theme import T, px
from ui.widgets import Card, button, fill_table, label, make_table

HEAD = ["№", "φ", "ε пов.", "ε ось", "Σε пов.", "Σε ось", "σв пов., МПа", "σв ось, МПа",
        "σвол Avitzur, МПа", "σвол Зибель, МПа", "Δ", "Оценка"]
TIPS = ["Номер прохода", "Коэффициент неравномерности: средняя деформация / однородная",
        "Деформация за проход у поверхности", "Деформация за проход в оси",
        "Накопленная от катанки или отжига — у поверхности", "Накопленная — в оси",
        "Прочность у поверхности", "Прочность в оси",
        "Напряжение волочения по верхней оценке Avitzur", "Напряжение волочения по Зибелю "
        "(им считаются усилие и запас прочности)", "Параметр очага деформации (Wright)",
        "Риск разрыва сердцевины по Δ"]
# шкала цвета деформации: синий → голубой → бирюзовый → жёлтый → красный
STOPS = [(0.0, (44, 62, 145)), (0.25, (31, 143, 209)), (0.5, (37, 194, 160)),
         (0.75, (242, 208, 36)), (1.0, (232, 70, 58))]


def cmap(x):
    x = min(max(x, 0.0), 1.0)
    for (a, ca), (b, cb) in zip(STOPS, STOPS[1:]):
        if x <= b:
            t = (x - a) / (b - a) if b > a else 0
            return QColor(*(int(ca[i] + (cb[i] - ca[i]) * t) for i in range(3)))
    return QColor(*STOPS[-1][1])


def _interp(xs, ys, x):
    x = min(max(x, 0.0), 1.0)
    for i in range(len(xs) - 1):
        if x <= xs[i + 1]:
            t = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + (ys[i + 1] - ys[i]) * t
    return ys[-1]


class DieView(QWidget):
    """Осевое сечение прохода: волока, проволока с полем накопленной деформации, линии тока,
    сферические границы очага (модель Avitzur)."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(px(250))
        self.data = None
        self._cache = {}

    def set_pass(self, data):
        """data: d_in, d_out, alpha, bearing, prev (Σε до прохода по ξ), inc (за проход по ξ),
        xs, k_shear, vmax (верх шкалы), title."""
        self.data = data
        self.update()

    def _strain(self, z, r, g):
        """Накопленная деформация в точке (z, r) сечения, мм."""
        if r > g["R0"] + 1e-9:
            return None
        rho = math.hypot(g["za"] - z, r)
        th = math.atan2(r, g["za"] - z)
        d = self.data
        if rho >= g["rho0"]:
            if r > g["R0"]:
                return None
            return _interp(d["xs"], d["prev"], r / g["R0"])
        if rho <= g["rhof"]:
            if r > g["Rf"] + 1e-9:
                return None
            xi = r / g["Rf"]
            return _interp(d["xs"], d["prev"], xi) + _interp(d["xs"], d["inc"], xi)
        if th > g["a"] + 1e-9:
            return None
        xi = math.sin(th) / math.sin(g["a"])
        shear = 1 / math.sqrt(3) * math.tan(th) * d["k_shear"]
        inner = 2 * math.log(g["rho0"] / rho) * math.sqrt(1 - 11 / 12 * math.sin(th) ** 2)
        return _interp(d["xs"], d["prev"], xi) + shear + inner

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        if not self.data:
            p.setPen(QColor(T["muted"]))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Нет маршрута")
            p.end()
            return
        d = self.data
        a = math.radians(d["alpha"])
        R0, Rf = d["d_in"] / 2, d["d_out"] / 2
        r_entry = R0 * 1.15
        za = r_entry / math.tan(a)                 # вершина конуса волоки (вход волоки — z = 0)
        g = dict(a=a, R0=R0, Rf=Rf, za=za, rho0=R0 / math.sin(a), rhof=Rf / math.sin(a))
        z_cone = (r_entry - Rf) / math.tan(a)
        z_bear = z_cone + d["bearing"]
        z_touch = (r_entry - R0) / math.tan(a)
        z0, z1 = z_touch - 1.6 * d["d_in"], z_bear + 1.4 * d["d_out"]
        r_max = max(R0 * 1.9, R0 + 1.2)
        # масштаб: одинаковый по осям, сечение симметрично относительно оси
        bar_w = px(54)
        sx = (W - px(24) - bar_w) / (z1 - z0)
        sy = (H - px(40)) / (2 * r_max)
        s = min(sx, sy)
        ox = px(12) + ((W - px(24) - bar_w) - (z1 - z0) * s) / 2
        oy = px(28) + (H - px(40)) / 2

        def X(z):
            return ox + (z - z0) * s

        def Y(r):
            return oy - r * s

        # поле деформации — растром, кеш по проходу и размеру
        key = (d["key"], W, H)
        img = self._cache.get(key)
        if img is None:
            img = self._raster(g, X, Y, s, z0, z1, R0, W, H, d["vmin"], d["vmax"])
            self._cache = {key: img}
        p.drawImage(0, 0, img)
        # волока (обе половины) — не залезая на строку заголовка
        p.setClipRect(QRectF(0, px(26), W - bar_w, H - px(26)))
        die, _ = dl.die_profile(d["d_in"], d["d_out"], d["alpha"], d["bearing"])
        for sign in (1, -1):
            poly = QPolygonF([QPointF(X(z), oy - sign * r * s) for r, z in die])
            p.setPen(QPen(QColor(T["tertiary"]), 1))
            c = QColor(T["surface2"])
            p.setBrush(c)
            p.drawPolygon(poly)
        # линии тока и границы очага
        pen = QPen(QColor(255, 255, 255, 150), 1)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for xi in (0.33, 0.66, 1.0):
            th = math.asin(xi * math.sin(a))
            for sign in (1, -1):
                path = QPainterPath()
                r_up = xi * R0
                z_in = za - g["rho0"] * math.cos(th)
                z_out = za - g["rhof"] * math.cos(th)
                path.moveTo(X(z0), oy - sign * r_up * s)
                path.lineTo(X(z_in), oy - sign * r_up * s)
                path.lineTo(X(z_out), oy - sign * xi * Rf * s)
                path.lineTo(X(z1), oy - sign * xi * Rf * s)
                p.setPen(QPen(QColor(255, 255, 255, 70), 1))
                p.drawPath(path)
        for rho in (g["rho0"], g["rhof"]):
            path = QPainterPath()
            steps = 24
            for k in range(-steps, steps + 1):
                th = a * k / steps
                pt = QPointF(X(za - rho * math.cos(th)), oy - rho * math.sin(th) * s)
                path.moveTo(pt) if k == -steps else path.lineTo(pt)
            p.setPen(pen)
            p.drawPath(path)
        p.setClipping(False)
        # ось
        ax = QPen(QColor(T["muted"]), 1)
        ax.setStyle(Qt.PenStyle.DashDotLine)
        p.setPen(ax)
        p.drawLine(QPointF(X(z0), oy), QPointF(X(z1), oy))
        # подписи
        p.setPen(QColor(T["text"]))
        p.drawText(QRectF(px(12), px(2), W - px(24), px(22)),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, d["title"])
        p.setPen(QColor(T["muted"]))
        p.drawText(QRectF(X(z0), oy + R0 * s + px(4), px(140), px(18)), Qt.AlignmentFlag.AlignLeft,
                   f"Ø {fmt(d['d_in'], 3)}")
        p.drawText(QRectF(X(z1) - px(140), oy + Rf * s + px(4), px(140), px(18)),
                   Qt.AlignmentFlag.AlignRight, f"Ø {fmt(d['d_out'], 3)}")
        p.drawText(QRectF(X(z0), oy - R0 * s - px(22), px(240), px(18)),
                   Qt.AlignmentFlag.AlignLeft, "→ волочение")
        self._colorbar(p, W - bar_w + px(8), px(34), px(12), H - px(56), d["vmin"], d["vmax"],
                       d["scale_label"])
        p.end()

    def _raster(self, g, X, Y, s, z0, z1, R0, W, H, vmin, vmax):
        step = 2                                   # шаг растра, пикселей
        img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        q = QPainter(img)
        q.setPen(Qt.PenStyle.NoPen)
        x_from, x_to = int(X(z0)), int(X(z1))
        oy = Y(0)
        top = int(oy - R0 * s) - 1
        for py in range(top, int(oy) + 1, step):
            r = (oy - py) / s
            if r < 0:
                r = 0.0
            for pxl in range(x_from, x_to, step):
                z = z0 + (pxl - x_from) / s
                e = self._strain(z, r, g)
                if e is None:
                    continue
                c = cmap((e - vmin) / (vmax - vmin) if vmax > vmin else 0)
                q.setBrush(c)
                q.drawRect(pxl, py, step, step)
                q.drawRect(pxl, int(2 * oy - py) - step + 1, step, step)   # нижняя половина
        q.end()
        return img

    def _colorbar(self, p, x, y, w, h, vmin, vmax, title):
        for k in range(h):
            p.setPen(cmap(1 - k / max(h - 1, 1)))
            p.drawLine(QPointF(x, y + k), QPointF(x + w, y + k))
        p.setPen(QColor(T["muted"]))
        for t in (0, 0.5, 1):
            yy = y + (1 - t) * h
            p.drawText(QRectF(x + w + px(4), yy - px(8), px(40), px(16)),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       fmt(vmin + (vmax - vmin) * t, 2))
        p.drawText(QRectF(x - px(10), y - px(20), px(60), px(16)), Qt.AlignmentFlag.AlignLeft,
                   title)


class ProfileChart(QWidget):
    """Слева — накопленная деформация поверхности и оси по проходам; справа — прочность по
    сечению на выбранном проходе."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(px(190))
        self.model, self.sel = None, 0

    def set_data(self, model, sel):
        self.model, self.sel = model, sel
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.model or not self.model["passes"]:
            p.end()
            return
        W, H = self.width(), self.height()
        half = (W - px(16)) / 2
        self._route(p, QRectF(0, 0, half, H))
        self._section(p, QRectF(half + px(16), 0, half, H))
        p.end()

    def _frame(self, p, r, title):
        p.setPen(QColor(T["muted"]))
        p.drawText(QRectF(r.left(), r.top(), r.width(), px(18)), Qt.AlignmentFlag.AlignLeft, title)
        plot = QRectF(r.left() + px(40), r.top() + px(26), r.width() - px(48), r.height() - px(52))
        p.setPen(QPen(QColor(T["border"]), 1))
        p.drawLine(plot.bottomLeft(), plot.bottomRight())
        p.drawLine(plot.bottomLeft(), plot.topLeft())
        return plot

    def _axis_labels(self, p, plot, lo, hi, nd=1):
        p.setPen(QColor(T["muted"]))
        for t in (0, 0.5, 1):
            v = lo + (hi - lo) * t
            y = plot.bottom() - plot.height() * t
            p.drawText(QRectF(plot.left() - px(40), y - px(8), px(36), px(16)),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, fmt(v, nd))

    def _route(self, p, r):
        ps = self.model["passes"]
        plot = self._frame(p, r, "НАКОПЛЕННАЯ Σε ПО ПРОХОДАМ")
        hi = max(x["cum_surface"] for x in ps) * 1.08 or 1
        self._axis_labels(p, plot, 0, hi, 1)
        n = len(ps)

        def pt(i, v):
            x = plot.left() + plot.width() * (i + 0.5) / n
            return QPointF(x, plot.bottom() - plot.height() * v / hi)
        for key, col in (("cum_surface", "#E8463A"), ("cum_center", "#1F8FD1")):
            path = QPainterPath()
            for i, x in enumerate(ps):
                path.moveTo(pt(i, x[key])) if i == 0 or x["anneal"] else path.lineTo(pt(i, x[key]))
            p.setPen(QPen(QColor(col), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        sel = QPointF(pt(self.sel, 0).x(), plot.top())
        pen = QPen(QColor(T["accent"]), 1)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawLine(sel, QPointF(sel.x(), plot.bottom()))
        p.setPen(QColor(T["muted"]))
        for i, x in enumerate(ps):
            if n <= 10 or i % 2 == 0:
                p.drawText(QRectF(pt(i, 0).x() - px(12), plot.bottom() + px(4), px(24), px(14)),
                           Qt.AlignmentFlag.AlignCenter, str(x["i"]))
        self._legend(p, plot, (("поверхность", "#E8463A"), ("ось", "#1F8FD1")))

    def _section(self, p, r):
        x = self.model["passes"][self.sel]
        xs = self.model["xs"]
        plot = self._frame(p, r, f"σв ПО СЕЧЕНИЮ, МПа · ПРОХОД {x['i']}")
        lo, hi = min(x["sig"]) * 0.98, max(x["sig"]) * 1.02
        if hi - lo < 1:
            lo, hi = lo - 1, hi + 1
        self._axis_labels(p, plot, lo, hi, 0)
        path = QPainterPath()
        for k, (xi, v) in enumerate(zip(xs, x["sig"])):
            q = QPointF(plot.left() + plot.width() * xi, plot.bottom() - plot.height() *
                        (v - lo) / (hi - lo))
            path.moveTo(q) if k == 0 else path.lineTo(q)
        p.setPen(QPen(QColor(T["accent"]), 2))
        p.drawPath(path)
        p.setPen(QColor(T["muted"]))
        p.drawText(QRectF(plot.left(), plot.bottom() + px(4), px(60), px(14)),
                   Qt.AlignmentFlag.AlignLeft, "ось")
        p.drawText(QRectF(plot.right() - px(120), plot.bottom() + px(4), px(120), px(16)),
                   Qt.AlignmentFlag.AlignRight, "поверхность")

    def _legend(self, p, plot, items):
        x = plot.left() + px(6)
        for text, col in items:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(col))
            p.drawRect(QRectF(x, plot.top() + px(4), px(10), px(3)))
            p.setPen(QColor(T["muted"]))
            p.drawText(QPointF(x + px(14), plot.top() + px(9)), text)
            x += p.fontMetrics().horizontalAdvance(text) + px(28)


def build_results(page, tabs):
    host = QWidget()
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 12, 0, 0)
    lay.setSpacing(10)
    page.def_cards = [Card("Неравномерность φ, макс."), Card("Σε поверхность / ось"),
                      Card("σв поверхность / ось", "МПа"), Card("Δ макс. / предел")]
    cg = QGridLayout()
    cg.setSpacing(12)
    for i, c in enumerate(page.def_cards):
        cg.addWidget(c, i // 2, i % 2)
    lay.addLayout(cg)
    page.def_view = DieView()
    lay.addWidget(page.def_view)
    nav = QHBoxLayout()
    page.def_prev = button("◀")
    page.def_play = button("▶  Прогнать по маршруту")
    page.def_next = button("▶")
    page.def_slider = QSlider(Qt.Orientation.Horizontal)
    page.def_slider.setMinimum(0)
    page.def_pos = QLabel("")
    for w in (page.def_prev, page.def_slider, page.def_next, page.def_pos, page.def_play):
        nav.addWidget(w, 1 if w is page.def_slider else 0)
    lay.addLayout(nav)
    page.def_cum = QCheckBox("Раскраска по накопленной деформации (иначе — за проход)")
    page.def_cum.setToolTip("За проход — видна неравномерность по сечению в этом проходе; "
                            "накопленная — сколько металл набрал от катанки или отжига.")
    page.def_cum.toggled.connect(lambda *_: _select(page, page.def_slider.value()))
    lay.addWidget(page.def_cum)
    page.def_chart = ProfileChart()
    lay.addWidget(page.def_chart)
    page.def_table = make_table(HEAD)
    for i, tip in enumerate(TIPS):
        page.def_table.horizontalHeaderItem(i).setToolTip(tip)
    page.def_table.setMinimumHeight(px(220))
    lay.addWidget(page.def_table, 1)
    lay.addWidget(label("DEFORM", "section"))
    page.def_use = QCheckBox("Учитывать поправки DEFORM для этой группы")
    page.def_use.setEnabled(False)
    lay.addWidget(page.def_use)
    page.def_calib = label("", "muted", True)
    lay.addWidget(page.def_calib)
    bar = QGridLayout()
    bar.setHorizontalSpacing(8)
    b_exp = button("Выгрузить в DEFORM…")
    b_exp.setToolTip("Волока и заготовка каждого прохода (STL), профиль (DXF), параметры "
                     "процесса и таблица для результатов.")
    b_imp = button("Загрузить результаты DEFORM…")
    b_imp.setToolTip("Заполненная таблица results_template.csv: усилие, деформация на "
                     "поверхности и в оси, повреждаемость.")
    bar.addWidget(b_exp, 0, 0)
    bar.addWidget(b_imp, 0, 1)
    bar.setColumnStretch(2, 1)
    lay.addLayout(bar)
    lay.addWidget(label(
        "Модель очага деформации — верхняя оценка Avitzur (течение по сферическим поверхностям к "
        "вершине конуса): в оси деформация однородная, к поверхности растёт за счёт сдвига на "
        "входе и выходе из очага. Верхняя оценка завышает неравномерность и усилие — их "
        "уточняют поправки по расчётам DEFORM. Формулы — «Справочник → Формулы».", "note", True))
    page.def_model, page.def_timer = None, QTimer(page)
    page.def_timer.setInterval(900)
    page.def_timer.timeout.connect(lambda: _step(page, 1, loop=False))
    page.def_slider.valueChanged.connect(lambda v: _select(page, v))
    page.def_prev.clicked.connect(lambda: _step(page, -1))
    page.def_next.clicked.connect(lambda: _step(page, 1))
    page.def_play.clicked.connect(lambda: _play(page))
    page.def_use.toggled.connect(page.safe_recalc)
    page.checks["route/deform_use"] = page.def_use
    page.checks["route/deform_cum"] = page.def_cum
    b_exp.clicked.connect(lambda: export_deform(page))
    b_imp.clicked.connect(lambda: import_deform(page))
    tabs.addTab(host, "Деформация")


def calibration(page):
    """Активная калибровка DEFORM для группы маршрута и признак, применять ли её."""
    cal = dl.active_calibration(page.group.currentText())
    page.def_use.setEnabled(cal is not None)
    return cal if cal is not None and page.def_use.isChecked() else None, cal


def show(page, res, p, group):
    use, cal = calibration(page)
    if cal:
        page.def_calib.setText(
            f"Поправки DEFORM: усилие ×{fmt(cal.k_force, 2)}, сдвиговая деформация "
            f"×{fmt(cal.k_shear, 2)}" + (f", предел Δ {fmt(cal.delta_limit, 2)}"
                                          if cal.delta_limit else "")
            + f" — по {cal.n_points} проходам." + ("" if use else " Сейчас не применяются."))
    else:
        page.def_calib.setText("Для этой группы поправок DEFORM нет: выгрузи маршрут, рассчитай "
                               "проходы в DEFORM и загрузи результаты.")
    m = route_deformation(res["rows"], res["forces"], p, calib=use)
    page.def_model = m
    ps = m["passes"]
    page.def_cards[0].set(fmt(max(x["phi"] for x in ps), 2))
    last = ps[-1]
    page.def_cards[1].set(f"{fmt(last['cum_surface'], 2)} / {fmt(last['cum_center'], 2)}")
    page.def_cards[2].set(f"{fmt(last['sig'][-1], 0)} / {fmt(last['sig'][0], 0)}")
    page.def_cards[3].set(f"{fmt(m['worst']['delta'], 2)} / {fmt(m['delta_limit'], 1)}")
    rows, colors = [], []
    for x in ps:
        rows.append((x["i"], fmt(x["phi"], 3), fmt(x["surface"], 3), fmt(x["center"], 3),
                     fmt(x["cum_surface"], 3), fmt(x["cum_center"], 3), fmt(x["sig"][-1], 0),
                     fmt(x["sig"][0], 0), fmt(x["sig_d_avitzur"], 0), fmt(x["sig_d_siebel"], 0),
                     fmt(x["delta"], 2), x["risk"] + ("; отжиг перед проходом" if x["anneal"]
                                                      else "")
                     + ("; фасонный — по экв. кругу" if x["i"] in res.get("shaped", [])
                        else "")))
        colors.append((T["warn_soft"], T["warn"]) if x["risk"] == "риск" else
                      (T["anneal"], None) if x["risk"] == "внимание" or x["anneal"] else None)
    fill_table(page.def_table, rows, colors)
    page.def_res, page.def_p, page.def_group = res, p, group
    page.def_slider.blockSignals(True)
    page.def_slider.setMaximum(len(ps) - 1)
    page.def_slider.setValue(min(page.def_slider.value(), len(ps) - 1))
    page.def_slider.blockSignals(False)
    _select(page, page.def_slider.value())


def _select(page, i):
    m = page.def_model
    if not m or not m["passes"]:
        return
    i = min(max(i, 0), len(m["passes"]) - 1)
    x, r = m["passes"][i], page.def_res["rows"][i]
    p = page.def_p
    prev = [c - e for c, e in zip(x["cum"], x["eps"])]
    use, _ = calibration(page)
    bear = bearing_share(page.def_group, r["d_out"] <= 1.6) * r["d_out"]
    risk = {"риск": "риск разрыва сердцевины", "внимание": "растяжение в оси",
            "норма": "норма"}[x["risk"]]
    cum = page.def_cum.isChecked()
    ps = m["passes"]
    # шкала одна на весь маршрут — при листании цвета сравнимы; растянута от min до max
    if cum:
        vmin, vmax = 0.0, max(q["cum_surface"] for q in ps)
    else:
        vmin, vmax = min(q["center"] for q in ps), max(q["surface"] for q in ps)
    page.def_view.set_pass(dict(
        key=(id(m), i, cum), d_in=r["d_in"], d_out=r["d_out"], alpha=p["alpha"], bearing=bear,
        xs=m["xs"], prev=prev if cum else [0.0] * len(prev), inc=x["eps"],
        k_shear=use.k_shear if use else 1.0, vmin=vmin, vmax=vmax,
        scale_label="Σε" if cum else "ε",
        title=f"Проход {x['i']}: Ø {fmt(r['d_in'], 3)} → {fmt(r['d_out'], 3)} мм · 2α = "
              f"{fmt(2 * p['alpha'], 0)}° · Δ = {fmt(x['delta'], 2)} ({risk}) · "
              f"φ = {fmt(x['phi'], 2)}" + (" · после отжига" if x["anneal"] else "")))
    page.def_pos.setText(f"{x['i']} из {len(m['passes'])}")
    page.def_chart.set_data(m, i)


def _step(page, d, loop=True):
    s = page.def_slider
    v = s.value() + d
    if v > s.maximum():
        if not loop:
            page.def_timer.stop()
            page.def_play.setText("▶  Прогнать по маршруту")
            return
        v = 0
    s.setValue(max(v, 0))


def _play(page):
    if page.def_timer.isActive():
        page.def_timer.stop()
        page.def_play.setText("▶  Прогнать по маршруту")
        return
    if page.def_slider.value() >= page.def_slider.maximum():
        page.def_slider.setValue(0)
    page.def_play.setText("❚❚  Пауза")
    page.def_timer.start()


def clear(page):
    page.def_timer.stop()
    for c in page.def_cards:
        c.set("—")
    page.def_table.setRowCount(0)
    page.def_view.set_pass(None)
    page.def_chart.set_data(None, 0)
    page.def_model = None


def export_deform(page):
    if not page.def_model:
        notify(page, "Сначала получи корректный маршрут", "warn")
        return
    root = QFileDialog.getExistingDirectory(page, "Папка для файлов DEFORM",
                                            os.path.expanduser("~"))
    if not root:
        return
    p = page.def_p
    name = f"DEFORM {fmt(p['d0'], 2)}-{fmt(p['dk'], 2)} {page.def_group.split(' (')[0]}"
    folder = os.path.join(root, "".join(ch if ch.isalnum() or ch in " -_.," else "_"
                                        for ch in name).strip())
    try:
        files = dl.export_route(folder, page.def_res["rows"], page.def_res["forces"], p,
                                page.def_group)
    except OSError as e:
        QMessageBox.warning(page, "DEFORM", f"Не удалось записать файлы:\n{e}")
        return
    notify(page, f"Для DEFORM выгружено файлов: {len(files)}", "ok",
           detail=f"{folder}. Порядок работы — в ПРОЧТИ_DEFORM.txt.")


def import_deform(page):
    if not page.def_model:
        notify(page, "Сначала получи корректный маршрут", "warn")
        return
    path, _ = QFileDialog.getOpenFileName(page, "Результаты DEFORM", os.path.expanduser("~"),
                                          "Таблица (*.csv *.txt)")
    if not path:
        return
    try:
        with open(path, encoding="utf-8-sig") as fh:
            text = fh.read()
    except UnicodeDecodeError:
        with open(path, encoding="cp1251") as fh:
            text = fh.read()
    except OSError as e:
        QMessageBox.warning(page, "DEFORM", str(e))
        return
    crit, ok = QInputDialog.getDouble(
        page, "Критическая повреждаемость", "Критическое значение Damage (Cockcroft–Latham)\n"
        "для этого металла; 0 — не учитывать:", 0.0, 0.0, 100.0, 3)
    if not ok:
        return
    try:
        results = dl.parse_results(text)
        # сравнение — с моделью без поправок, иначе поправка наложится сама на себя
        p0 = dict(page.def_p, kF=1.0, dlim=None)
        raw = plan_route(p0, page.def_group, page.mill_profile())
        model = route_deformation(raw["rows"], raw["forces"], p0)["passes"]
        cal = dl.calibrate(results, model, raw["forces"], crit or None)
    except InputError as e:
        QMessageBox.warning(page, "DEFORM", str(e))
        return
    text = (f"Сопоставлено проходов: {len(cal['points'])}.\n\n"
            f"Усилие DEFORM / программа: ×{fmt(cal['k_force'], 3)} (по {cal['n_force']})\n"
            f"Неравномерность DEFORM / модель: ×{fmt(cal['k_shear'], 3)} (по {cal['n_shear']})\n"
            + (f"Предел Δ по повреждаемости: {fmt(cal['delta_limit'], 2)}\n" if cal["delta_limit"]
               else "Критическая повреждаемость не достигнута — предел Δ прежний.\n")
            + f"\nСохранить как поправки для группы «{page.def_group}»?")
    if QMessageBox.question(page, "Поправки DEFORM", text) != QMessageBox.StandardButton.Yes:
        return
    try:
        dl.save_calibration(dict(cal, group=page.def_group, name=os.path.basename(path)))
    except (OSError, ValueError) as e:
        QMessageBox.warning(page, "DEFORM", f"Не удалось сохранить поправки:\n{e}")
        return
    page.def_use.setEnabled(True)
    page.def_use.setChecked(True)
    page.safe_recalc()
    notify(page, "Поправки DEFORM сохранены и применены", "ok",
           detail="Усилие, запас прочности, нагрев и модель деформации пересчитаны.")


def route_inputs(page):
    """Параметры маршрута от поправок DEFORM: множитель усилия kF и предел Δ."""
    use, _ = calibration(page)
    return dict(kF=use.k_force if use else 1.0, dlim=use.delta_limit if use else None)

