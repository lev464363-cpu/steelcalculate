"""Раздел «Маршрут и скорости»: проходы, отжиги, усилия, запас прочности."""
import math

from PySide6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QMessageBox, QVBoxLayout)

from core.data import GROUPS
from core.cards import default_name, load_cards, save_cards, upsert_card
from core.cost import cost_for_route
from core.mills import find_mill, load_mills
from core.storage import DamagedFile
from core.drawing import manual_fits, redistribute
from core.forces import fit_n
from core.route_plan import PARAM_KEYS, plan_route, suggest_n_full
from core.util import InputError, fmt
from ui import cost_panel, dies_panel, heat_panel
from ui.chart import RouteChart
from ui.draft_editor import DraftEditor
from ui.export import save_workbook, table_sheet
from ui.export_dialog import ExportDialog
from ui.popup import notify
from ui.pdf import save_card_pdf, save_operator_pdf
from ui.theme import T, px, sized
from ui.widgets import (Card, FieldError, Page, button, fill_groups, fill_table, label,
                        make_table, panel, tab_box, tab_form)
from ui.anim import AnimatedTabWidget


ROUTE_HEADERS = ["№", "Диаметр на входе, мм", "Диаметр на выходе, мм", "Вытяжка", "Обжатие, %",
                 "Накопл. обжатие*, %", "Накопл. деформация*",
                 "Прочность после прохода, МПа", "Напряжение волочения, МПа", "Запас прочности",
                 "Усилие волочения, кН", "Мощность, кВт", "Скорость проволоки, м/с",
                 "Обороты барабана, об/мин", "Примечание"]


