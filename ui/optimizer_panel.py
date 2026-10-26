"""Вкладка «Оптимизатор» в «Аналитике»: самый дешёвый допустимый маршрут под свои условия."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QVBoxLayout, QWidget)

from core.data import GROUPS
from core.optimize import DEFAULT_LIMITS, optimize
from core.util import InputError, fmt, num
from ui.theme import px
from ui.widgets import FieldError, NumField, button, fill_table, label, make_table, panel

HEAD = ["Диаметр, мм", "Проходов", "Перевес обжатия", "Отжигов",
        "Скорость стана на финише, м/с", "Вытяжка первого / последнего прохода",
        "Мин. запас прочности", "Температура макс. / на намотке, °C", "Производительность, кг/ч",
        "Передел, руб/т", "Что ограничило"]


def build(page, tabs, index):
    host = QWidget()
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 12, 0, 0)
    lay.setSpacing(10)
    lay.addWidget(label("Перебирает число проходов и перевес обжатия, для каждого варианта находит "
                        "наибольшую допустимую скорость каждого этапа и выбирает самый дешёвый маршрут. "
                        "Цены, охлаждение и трение берутся из «Маршрута» (вкладки «Стан» и «Экономика»).",
                        "muted", True))
    p = panel()
    g = QGridLayout(p)
    g.setContentsMargins(16, 12, 16, 12)
    g.setHorizontalSpacing(12)
    page.o_group = QComboBox()
    family = None
    for name, grp in GROUPS.items():
        if grp.get("family") != family:
            if family is not None:
                page.o_group.insertSeparator(page.o_group.count())
            family = grp.get("family")
        page.o_group.addItem(name)
    g.addWidget(QLabel("Группа сталей"), 0, 0)
    g.addWidget(page.o_group, 0, 1, 1, 3)
    page.o_rho = NumField("Плотность")
    page.o_diams = QLineEdit("0,8; 1,0; 1,2; 1,6; 2,0; 2,5; 3,0; 4,0")
    page.o_d0 = NumField("Исходный диаметр", "5,5")
    page.o_vmin = NumField("Мин. скорость", fmt(DEFAULT_LIMITS["v_min"], 0))
    page.o_vmax = NumField("Макс. скорость", fmt(DEFAULT_LIMITS["v_max"], 0))
    page.o_gmin = NumField("Мин. запас прочности", "1,4")
    page.o_tmax = NumField("Макс. температура", fmt(DEFAULT_LIMITS["t_max"], 0))
    page.o_twind = NumField("Температура намотки", fmt(DEFAULT_LIMITS["t_wind"], 0))
    page.o_lmin = NumField("Мин. вытяжка за проход", "1,10")
    grid = [("Плотность, г/см³", page.o_rho), ("Исходный диаметр, мм", page.o_d0),
            ("Готовые диаметры, мм", page.o_diams), ("Мин. скорость стана, м/с", page.o_vmin),
            ("Макс. скорость стана, м/с", page.o_vmax),
            ("Минимальный запас прочности", page.o_gmin), ("Макс. температура проволоки, °C", page.o_tmax),
            ("Макс. температура на намотке, °C", page.o_twind),
            ("Мин. вытяжка за проход", page.o_lmin)]
    for i, (text, w) in enumerate(grid):
        g.addWidget(QLabel(text), 1 + i // 2, (i % 2) * 2)
        g.addWidget(w, 1 + i // 2, (i % 2) * 2 + 1)
    page.o_from_route = QCheckBox("Цены, охлаждение, трение, стан и требование к прочности — "
                                  "из «Маршрута»")
    page.o_from_route.setChecked(True)
    g.addWidget(page.o_from_route, 6, 0, 1, 4)
    bar = QHBoxLayout()
    run = button("Рассчитать", primary=True)
    open_btn = button("Открыть выбранный в маршруте")
    bar.addWidget(run)
    bar.addWidget(open_btn)
    bar.addStretch()
    g.addLayout(bar, 7, 0, 1, 4)
    lay.addWidget(p)
    page.o_msg = label("", "muted", True)
    lay.addWidget(page.o_msg)
    page.o_table = make_table(HEAD)
    page.o_table.setMinimumHeight(px(260))
    lay.addWidget(page.o_table, 1)
    tabs.insertTab(index, host, "Оптимизатор")
    page.o_results = []
    page.o_group.currentIndexChanged.connect(lambda *_: _fill_rho(page))
    run.clicked.connect(lambda: run_opt(page))
    open_btn.clicked.connect(lambda: open_in_route(page))
    _fill_rho(page)


def _fill_rho(page):
    page.o_rho.setText(fmt(GROUPS[page.o_group.currentText()]["rho"], 2))


def _route_conditions(page):
    """Цены, тепловые условия, трение, профиль стана и параметры металла из «Маршрута»
    (или значения по умолчанию без стана)."""
    if not page.o_from_route.isChecked():
        return None, None, 6.0, 0.05, None, None
    from ui import cost_panel
    from ui.pages.route import RoutePage
    route = page.win.page_of(RoutePage)
    p = route._inputs()                                   # FieldError — понятный текст
    thermal = {k: p[k] for k in ("t0", "tw", "cool", "vcool", "dcool")}
    cost = cost_panel.read_inputs(route) if route.cost_on.isChecked() else None
    if cost:
        cost.update(copper=False, full=False)
    overrides = {k: p[k] for k in ("ys", "sq", "sig_ann", "sig_min", "sig_max")}
    return cost, thermal, p["alpha"], p["mu"], route.mill_profile(), overrides


def run_opt(page):
    try:
        for f in (page.o_rho, page.o_d0, page.o_vmin, page.o_vmax, page.o_gmin, page.o_tmax,
                  page.o_twind, page.o_lmin):
            f.set_error(False)
        group = page.o_group.currentText()
        rho, d0 = page.o_rho.value(), page.o_d0.value()
        try:
            diams = [num(x) for x in page.o_diams.text().replace(" ", "").split(";") if x]
        except ValueError:
            raise InputError("Готовые диаметры — числа через точку с запятой.")
        if not diams or any(not 0 < d < d0 for d in diams):
            raise InputError("Готовые диаметры должны быть меньше исходного.")
        limits = dict(v_min=page.o_vmin.value(), v_max=page.o_vmax.value(), gmin=page.o_gmin.value(),
                      t_max=page.o_tmax.value(), t_wind=page.o_twind.value(),
                      lam_min=page.o_lmin.value())
        if limits["v_min"] >= limits["v_max"]:
            raise FieldError(page.o_vmin, "Минимальная скорость должна быть меньше максимальной.")
        if limits["lam_min"] <= 1:
            raise FieldError(page.o_lmin, "Минимальная вытяжка должна быть больше 1.")
        cost, thermal, alpha, mu, mill, overrides = _route_conditions(page)
    except FieldError as e:
        e.field.set_error(True, str(e))
        page.o_msg.setText(str(e))
        return
    except InputError as e:
        page.o_msg.setText("Проверь данные: " + str(e))
        return
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    page.o_results, rows = [], []
    try:
        for d in diams:
            page.o_msg.setText(f"Считаю {fmt(d, 2)} мм…")
            QApplication.processEvents()
            b = optimize(group, rho, d, d0=d0, cost=cost, thermal=thermal, limits=limits,
                         alpha=alpha, mu=mu, overrides=overrides, mill=mill)
            page.o_results.append((group, b))
            if b is None:
                rows.append([fmt(d, 2)] + ["—"] * 9 + ["нет допустимого маршрута"])
                continue
            vs = b.get("v_stages") or [b["v"]]
            rows.append([fmt(d, 2), b["n"], fmt(b["ratio"], 2), b["anneals"],
                         " / ".join(fmt(x, 1) for x in vs),
                         f"{fmt(b['lam1'], 2)} / {fmt(b['lamn'], 2)}", fmt(b["gamma_min"], 2),
                         f"{fmt(b['t_max'], 0)} / {fmt(b['t_wind'], 0)}", fmt(b["q_t"], 0),
                         fmt(b["conversion"], 0), b["limit_by"]])
    finally:
        QApplication.restoreOverrideCursor()
    fill_table(page.o_table, rows)
    page.o_msg.setText("Готово. Скорости этапов между отжигами указаны через «/». В маршрут "
                       "откроется скорость последнего этапа. "
                       + (f"Учтён стан «{mill['name']}»: барабаны, паспортная скорость и мощность "
                          f"двигателей." if mill else "Стан не выбран — барабаны и мощность "
                          "двигателей не проверялись (выбери стан во вкладке «Стан» маршрута)."))


def open_in_route(page):
    rows = page.o_table.selectionModel().selectedRows()
    if not rows:
        page.o_msg.setText("Выдели строку в таблице.")
        return
    group, b = page.o_results[rows[0].row()]
    if b is None:
        page.o_msg.setText("Для этого диаметра допустимого маршрута нет.")
        return
    from ui.pages.route import RoutePage
    route = page.win.page_of(RoutePage)
    params = {k: v for k, v in b["params"].items() if k != "v_stages"}
    route.load_card(dict(group=group, mill=route.mill.currentText(), params=params))
    page.win.go_to(route)
