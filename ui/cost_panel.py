"""Себестоимость передела внутри «Маршрута»: ввод («гармошка» групп) и результаты.
Продукт, число проходов, отжиги и мощность берутся из рассчитанного маршрута."""
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QMessageBox,
                               QToolBox, QVBoxLayout, QWidget)

from core.cost import (COPPER_KEYS, COST_NUM_KEYS, ENERGY_BY_ROUTE, ENERGY_METHODS, FORMULAS,
                       FULL_KEYS)
from core.util import fmt
from ui.theme import px
from ui.widgets import Card, FieldError, button, fill_table, label, make_table

ZERO_OK = {"idle_pct", "tax_pct", "overhead_pct", "die_price", "lube_kg_t", "lube_price",
           "other_t", "anneal_cost_t", "repair_pct", "scrap_price", "pack_price", "cu_loss_pct",
           "mill_price"}
PERCENT_100 = {"ku_pct", "yield_pct", "load_pct", "eta_pct", "idle_pct"}

# (группа, [(ключ, подпись, по умолчанию)])
GROUPS = [
    ("Режим работы", [("shifts", "Смен в сутки", "2"), ("shift_h", "Часов в смене", "12"),
                      ("days", "Рабочих дней в году", "250"),
                      ("ku_pct", "Коэффициент использования стана, %", "75"),
                      ("yield_pct", "Выход годного, %", "97")]),
    ("Электроэнергия", [("p_inst", "Установленная мощность (стан, размотчик, намотчик), кВт",
                         "632"),
                        ("load_pct", "Коэффициент загрузки по мощности, %", "60"),
                        ("eta_pct", "КПД привода, %", "85"),
                        ("idle_pct", "Холостой ход, % от установленной", "10"),
                        ("tariff", "Тариф, руб/кВт·ч", "8")]),
    ("Персонал", [("workers", "Рабочих на стане в смену", "2"),
                  ("rate", "Часовая ставка, руб/ч", "450"),
                  ("tax_pct", "Страховые взносы, %", "30,2"),
                  ("overhead_pct", "Цеховые накладные, % от зарплаты", "100")]),
    ("Инструмент и материалы", [("die_price", "Средняя цена фильеры, руб", "7000"),
                                ("die_life_t", "Стойкость одной фильеры с переточками, т", "35"),
                                ("lube_kg_t", "Расход смазки, кг/т", "1,5"),
                                ("lube_price", "Цена смазки, руб/кг", "250"),
                                ("anneal_cost_t", "Стоимость одного отжига, руб/т", "3000"),
                                ("other_t", "Прочие материалы, руб/т", "300")]),
    ("Амортизация и ремонт стана", [("mill_price", "Балансовая стоимость стана, руб", "45000000"),
                                    ("mill_years", "Срок полезного использования, лет", "10"),
                                    ("repair_pct", "Ремонт и обслуживание, % в год", "4")]),
    ("Омеднение", [("cu_um", "Толщина слоя, мкм", "0,3"), ("cu_loss_pct", "Потери меди, %", "10"),
                   ("cu_price", "Цена меди (анодов), руб/кг", "1100")]),
    ("Полная себестоимость", [("rod_price", "Цена катанки, руб/т", "85000"),
                              ("scrap_price", "Цена отходов (лома), руб/т", "25000"),
                              ("pack_price", "Цена упаковки на единицу, руб", "180"),
                              ("pack_kg", "Масса нетто в упаковке, кг", "15")]),
]