class RoutePage(Page):
    title = "Маршрут"
    hint = "Меняй любое поле — маршрут пересчитывается сразу."

    def build(self):
        self.rows, self.forces = [], []
        main = QHBoxLayout()
        main.setSpacing(18)

        # ---- ввод: четыре вкладки ----
        left = QVBoxLayout()
        left.setSpacing(10)
        p = panel()
        sized(p, "fixed", 440)
        pl = QVBoxLayout(p)
        pl.setContentsMargins(14, 10, 14, 14)
        inputs = AnimatedTabWidget()
        pl.addWidget(inputs)
        left.addWidget(p)

        def adder(grid):
            def field(text, default, key):
                return self.add_field(grid, grid.rowCount(), text, default, key)

            def note(widget):
                grid.addWidget(widget, grid.rowCount(), 0, 1, 2)
            return field, note

        g = tab_form(inputs, "Маршрут")
        field, note = adder(g)
        self.group = QComboBox()
        self.group.setMaxVisibleItems(20)
        fill_groups(self.group, tooltips=True)
        note(self.group)
        self.prep = label("", "note", True)
        note(self.prep)
        self.d0 = field("Исходный диаметр, мм", "5,5", "route/d0")
        self.dk = field("Готовый диаметр, мм", "1,2", "route/dk")
        self.n = field("Число проходов", "14", "route/n")
        self.ratio = field("Перевес обжатия в начале маршрута", "1,15", "route/ratio")
        self.ratio.setToolTip("Во сколько раз вытяжка на первом проходе больше, чем на последнем.")
        note(label("1 — все проходы одинаковые; 1,15 — первый проход обжимает на 15 % сильнее "
                   "последнего. Обычно 1,1–1,2.", "note", True))
        self.auto_btn = button("Подобрать число проходов", primary=True)
        note(self.auto_btn)

        g = tab_form(inputs, "Стан")
        field, note = adder(g)
        r = g.rowCount()
        g.addWidget(QLabel("Стан"), r, 0)
        self.mill = QComboBox()
        self.mill.setEditable(True)
        self.mill.lineEdit().setPlaceholderText("например, 1К89М")
        sized(self.mill, "min", 140)
        g.addWidget(self.mill, r, 1)
        self.mills = []
        self.v = field("Скорость волочильного стана на финише, м/с", "15", "route/v")
        self.drum = field("Диаметр барабана, мм", "", "route/drum")
        self.drum.setPlaceholderText("необязательно")
        self.alpha = field("Полуугол волоки, °", "6", "route/alpha")
        self.mu = field("Коэффициент трения", "0,05", "route/mu")
        self.sq = field("Противонатяжение, МПа", "0", "route/sq")
        note(label("Натяжение проволоки перед волокой (кроме первого прохода этапа). Повышает "
                   "напряжение волочения и снижает запас прочности, но разгружает волоку и "
                   "предыдущий барабан. 0 — без противонатяжения.", "note", True))
        note(label("Нагрев и охлаждение", "section"))
        self.t0 = field("Температура заготовки, °C", "20", "route/t0")
        self.tw = field("Температура охлаждающей воды, °C", "25", "route/tw")
        self.cool = field("Охлаждение на барабане, % перегрева", "50", "route/cool")
        self.vcool = field("…при скорости на финише, м/с", "15", "route/vcool")
        self.dcool = field("…на проволоке диаметром, мм", "1,2", "route/dcool")
        note(label("Доля охлаждения задаётся при опорной скорости; на других скоростях и диаметрах "
                   "программа пересчитывает её (быстрее и толще — остывает хуже). Лучше подобрать по "
                   "замеру пирометром: вкладка «Нагрев и стан». Профили станов — подвкладка «Станы».",
                   "note", True))

        g = tab_form(inputs, "Металл")
        field, note = adder(g)
        self.rho = field("Плотность, г/см³", "", "route/rho")
        self.sig0 = field("Прочность заготовки на разрыв, МПа", "", "route/sig0")
        self.sigf = field("Прочность после обжатия, МПа", "", "route/sigf")
        self.redref = field("…при суммарном обжатии, %", "", "route/redref")
        self.nh = field("Показатель упрочнения n", "", "route/nh")
        self.fit_btn = button("Подобрать n по замеру…")
        self.fit_btn.setToolTip("n — насколько быстро растёт прочность с обжатием. Подбирается по "
                                "одной замеренной прочности при известном обжатии от катанки.")
        note(self.fit_btn)
        self.sig_ann = field("Прочность после отжига, МПа", "", "route/sig_ann")
        self.sig_ann.setPlaceholderText("как у заготовки")
        self.ys = field("Отношение σт/σв", "0,85", "route/ys")
        note(label("Предел текучести к прочности: ≈0,85 для холоднотянутой проволоки, 0,6–0,75 для "
                   "отожжённой катанки, 0,9–0,95 для сильно нагартованной. Уточняется по практике.",
                   "note", True))
        self.cp = field("Теплоёмкость, Дж/(кг·К)", "", "route/cp")
        self.hsrc = label("", "note", True)
        note(self.hsrc)

        g = tab_form(inputs, "Пределы")
        field, note = adder(g)
        self.limit = field("Предел обжатия до отжига, %", "", "route/limit")
        self.lmax = field("Макс. вытяжка за проход", "", "route/lmax")
        self.gmin = field("Минимальный запас прочности", "1,4", "route/gmin")
        self.sig_min = field("Прочность готовой по ГОСТ/ТУ: от, МПа", "", "route/sig_min")
        self.sig_max = field("…до, МПа", "", "route/sig_max")
        for w in (self.sig_min, self.sig_max):
            w.setPlaceholderText("не задано")
        self.src = label("", "note", True)
        note(self.src)

        cost_panel.build_inputs(self, inputs)
        left.addWidget(self.status)
        left.addStretch()
        main.addLayout(left)

        # ---- результаты: сводка и таблица проходов ----
        right = QVBoxLayout()
        right.setSpacing(10)
        self.warn = label("", "error", True)
        right.addWidget(self.warn)
        results = AnimatedTabWidget()
        right.addWidget(results, 1)

        box = tab_box(results, "Сводка")
        self.c = [Card("Общая вытяжка"), Card("Суммарное обжатие", "%"), Card("Отжигов"),
                  Card("Мин. запас прочности"), Card("Мощность на волочение", "кВт"),
                  Card("Производительность", "кг/ч")]
        cg = QGridLayout()
        cg.setSpacing(12)
        for i, c in enumerate(self.c):
            cg.addWidget(c, i // 3, i % 3)
        box.addLayout(cg)
        mode = QHBoxLayout()
        self.mode_label = label("", "muted", True)
        mode.addWidget(self.mode_label, 1)
        self.reset_btn = button("Сбросить к автоматической раскладке")
        mode.addWidget(self.reset_btn)
        box.addLayout(mode)
        self.draft = DraftEditor()
        box.addWidget(self.draft, 3)
        self.chart = RouteChart()
        box.addWidget(self.chart, 2)
        self.summary = label("", "muted", True)
        box.addWidget(self.summary)

        box = tab_box(results, "Проходы")
        self.results_tabs = results
        self.table = make_table(ROUTE_HEADERS)
        self.table.setMinimumHeight(px(300))
        box.addWidget(self.table, 1)
        box.addWidget(label("* от катанки или последнего отжига. Жёлтым — отжиг перед проходом, "
                            "красным — превышена вытяжка или мал запас прочности. Усилие — по "
                            "формуле Зибеля с противонатяжением (если задано); мощность — на "
                            "барабане, за вычетом помощи от противонатяжения следующего прохода.", "note", True))
        cost_panel.build_results(self, results)
        heat_panel.build_results(self, results)
        dies_panel.build_results(self, results)

        bar = QGridLayout()             # 2×2 — не раздвигает окно
        bar.setHorizontalSpacing(8)
        bar.setVerticalSpacing(8)
        self.save_btn = button("Сохранить техкарту", primary=True)
        self.export_btn = button("Экспорт в Excel…")
        self.export_btn.setToolTip("Маршрут, себестоимость, нагрев, волоки — что выгрузить, "
                                   "выбирается в окне экспорта.")
        self.pdf_btn = button("Техкарта в PDF")
        self.op_btn = button("Карта оператора")
        self.op_btn.setToolTip("Маршрутная карта для оператора стана: барабаны, волоки и номера "
                               "фильер из журнала, скорости и графы для замеров.")
        for i, b in enumerate((self.save_btn, self.export_btn, self.pdf_btn, self.op_btn)):
            bar.addWidget(b, i // 2, i % 2)
        bar.setColumnStretch(2, 1)
        right.addLayout(bar)
        main.addLayout(right, 1)
        self.body.addLayout(main, 1)

        self.combos["route/group"] = self.group
        self.group.currentIndexChanged.connect(self.apply_group)
        self.auto_btn.clicked.connect(self.auto_n)
        self.fit_btn.clicked.connect(self.fit_hardening)
        self.export_btn.clicked.connect(self.export)
        self.save_btn.clicked.connect(self.save_card)
        self.pdf_btn.clicked.connect(self.to_pdf)
        self.op_btn.clicked.connect(self.to_operator)
        self.texts["route/mill"] = self.mill.lineEdit()
        self.manual = None                # ручная раскладка из редактора обжатий
        self.export_cols = None           # выбранные в прошлый раз столбцы проходов
        self.draft.dragged.connect(self.on_drag)
        self.draft.unpinned.connect(self.on_unpin)
        self.reset_btn.clicked.connect(self.reset_manual)
        self.mill.currentTextChanged.connect(self.safe_recalc)
        self.reload_mills()
        self.apply_group()

    def apply_group(self, *args):
        name = self.group.currentText()
        g = GROUPS[name]
        h = g["hardening"]
        self.limit.setText(fmt(g["limit"], 0))
        self.lmax.setText(fmt(g["lam_max"], 2))
        self.rho.setText(fmt(g["rho"], 2))
        self.sig0.setText(fmt(h["sig0"], 0))
        self.sigf.setText(fmt(h["sigf"], 0))
        self.redref.setText(fmt(h["red_ref"], 0))
        self.nh.setText(fmt(h["n"], 2))
        self.cp.setText(fmt(g.get("cp", 470), 0))
        self.src.setText("Обоснование пределов: " + g["src"])
        self.prep.setText(" ".join(x for x in (g.get("family", "") + ".", g.get("prep", "")) if x))
        self.hsrc.setText("Прочность: " + h["src"] + f" Лучше подставить прочность своей катанки и проволоки после известного обжатия.")

    def _inputs(self):
        d0 = self.d0.value()
        dk = self.dk.value()
        if dk >= d0:
            raise FieldError(self.dk, "Готовый диаметр должен быть меньше исходного.")
        ratio = self.ratio.value()
        if ratio < 1:
            raise FieldError(self.ratio, "Перевес обжатия — не меньше 1 "
                                         "(1 означает одинаковые проходы).")
        lmax = self.lmax.value()
        if lmax <= 1:
            raise FieldError(self.lmax, "Максимальная вытяжка за проход должна быть больше 1.")
        v = self.v.value()
        drum = self.drum.value(optional=True)
        limit = self.limit.value()
        if limit >= 100:
            raise FieldError(self.limit, "Предел обжатия должен быть меньше 100 %.")
        alpha = self.alpha.value()
        if not 1 <= alpha <= 20:
            raise FieldError(self.alpha, "Полуугол волоки — от 1 до 20° (обычно 4–8°).")
        mu = self.mu.value(allow_zero=True)
        if mu > 0.3:
            raise FieldError(self.mu, "Коэффициент трения при волочении обычно 0,02–0,1.")
        sq = self.sq.value(allow_zero=True)
        gmin = self.gmin.value()
        if gmin <= 1:
            raise FieldError(self.gmin, "Запас прочности должен быть больше 1.")
        sig0 = self.sig0.value()
        sigf = self.sigf.value()
        if sigf <= sig0:
            raise FieldError(self.sigf, "Прочность после обжатия должна быть выше, "
                                        "чем у заготовки.")
        redref = self.redref.value()
        if redref >= 100:
            raise FieldError(self.redref, "Обжатие должно быть меньше 100 %.")
        nh = self.nh.value()
        if nh > 1.5:
            raise FieldError(self.nh, "Показатель упрочнения обычно 0,2–0,8.")
        sig_ann = self.sig_ann.value(optional=True)
        sig_min = self.sig_min.value(optional=True)
        sig_max = self.sig_max.value(optional=True)
        if sig_min is not None and sig_max is not None and sig_min >= sig_max:
            raise FieldError(self.sig_max, "Верхняя граница прочности должна быть больше нижней.")
        ys = self.ys.value()
        if not 0.4 <= ys <= 1:
            raise FieldError(self.ys, "Отношение σт/σв — от 0,4 до 1 (обычно 0,6–0,95).")
        if sq >= 0.5 * ys * sig0:
            raise FieldError(self.sq, "Противонатяжение слишком велико: оно должно быть заметно "
                                      "меньше предела текучести заготовки (обычно до 10–30 % от "
                                      "напряжения волочения).")
        rho = self.rho.value()
        t0 = self.t0.value(allow_zero=True)
        tw = self.tw.value(allow_zero=True)
        cool = self.cool.value(allow_zero=True)
        if cool > 100:
            raise FieldError(self.cool, "Охлаждение — от 0 до 100 % перегрева.")
        cp = self.cp.value()
        vcool = self.vcool.value()
        dcool = self.dcool.value()
        return dict(vcool=vcool, dcool=dcool, d0=d0, dk=dk, ratio=ratio, lmax=lmax, v=v, drum=drum, limit=limit,
                    alpha=alpha, mu=mu, gmin=gmin, sig0=sig0, sigf=sigf, nh=nh, rho=rho,
                    redref=redref, t0=t0, tw=tw, cool=cool, cp=cp, ys=ys, sq=sq,
                    sig_ann=sig_ann, sig_min=sig_min, sig_max=sig_max)

    def recalc(self):
        p = self._inputs()
        n = self.n.value()
        if n != int(n) or n < 1:
            raise FieldError(self.n, "Число проходов — целое число от 1.")
        if n > 60:
            raise FieldError(self.n, "Не больше 60 проходов.")
        n = int(n)
        p["n"] = n
        p["lams"] = self._manual_lams(p)
        mill = self.mill_profile()
        res = plan_route(p, self.group.currentText(), mill)
        total, lams, rows, anneals, forces = (res["total"], res["lams"], res["rows"],
                                              res["anneals"], res["forces"])
        self.rows, self.forces, self.p, self.n_used, self.res = rows, forces, p, n, res
        gpm, gamma_min, power = res["gpm"], res["gamma_min"], res["power"]
        self.c[0].set(fmt(total, 2))
        self.c[1].set(fmt((1 - 1 / total) * 100, 1))
        self.c[2].set(str(anneals))
        self.c[3].set(fmt(gamma_min, 2))
        self.c[4].set(fmt(power, 1))
        self.c[5].set(fmt(gpm * p["v"] * 3.6, 0))
        self.summary.setText(
            f"Средняя вытяжка {fmt(total ** (1 / n))}  ·  первый проход {fmt(lams[0])}, "
            f"последний {fmt(lams[-1])}  ·  истинная деформация {fmt(math.log(total))}  ·  "
            f"масса 1 м готовой {fmt(gpm, 2)} г. Мощность — на самой проволоке, без потерь "
            f"в приводе; производительность — без простоев.")

        warn = res["warnings"]
        self.warn.setText("\n".join(warn))

        data, colors = [], []
        for r, f in zip(rows, forces):
            low = f["gamma"] < p["gmin"]
            note = r["notes"]
            if low:
                note = (note + "; " if note else "") + "мал запас прочности"
            data.append((r["i"], fmt(r["d_in"]), fmt(r["d_out"]), fmt(r["lam"]), fmt(r["red"], 1),
                         fmt(r["red_cum"], 1), fmt(r["eps"]), fmt(f["sig_out"], 0),
                         fmt(f["sig_d"], 0), fmt(f["gamma"], 2), fmt(f["P"] / 1000, 2),
                         fmt(f["power"], 2), fmt(r["v"], 2),
                         fmt(r["rpm"], 0) if r["rpm"] else "—", note))
            bad = r["over"] or low
            colors.append((T["anneal"] if r["anneal"] else (T["warn_soft"] if low else None),
                           T["warn"] if bad else None))
        fill_table(self.table, data, colors)
        self.recalc_cost()
        heat_panel.show(self, res, p, mill)
        dies_panel.show(self, res, p, self.group.currentText())
        self.chart.set_data(p["d0"], [dict(r, over=r["over"] or f["gamma"] < p["gmin"])
                                      for r, f in zip(rows, forces)])
        self.draft.set_data(rows, forces, res["thermal"], p["lmax"], p["gmin"],
                            self.manual["pinned"] if self.manual else set())
        self._update_mode()

    # ---------- ручная раскладка обжатий ----------
    def _manual_lams(self, p):
        """Ручная раскладка годится, пока не изменились диаметры и число проходов."""
        if not self.manual:
            return None
        lams = manual_fits(self.manual["lams"], (p["d0"] / p["dk"]) ** 2, p["n"])
        if lams is None and not getattr(self, "_loading", False):
            self.manual = None            # во время загрузки техкарты поля меняются по одному
        return lams

    def on_drag(self, i, lam):
        if not self.rows:
            return
        p = self.p
        lams = self.manual["lams"] if self.manual else self.res["lams"]
        pinned = self.manual["pinned"] if self.manual else set()
        r = redistribute(lams, i, lam, pinned, (p["d0"] / p["dk"]) ** 2)
        if r is None:
            self.mode_label.setText("Все остальные проходы закреплены — двигать нечего. Двойной "
                                    "щелчок по столбцу снимает закрепление.")
            return
        self.manual = dict(lams=r[0], pinned=r[1])
        self.safe_recalc()

    def on_unpin(self, i):
        if self.manual:
            self.manual["pinned"].discard(i)
            if not self.manual["pinned"]:
                self.manual = None
            self.safe_recalc()

    def reset_manual(self):
        self.manual = None
        self.safe_recalc()

    def _update_mode(self):
        if self.manual:
            k = len(self.manual["pinned"])
            self.mode_label.setText(
                f"Раскладка ручная: закреплено проходов — {k} из {len(self.rows)}. Тяни столбец "
                f"мышью; остальные проходы подстраиваются так, чтобы готовый диаметр не изменился. "
                f"Двойной щелчок по столбцу снимает закрепление.")
        else:
            self.mode_label.setText(
                f"Раскладка автоматическая (перевес обжатия {fmt(self.p['ratio'], 2)}). Потяни "
                f"любой столбец мышью, чтобы распределить обжатия вручную.")
        self.reset_btn.setEnabled(self.manual is not None)

    def reload_mills(self):
        """Обновляет список профилей станов, сохраняя введённое название."""
        try:
            self.mills = load_mills()
        except DamagedFile as e:
            self.mills = []
            QMessageBox.warning(self, "Профили станов", str(e))
        except (OSError, ValueError):
            self.mills = []
        text = self.mill.currentText()
        self.mill.blockSignals(True)
        self.mill.clear()
        self.mill.addItems([m["name"] for m in self.mills])
        self.mill.setEditText(text)
        self.mill.blockSignals(False)

    def mill_profile(self):
        return find_mill(self.mills, self.mill.currentText())

    def on_show(self):
        fill_groups(self.group, tooltips=True)       # могли добавиться свои марки
        self.reload_mills()
        self.safe_recalc()

    def recalc_cost(self):
        """Себестоимость по рассчитанному маршруту. Ошибка в ценах не ломает сам маршрут."""
        cost_panel.enable_fields(self)
        self.cost_inputs, self.res["cost"] = None, None
        if not self.cost_on.isChecked():
            cost_panel.clear(self, "Расчёт себестоимости выключен на вкладке «Экономика».")
            return
        try:
            c = cost_panel.read_inputs(self)
            r = cost_for_route(c, self.p, self.res)
        except FieldError as e:
            e.field.set_error(True, str(e))
            cost_panel.clear(self, "Себестоимость не рассчитана: " + str(e))
            return
        except InputError as e:
            cost_panel.clear(self, "Себестоимость не рассчитана: " + str(e))
            return
        self.cost_inputs, self.res["cost"] = c, r
        cost_panel.show(self, r, c)

    def clear_results(self):
        self.rows, self.forces = [], []
        cost_panel.clear(self)
        heat_panel.clear(self)
        dies_panel.clear(self)
        for c in self.c:
            c.set("—")
        self.summary.setText("")
        self.warn.setText("")
        self.table.setRowCount(0)
        self.chart.set_data(None, [])
        self.draft.set_data([], [], [], 1.3, 1.4, set())

    def auto_n(self):
        for f in self.fields:
            f.set_error(False)
        try:
            p = self._inputs()
        except FieldError as e:
            e.field.set_error(True, str(e))
            self.status.setText(str(e))
            return
        n = suggest_n_full(p, self.group.currentText(), self.mill_profile())
        if n is not None:
            self.n.setText(str(n))
            return
        self.status.setText("Не удалось подобрать маршрут с допустимыми вытяжкой и запасом "
                            "прочности. Уменьши перевес обжатия, угол волоки или трение.")

    def fit_hardening(self):
        """Показатель упрочнения по замеру: прочность проволоки после известного обжатия."""
        try:
            sig0, sigf, redref = self.sig0.value(), self.sigf.value(), self.redref.value()
        except FieldError as e:
            QMessageBox.warning(self, "Показатель упрочнения", str(e))
            return
        red, ok = QInputDialog.getDouble(self, "Замер прочности", "Суммарное обжатие от катанки "
                                         "(или от отжига), %:", 60.0, 1.0, 99.0, 1)
        if not ok:
            return
        sig, ok = QInputDialog.getDouble(self, "Замер прочности", f"Прочность проволоки после "
                                         f"обжатия {fmt(red, 1)} %, МПа:", sigf, 1.0, 5000.0, 0)
        if not ok:
            return
        try:
            n = fit_n(sig0, sigf, redref, red, sig)
        except InputError as e:
            QMessageBox.warning(self, "Показатель упрочнения", str(e))
            return
        self.nh.setText(fmt(n, 2))
        notify(self, f"Показатель упрочнения n = {fmt(n, 2)}", "ok",
               detail=f"Кривая проходит через {fmt(sig0, 0)} МПа у катанки, {fmt(sigf, 0)} МПа "
                      f"при {fmt(redref, 0)} % и замер {fmt(sig, 0)} МПа при {fmt(red, 1)} %.")

    def current_params(self):
        """Параметры текущего маршрута или None, если в полях ошибка."""
        if not self.rows:
            notify(self, "Сначала получи корректный маршрут", "warn")
            return None
        return {k: self.p[k] for k in PARAM_KEYS}

    def save_card(self):
        p = self.current_params()
        if p is None:
            return
        group, mill = self.group.currentText(), self.mill.currentText().strip()
        name, ok = QInputDialog.getText(self, "Сохранить техкарту", "Название техкарты:",
                                        QLineEdit.EchoMode.Normal, default_name(group, p, mill))
        name = name.strip()
        if not ok or not name:
            return
        try:
            cards = load_cards()
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Техкарты", f"Не удалось прочитать файл техкарт:\n{e}")
            return
        if any(c["name"] == name for c in cards) and QMessageBox.question(
                self, "Техкарта существует", f"Техкарта «{name}» уже есть. Заменить её?") \
                != QMessageBox.StandardButton.Yes:
            return
        upsert_card(cards, name, mill, group, p, cost=self.cost_inputs)
        try:
            save_cards(cards)
        except OSError as e:
            QMessageBox.warning(self, "Техкарты", f"Не удалось сохранить:\n{e}")
            return
        extra = "" if self.cost_inputs else (" Себестоимость не сохранена: она выключена или в "
                                             "ценах есть ошибка.")
        notify(self, f"Техкарта «{name}» сохранена", "ok",
               detail="Открыть, сравнить и распечатать — в разделе «Техкарты»." + extra)

    def to_pdf(self):
        p = self.current_params()
        if p is None:
            return
        group, mill = self.group.currentText(), self.mill.currentText().strip()
        save_card_pdf(self, default_name(group, p, mill), mill, group, self.p, self.res)

    def to_operator(self):
        p = self.current_params()
        if p is None:
            return
        group, mill = self.group.currentText(), self.mill.currentText().strip()
        save_operator_pdf(self, default_name(group, p, mill), mill, group, self.p, self.res,
                          self.die_plan)

    def load_card(self, card):
        """Подставляет параметры техкарты в поля (группа первой: она перезаписывает пределы)."""
        if self.group.findText(card["group"]) >= 0:
            self.group.setCurrentText(card["group"])
        cost_panel.load(self, card.get("cost"))
        self.mill.setEditText(card.get("mill", ""))
        lams = card["params"].get("lams")
        self.manual = dict(lams=list(lams), pinned=set()) if lams else None
        self._loading = True
        names = {"d0": self.d0, "dk": self.dk, "n": self.n, "ratio": self.ratio, "v": self.v,
                 "drum": self.drum, "alpha": self.alpha, "mu": self.mu, "limit": self.limit,
                 "lmax": self.lmax, "gmin": self.gmin, "rho": self.rho, "sig0": self.sig0,
                 "sigf": self.sigf, "nh": self.nh, "redref": self.redref, "t0": self.t0,
                 "tw": self.tw, "cool": self.cool, "cp": self.cp, "vcool": self.vcool,
                 "dcool": self.dcool, "ys": self.ys, "sq": self.sq,
                 "sig_ann": self.sig_ann, "sig_min": self.sig_min, "sig_max": self.sig_max}
        for key, field in names.items():
            if key not in card["params"]:       # старые техкарты: оставляем текущее значение
                continue
            val = card["params"].get(key)
            field.setText("" if val is None else fmt(val, 6).rstrip("0").rstrip(","))
        self._loading = False
        self.safe_recalc()

    def export(self, preset=None):
        """Экспорт в Excel: окно выбора разделов и столбцов, затем книга — лист на раздел."""
        if not self.rows:
            notify(self, "Сначала получи корректный маршрут.", "warn")
            return
        cost_ok = cost_panel.has_cost(self)
        on = preset or {"params", "passes", "cost", "cost_in"}
        n_items = len(self.res["cost"]["items"]) + len(self.res["cost"]["full_items"]) \
            if cost_ok else 0
        n_pick = n_items - len(self.cost_skip) if cost_ok else 0
        sections = [
            ("params", "Параметры маршрута", "Группа, диаметры, скорость, металл и пределы.",
             "params" in on),
            ("passes", "Проходы", "Таблица проходов — отметь нужные столбцы.", "passes" in on),
            ("cost", "Себестоимость: статьи",
             f"Отмечено галочками в таблице «Себестоимость»: {n_pick} из {n_items}."
             if cost_ok else "Себестоимость не рассчитана (вкладка «Экономика»).",
             "cost" in on, cost_ok),
            ("cost_in", "Себестоимость: цены и нормы", "Исходные данные вкладки «Экономика».",
             "cost_in" in on, cost_ok),
            ("heat", "Нагрев и стан", "Температуры, барабаны, загрузка привода, скольжение.",
             "heat" in on),
            ("dies", "Волоки", "Углы, поясок, материал, фильеры из журнала.",
             "dies" in on, bool(self.die_plan)),
        ]
        dlg = ExportDialog(self, sections, ROUTE_HEADERS, "passes", self.export_cols)
        if dlg.exec() != ExportDialog.DialogCode.Accepted:
            return
        chosen, cols = dlg.chosen(), dlg.chosen_columns()
        self.export_cols = cols
        sheets = []
        p = self.p
        info = [("Группа сталей", self.group.currentText()), ("Исходный диаметр, мм", p["d0"]),
                ("Готовый диаметр, мм", p["dk"]), ("Проходов", self.n_used),
                ("Перевес обжатия в начале маршрута", p["ratio"]),
                ("Предел обжатия до отжига, %", p["limit"]), ("Макс. вытяжка за проход", p["lmax"]),
                ("Скорость волочильного стана на финише, м/с", p["v"]), ("Полуугол волоки, °", p["alpha"]),
                ("Коэффициент трения", p["mu"]), ("Мин. запас прочности", p["gmin"]),
                ("Прочность заготовки на разрыв, МПа", p["sig0"]), ("Прочность после обжатия, МПа", p["sigf"]),
                ("…при суммарном обжатии, %", p["redref"]),
                ("Показатель упрочнения n", p["nh"]), ("Отношение σт/σв", p["ys"]),
                ("Противонатяжение, МПа", p["sq"]),
                ("Прочность после отжига, МПа", p["sig_ann"] if p["sig_ann"] else "как у заготовки"),
                ("Прочность готовой по ГОСТ/ТУ, МПа",
                 " – ".join(fmt(x, 0) if x else "—" for x in (p["sig_min"], p["sig_max"])))]
        if "params" in chosen:
            sheets.append(("Параметры маршрута", [], ["Параметр", "Значение"],
                           [list(x) for x in info], None))
        if "passes" in chosen:
            idx = [i for i, h in enumerate(ROUTE_HEADERS) if h in cols] or \
                list(range(len(ROUTE_HEADERS)))
            rows, fills = [], []
            for r, f in zip(self.rows, self.forces):
                full = [r["i"], round(r["d_in"], 4), round(r["d_out"], 4), round(r["lam"], 4),
                        round(r["red"], 2), round(r["red_cum"], 2), round(r["eps"], 4),
                        round(f["sig_out"]), round(f["sig_d"]), round(f["gamma"], 3),
                        round(f["P"] / 1000, 3), round(f["power"], 3), round(r["v"], 3),
                        round(r["rpm"], 1) if r["rpm"] else "", r["notes"]]
                rows.append([full[i] for i in idx])
                fills.append("yellow" if r["anneal"] else
                             ("red" if f["gamma"] < p["gmin"] else None))
            sheets.append(("Проходы", [], [ROUTE_HEADERS[i] for i in idx], rows, fills))
        if cost_ok and chosen & {"cost", "cost_in"}:
            sheets += cost_panel.cost_sheets(self, "cost" in chosen, "cost_in" in chosen)
        if "heat" in chosen:
            sheets.append(table_sheet("Нагрев и стан", self.heat_table))
        if "dies" in chosen:
            sheets.append(table_sheet("Волоки", self.die_table))
        path = save_workbook(self, f"маршрут {default_name(self.group.currentText(), p, '')}",
                             sheets)
        if path:
            notify(self, f"Сохранено листов: {len(sheets)}", "ok", detail=path)
