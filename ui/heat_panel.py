"""Вкладка «Нагрев и стан» в результатах маршрута: температура по проходам, загрузка привода,
скольжение, подбор охлаждения по замеру пирометром."""
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.thermal import T_AGING, T_WINDING, calibrate_cooling
from core.util import fmt
from ui.theme import T, px
from ui.widgets import Card, NumField, button, fill_table, label, make_table

HEAD = ["№", "Температура на входе, °C", "Нагрев в волоке, °C", "Температура на выходе, °C",
        "Температура после барабана, °C",
        "Барабан", "Мощность, кВт", "Загрузка привода, %", "Скольжение, %", "Примечание"]


def build_results(page, tabs):
    host = QWidget()
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 12, 0, 0)
    lay.setSpacing(10)
    page.heat_cards = [Card("Макс. температура проволоки", "°C"), Card("Температура на намотке", "°C"),
                       Card("Макс. загрузка привода", "%"), Card("Проходов / барабанов")]
    cg = QGridLayout()
    cg.setSpacing(12)
    for i, c in enumerate(page.heat_cards):
        cg.addWidget(c, 0, i)
    lay.addLayout(cg)
    page.heat_info = label("", "muted", True)
    lay.addWidget(page.heat_info)

    cal = QHBoxLayout()
    cal.addWidget(QLabel("Замер пирометром на барабане прохода №"))
    page.cal_pass = NumField("Номер прохода")
    page.cal_temp = NumField("Температура")
    page.cal_temp.setPlaceholderText("°C")
    cal.addWidget(page.cal_pass)
    cal.addWidget(QLabel("температура, °C"))
    cal.addWidget(page.cal_temp)
    b = button("Подобрать охлаждение")
    cal.addWidget(b)
    cal.addStretch()
    lay.addLayout(cal)
    page.cal_msg = label("", "muted", True)
    lay.addWidget(page.cal_msg)
    b.clicked.connect(lambda: calibrate(page))

    page.heat_table = make_table(HEAD)
    page.heat_table.setMinimumHeight(px(260))
    lay.addWidget(page.heat_table, 1)
    lay.addWidget(label(
        f"Нагрев в волоке считается по работе волочения (90 % тепла остаётся в проволоке); на "
        f"барабане снимается заданная доля перегрева над температурой воды. Выше {fmt(T_AGING, 0)} °C — условия для статического деформационного "
        f"старения (Радионова и др., Metals, 2022). Это средняя по сечению температура: поверхность "
        f"в волоке нагревается сильнее. Жёлтым — проход на грани, красным — перегрев или перегрузка.",
        "note", True))
    tabs.addTab(host, "Нагрев и стан")


def show(page, res, p, mill):
    th, mr = res["thermal"], res.get("mill")
    page.heat_cards[0].set(fmt(res["t_max"], 0))
    page.heat_cards[1].set(fmt(res["t_wind"], 0))
    page.heat_cards[2].set(fmt(mr["max_load"], 0) if mr and mr.get("max_load") is not None else "—")
    page.heat_cards[3].set(f"{res['n']} / {mill['drums']}" if mill else f"{res['n']} / —")
    page.heat_info.setText(
        (f"Стан «{mill['name']}»: {mill['drive'].lower()}, барабаны {fmt(mill['drum_d'], 0)} мм. "
         if mill else "Стан не выбран из профилей — проверка кинематики и привода не выполняется. ")
        + f"Охлаждение {fmt(p['cool'], 0)} % перегрева при {fmt(p.get('vcool') or p['v'], 1)} м/с "
          f"на {fmt(p.get('dcool') or p['dk'], 2)} мм "
          f"(на других скоростях пересчитывается), вода {fmt(p['tw'], 0)} °C.")
    rows, colors = [], []
    per = mr["per"] if mr else [None] * len(th)
    for r, f, t, m in zip(res["rows"], res["forces"], th, per):
        notes = []
        if t["t_out"] > T_AGING:
            notes.append("перегрев")
        if m and m["load"] is not None and m["load"] > 100:
            notes.append("перегрузка привода")
        if m and m["slip"] is not None and m["slip"] < -0.5:
            notes.append("проволока обгоняет барабан")
        rows.append((r["i"], fmt(t["t_in"], 0), fmt(t["dT"], 0), fmt(t["t_out"], 0),
                     fmt(t["t_drum"], 0), m["drum"] if m else "—", fmt(f["power"], 2),
                     fmt(m["load"], 0) if m and m["load"] is not None else "—",
                     fmt(m["slip"], 1) if m and m["slip"] is not None else "—", "; ".join(notes)))
        if notes:
            colors.append((T["warn_soft"], T["warn"]))
        elif t["t_out"] > 0.85 * T_AGING or (m and m["load"] is not None and m["load"] > 85):
            colors.append((T["anneal"], None))
        else:
            colors.append(None)
    if res["t_wind"] > T_WINDING and rows:
        colors[-1] = colors[-1] or (T["anneal"], None)
    fill_table(page.heat_table, rows, colors)


def clear(page):
    for c in page.heat_cards:
        c.set("—")
    page.heat_info.setText("")
    page.heat_table.setRowCount(0)


def calibrate(page):
    if not page.rows:
        page.cal_msg.setText("Сначала получи корректный маршрут.")
        return
    try:
        k = page.cal_pass.value()
        t = page.cal_temp.value(allow_zero=True)
    except Exception as e:      # FieldError — понятный текст
        page.cal_msg.setText(str(e))
        return
    if k != int(k) or not 1 <= k <= len(page.rows):
        page.cal_msg.setText(f"Номер прохода — от 1 до {len(page.rows)}.")
        return
    p = page.p
    # замер сделан на текущей скорости — она и становится опорной
    cool = calibrate_cooling(page.rows, page.forces, p["rho"], p["cp"], p["t0"], p["tw"],
                             int(k), t, v_ref=p["v"], d_ref=p["dk"])
    if cool is None:
        page.cal_msg.setText("Такой температуры не получить ни при каком охлаждении: проверь "
                             "замер, температуру воды и трение.")
        return
    page.vcool.setText(fmt(p["v"], 6).rstrip("0").rstrip(","))
    page.dcool.setText(fmt(p["dk"], 6).rstrip("0").rstrip(","))
    page.cool.setText(fmt(cool, 1))
    page.cal_msg.setText(f"Охлаждение подобрано: {fmt(cool, 1)} % перегрева при скорости "
                         f"{fmt(p['v'], 1)} м/с. Значения записаны на вкладку «Стан».")