def build_inputs(page, tabs):
    """Вкладка «Экономика» в панели ввода маршрута."""
    host = QWidget()
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 10, 0, 0)
    page.cost_on = QCheckBox("Считать себестоимость передела")
    page.cost_on.setChecked(True)
    lay.addWidget(page.cost_on)
    lay.addWidget(label("Цены и нормы — пример, подставь свои. Продукт, проходы, отжиги и "
                        "мощность берутся из маршрута.", "note", True))
    box = QToolBox()
    lay.addWidget(box, 1)
    page.cost_box = box
    page.cost_f = {}
    page.cost_method = QComboBox()
    page.cost_method.addItems(ENERGY_METHODS)
    page.cost_copper = QCheckBox("Учитывать медь на омеднение")
    page.cost_full = QCheckBox("Добавить катанку, отходы и упаковку")
    for title, fields in GROUPS:
        w = QWidget()
        g = QGridLayout(w)
        g.setContentsMargins(4, 6, 4, 6)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(6)
        extra = {"Электроэнергия": page.cost_method, "Омеднение": page.cost_copper,
                 "Полная себестоимость": page.cost_full}.get(title)
        if extra is not None:
            g.addWidget(extra, 0, 0, 1, 2)
        for key, text, default in fields:
            page.cost_f[key] = page.add_field(g, g.rowCount(), text, default, f"cost/{key}")
        if title == "Инструмент и материалы":
            b_life = button("Стойкость — из журнала фильер")
            b_life.setToolTip("Средняя наработка снятых с работы фильер по журналу.")
            b_life.clicked.connect(lambda: _life_from_journal(page))
            g.addWidget(b_life, g.rowCount(), 0, 1, 2)
            g.addWidget(label("Стойкость — тонн через одну волоку. Если на заводе считают норму "
                              "расхода на весь маршрут (например, 0,32 волоки на тонну), то "
                              "стойкость ≈ число проходов / норма: при 11 проходах ≈ 34 т.",
                              "note", True), g.rowCount(), 0, 1, 2)
        if title == "Режим работы":
            g.addWidget(label("Kи — доля смены, когда стан реально тянет: без обрывов, заправки, "
                              "смены катушек и переналадок.", "note", True), g.rowCount(), 0, 1, 2)
        g.setRowStretch(g.rowCount(), 1)
        box.addItem(w, title)
    tabs.addTab(host, "Экономика")
    page.combos["cost/method"] = page.cost_method
    page.checks["cost/copper"] = page.cost_copper
    page.checks["cost/full"] = page.cost_full
    page.checks["cost/on"] = page.cost_on
    for w in (page.cost_copper, page.cost_full, page.cost_on):
        w.toggled.connect(page.safe_recalc)
    page.cost_method.currentIndexChanged.connect(page.safe_recalc)


def _life_from_journal(page):
    from core.dies import actual_life, load_journal
    life = actual_life(load_journal())
    if not life:
        QMessageBox.information(page, "Стойкость", "В журнале нет снятых фильер с записанной "
                                                   "наработкой — оставлена норма.")
        return
    page.cost_f["die_life_t"].setText(fmt(life[0], 1))
    QMessageBox.information(page, "Стойкость", f"Взята фактическая стойкость {fmt(life[0], 1)} т "
                                               f"(среднее по {life[1]} снятым фильерам).")
    page.safe_recalc()


def build_results(page, tabs):
    """Вкладка «Себестоимость» в результатах маршрута."""
    host = QWidget()
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 12, 0, 0)
    lay.setSpacing(10)
    page.cost_cards = [Card("Передел", "руб/т"), Card("Передел", "руб/кг"),
                       Card("Полная себестоимость", "руб/т"), Card("Электроэнергия", "кВт·ч/т"),
                       Card("Факт. производительность", "кг/ч"), Card("Выпуск", "т/мес")]
    cg = QGridLayout()
    cg.setSpacing(12)
    for i, c in enumerate(page.cost_cards):
        cg.addWidget(c, i // 3, i % 3)
    lay.addLayout(cg)
    page.cost_msg = label("", "error", True)
    lay.addWidget(page.cost_msg)
    page.cost_table = make_table(["Статья", "руб/т годной", "Доля, %"])
    page.cost_table.setMinimumHeight(px(260))
    lay.addWidget(page.cost_table, 1)
    page.cost_info = label("", "muted", True)
    lay.addWidget(page.cost_info)
    bar = QHBoxLayout()
    how = button("Как считается")
    bar.addWidget(how)
    bar.addStretch()
    lay.addLayout(bar)
    how.clicked.connect(lambda: QMessageBox.information(page, "Как считается себестоимость",
                                                        "\n\n".join(FORMULAS)))
    tabs.addTab(host, "Себестоимость")


def enable_fields(page):
    on = page.cost_on.isChecked()
    page.cost_box.setEnabled(on)
    by_route = page.cost_method.currentText() == ENERGY_BY_ROUTE
    page.cost_f["load_pct"].setEnabled(not by_route)
    page.cost_f["eta_pct"].setEnabled(by_route)
    for k in COPPER_KEYS:
        page.cost_f[k].setEnabled(page.cost_copper.isChecked())
    for k in FULL_KEYS:
        page.cost_f[k].setEnabled(page.cost_full.isChecked())


def read_inputs(page):
    """Исходные данные себестоимости из полей (то, что сохраняется в техкарте)."""
    c = dict(energy_method=page.cost_method.currentText(), copper=page.cost_copper.isChecked(),
             full=page.cost_full.isChecked())
    keys = list(COST_NUM_KEYS)
    if c["copper"]:
        keys += COPPER_KEYS
    if c["full"]:
        keys += FULL_KEYS
    for key in keys:
        field = page.cost_f[key]
        v = field.value(allow_zero=key in ZERO_OK)
        if key in PERCENT_100 and v > 100:
            raise FieldError(field, f"«{field.name}» — не больше 100 %.")
        c[key] = v
    if c["shifts"] != int(c["shifts"]):
        raise FieldError(page.cost_f["shifts"], "Число смен — целое число.")
    return c


def show(page, r, c):
    page.cost_msg.setText("\n".join(r["warnings"]))
    page.cost_cards[0].set(fmt(r["conversion"], 0))
    page.cost_cards[1].set(fmt(r["conversion"] / 1000, 2))
    page.cost_cards[2].set(fmt(r["full"], 0) if c["full"] else "—")
    page.cost_cards[3].set(fmt(r["kwh_t"], 0))
    page.cost_cards[4].set(fmt(r["q_f"], 0))
    page.cost_cards[5].set(fmt(r["out_month_t"], 0))
    page.cost_info.setText(
        f"Теоретическая производительность {fmt(r['q_t'], 0)} кг/ч; рабочая мощность "
        f"{fmt(r['p_work'], 0)} кВт из {fmt(c['p_inst'], 0)} по паспорту; годовой выпуск "
        f"{fmt(r['out_year_t'], 0)} т." + (f" Медь {fmt(r['cu_kg_t'], 2)} кг/т." if c["copper"]
                                           else ""))
    rows = [(n, fmt(v, 0), fmt(v / r["conversion"] * 100, 1)) for n, v in r["items"]]
    rows.append(("ИТОГО передел", fmt(r["conversion"], 0), "100,0"))
    if c["full"]:
        rows += [(n, fmt(v, 0), "") for n, v in r["full_items"]]
        rows.append(("ИТОГО полная себестоимость", fmt(r["full"], 0), ""))
    fill_table(page.cost_table, rows)
    for i, row in enumerate(rows):
        if row[0].startswith("ИТОГО"):
            for j in range(3):
                it = page.cost_table.item(i, j)
                f = it.font()
                f.setBold(True)
                it.setFont(f)


def clear(page, message=""):
    for c in page.cost_cards:
        c.set("—")
    page.cost_table.setRowCount(0)
    page.cost_info.setText("")
    page.cost_msg.setText(message)


def load(page, cost):
    """Подставляет исходные данные себестоимости из техкарты."""
    if not cost:
        return
    if page.cost_method.findText(cost.get("energy_method", "")) >= 0:
        page.cost_method.setCurrentText(cost["energy_method"])
    page.cost_copper.setChecked(bool(cost.get("copper")))
    page.cost_full.setChecked(bool(cost.get("full")))
    for key, field in page.cost_f.items():
        if key in cost and cost[key] is not None:
            field.setText(fmt(cost[key], 6).rstrip("0").rstrip(","))
