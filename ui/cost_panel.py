"""Себестоимость передела внутри «Маршрута»: ввод («гармошка» групп) и результаты.
Продукт, число проходов, отжиги и мощность берутся из рассчитанного маршрута."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel,
                               QMessageBox, QVBoxLayout, QWidget)

from core.cost import (BAR_KEYS, BLANK_BAR, BLANKS, COIL_KEYS, COPPER_KEYS, COST_NUM_KEYS,
                       ENERGY_BY_ROUTE, ENERGY_METHODS, FORMULAS, FULL_KEYS)
from core.data import PACKAGES
from core.util import fmt
from ui.theme import px
from ui.widgets import (SHARE_ROLE, Card, Collapsible, FieldError, ShareBarDelegate, button,
                        compact_combo, dot_icon, fill_table, label, make_table)
from ui.popup import notify

ZERO_OK = {"idle_pct", "tax_pct", "overhead_pct", "die_price", "lube_kg_t", "lube_price",
           "other_t", "anneal_cost_t", "repair_pct", "scrap_price", "pack_price", "cu_loss_pct",
           "mill_price", "rod_vat_pct", "t_thread", "t_change", "point_mm", "repoint_mm"}
PERCENT_100 = {"ku_pct", "yield_pct", "load_pct", "eta_pct", "idle_pct", "rod_vat_pct"}
OWN_PACK = "своя масса нетто"
# цвет раздела ввода; тем же цветом помечены статьи в таблице результатов
SECTION_COLORS = {"Режим работы": "#8C96A0", "Заготовка и заправка": "#7BC67E",
                  "Электроэнергия": "#F2B705",
                  "Персонал": "#5B9BFF", "Инструмент и материалы": "#14C4A8",
                  "Амортизация и ремонт стана": "#B07CFF", "Омеднение": "#E07A3F",
                  "Полная себестоимость": "#FF5C8A"}
ITEM_SECTION = {"Электроэнергия": "Электроэнергия",
                "Оплата труда со страховыми взносами": "Персонал", "Цеховые накладные": "Персонал",
                "Фильеры": "Инструмент и материалы", "Смазка": "Инструмент и материалы",
                "Отжиги": "Инструмент и материалы", "Прочие материалы": "Инструмент и материалы",
                "Амортизация стана": "Амортизация и ремонт стана",
                "Ремонт и обслуживание стана": "Амортизация и ремонт стана",
                "Медь на омеднение": "Омеднение"}

# (группа, [(ключ, подпись, по умолчанию)])
GROUPS = [
    ("Режим работы", [("shifts", "Смен в сутки", "2"), ("shift_h", "Часов в смене", "12"),
                      ("days", "Рабочих дней в году", "250"),
                      ("ku_pct", "Коэффициент использования стана, %", "75"),
                      ("yield_pct", "Выход годного, %", "97")]),
    ("Заготовка и заправка", [("coil_kg", "Масса бунта (мотка), кг", "1000"),
                              ("bar_m", "Длина прутка-заготовки, м", "6"),
                              ("point_mm", "Первое заострение прутка, мм", "150"),
                              ("repoint_mm", "Повторное заострение (новый металл), мм", "30"),
                              ("t_thread", "Заправка стана (на прогон), мин", "10"),
                              ("t_change", "Смена бунта / прутка, мин", "5")]),
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
    ("Полная себестоимость", [("rod_price", "Цена катанки без НДС, руб/т", "85000"),
                              ("rod_vat_pct", "НДС на катанку, %", "22"),
                              ("scrap_price", "Цена отходов (лома), руб/т", "25000"),
                              ("pack_price", "Цена одной упаковки (катушка, кассета, моток), руб",
                               "180"),
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
    box = QWidget()
    blay = QVBoxLayout(box)
    blay.setContentsMargins(0, 4, 0, 0)
    blay.setSpacing(8)
    lay.addWidget(box, 1)
    page.cost_box = box
    page.cost_sections = {}
    page.cost_f = {}
    page.cost_method = QComboBox()
    page.cost_method.addItems(ENERGY_METHODS)
    compact_combo(page.cost_method, 20)
    page.cost_copper = QCheckBox("Учитывать медь на омеднение")
    page.cost_full = QCheckBox("Добавить катанку, отходы и упаковку")
    page.cost_blank = QComboBox()
    page.cost_blank.addItems(BLANKS)
    for gi, (title, fields) in enumerate(GROUPS):
        sec = Collapsible(title, SECTION_COLORS[title], open_=gi == 0)
        page.cost_sections[title] = sec
        g = sec.grid
        extra = {"Электроэнергия": page.cost_method, "Омеднение": page.cost_copper,
                 "Полная себестоимость": page.cost_full,
                 "Заготовка и заправка": page.cost_blank}.get(title)
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
        if title == "Полная себестоимость":
            page.cost_pack = QComboBox()
            page.cost_pack.addItems([OWN_PACK] + [f"{n} — {fmt(kg, 0)} кг" for n, kg in PACKAGES])
            compact_combo(page.cost_pack, 16)
            page.cost_pack.currentIndexChanged.connect(lambda i: _pick_pack(page, i))
            r = g.rowCount()
            g.addWidget(QLabel("Упаковка"), r, 0)
            g.addWidget(page.cost_pack, r, 1)
            g.addWidget(label("НДС прибавляется к цене катанки; если цена уже с НДС — поставь 0. "
                              "Упаковка: выбери из списка — масса нетто подставится; цена — за "
                              "одну единицу (катушку, кассету, бочку, моток).", "note", True),
                        g.rowCount(), 0, 1, 2)
        if title == "Режим работы":
            g.addWidget(label("Kи — доля смены без прочих простоев: обрывов, переналадок, ожидания. "
                              "Заправка стана и смена бунтов считаются отдельно — раздел "
                              "«Заготовка и заправка».", "note", True), g.rowCount(), 0, 1, 2)
        if title == "Заготовка и заправка":
            g.addWidget(label("Стан заправляется один раз на прогон — до стольких проходов, сколько "
                              "у него блоков (вкладка «Стан»); этап длиннее или после отжига — "
                              "новый прогон со своей заправкой и сменой бунта. Пруток острится "
                              "перед каждым прогоном, отрезается один раз после последнего "
                              "прохода: первое заострение — от заготовки, следующие — ещё "
                              "20–40 мм нового металла.", "note", True), g.rowCount(), 0, 1, 2)
        blay.addWidget(sec)
    blay.addStretch()
    tabs.addTab(host, "Экономика")
    page.combos["cost/method"] = page.cost_method
    page.checks["cost/copper"] = page.cost_copper
    page.checks["cost/full"] = page.cost_full
    page.checks["cost/on"] = page.cost_on
    page.combos["cost/pack"] = page.cost_pack
    page.combos["cost/blank"] = page.cost_blank
    page.cost_blank.currentIndexChanged.connect(page.safe_recalc)
    page.cost_blank.currentIndexChanged.connect(lambda *_: update_summaries(page))
    for w in (page.cost_copper, page.cost_full, page.cost_on):
        w.toggled.connect(page.safe_recalc)
    page.cost_method.currentIndexChanged.connect(page.safe_recalc)
    # сводка в заголовках разделов — сразу видно, что задано, без раскрытия
    for w in list(page.cost_f.values()):
        w.textChanged.connect(lambda *_: update_summaries(page))
    for w in (page.cost_copper, page.cost_full):
        w.toggled.connect(lambda *_: update_summaries(page))
    page.cost_method.currentIndexChanged.connect(lambda *_: update_summaries(page))
    update_summaries(page)


def update_summaries(page):
    def v(key):
        return page.cost_f[key].text().strip() or "—"
    try:
        mill = f"{float(v('mill_price').replace(',', '.')) / 1e6:g}".replace(".", ",")
    except ValueError:
        mill = v("mill_price")
    by_route = page.cost_method.currentText() == ENERGY_BY_ROUTE
    bar = page.cost_blank.currentText() == BLANK_BAR
    text = {
        "Заготовка и заправка": (f"пруток {v('bar_m')} м, заострение {v('point_mm')} + "
                                 f"{v('repoint_mm')} мм" if bar else f"бунт {v('coil_kg')} кг")
                                + f" · заправка {v('t_thread')} мин/прогон · смена "
                                  f"{v('t_change')} мин",
        "Режим работы": f"{v('shifts')} см. × {v('shift_h')} ч, {v('days')} дн./год · "
                        f"Kи {v('ku_pct')} % · выход годного {v('yield_pct')} %",
        "Электроэнергия": f"{v('p_inst')} кВт · {v('tariff')} руб/кВт·ч · "
                          + ("по расчёту маршрута" if by_route else f"загрузка {v('load_pct')} %"),
        "Персонал": f"{v('workers')} чел. × {v('rate')} руб/ч · взносы {v('tax_pct')} % · "
                    f"накладные {v('overhead_pct')} %",
        "Инструмент и материалы": f"фильера {v('die_price')} руб / {v('die_life_t')} т · смазка "
                                  f"{v('lube_kg_t')} кг/т · отжиг {v('anneal_cost_t')} руб/т",
        "Амортизация и ремонт стана": f"стан {mill} млн руб · {v('mill_years')} лет · ремонт "
                                      f"{v('repair_pct')} %/год",
        "Омеднение": (f"слой {v('cu_um')} мкм · потери {v('cu_loss_pct')} % · "
                      f"{v('cu_price')} руб/кг") if page.cost_copper.isChecked() else "не учитывается",
        "Полная себестоимость": (f"катанка {v('rod_price')} руб/т + НДС {v('rod_vat_pct')} % · "
                                 f"упаковка {v('pack_price')} руб / {v('pack_kg')} кг")
                                if page.cost_full.isChecked() else "только передел",
    }
    for title, sec in page.cost_sections.items():
        sec.set_summary(text.get(title, ""))


def _pick_pack(page, i):
    """Упаковка из списка: масса нетто подставляется в поле."""
    if i > 0:
        page.cost_f["pack_kg"].setText(fmt(PACKAGES[i - 1][1], 0))


def _life_from_journal(page):
    from core.dies import actual_life, load_journal
    life = actual_life(load_journal())
    if not life:
        notify(page, "Стойкость не изменена", "info",
               detail="В журнале нет снятых фильер с записанной наработкой — оставлена норма.")
        return
    page.cost_f["die_life_t"].setText(fmt(life[0], 1))
    notify(page, f"Стойкость {fmt(life[0], 1)} т — из журнала", "ok",
           detail=f"Среднее по {life[1]} снятым фильерам.")
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
        cg.addWidget(c, i // 2, i % 2)          # 2 в ряд — не шире окна
    lay.addLayout(cg)
    page.cost_msg = label("", "error", True)
    lay.addWidget(page.cost_msg)
    page.cost_table = make_table(["Статья", "руб/т годной", "Доля, %"])
    page.cost_table.setItemDelegateForColumn(2, ShareBarDelegate(page.cost_table))
    page.cost_table.horizontalHeader().setMinimumSectionSize(px(90))
    page.cost_table.setMinimumHeight(px(260))
    page.cost_table.setToolTip("Галочка у статьи — включать её в экспорт в Excel.")
    page.cost_skip = set()          # статьи, которые не выгружать (сняты галочки)
    page.cost_table.itemChanged.connect(lambda it: _on_check(page, it))
    lay.addWidget(page.cost_table, 1)
    page.cost_info = label("", "muted", True)
    lay.addWidget(page.cost_info)
    bar = QHBoxLayout()
    how = button("Как считается")
    exp = button("Экспорт в Excel")
    bar.addWidget(how)
    bar.addWidget(exp)
    bar.addStretch()
    lay.addLayout(bar)
    how.clicked.connect(lambda: QMessageBox.information(page, "Как считается себестоимость",
                                                        "\n\n".join(FORMULAS)))
    exp.clicked.connect(lambda: export(page))
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
    bar = page.cost_blank.currentText() == BLANK_BAR
    for k in COIL_KEYS:
        page.cost_f[k].setEnabled(not bar)
    for k in BAR_KEYS:
        page.cost_f[k].setEnabled(bar)


def read_inputs(page):
    """Исходные данные себестоимости из полей (то, что сохраняется в техкарте)."""
    c = dict(energy_method=page.cost_method.currentText(), copper=page.cost_copper.isChecked(),
             full=page.cost_full.isChecked(), blank=page.cost_blank.currentText())
    keys = list(COST_NUM_KEYS) + list(BAR_KEYS if c["blank"] == BLANK_BAR else COIL_KEYS)
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
                                           else "")
        + (f" Заправки и смены — {fmt(r['t_aux'], 0)} мин на {c['blank'].split(' ')[0]} "
           f"за весь маршрут: стан "
           f"тянет {fmt(r['run_share'] * 100, 1 if r['run_share'] < 0.1 else 0)} % рабочего времени."
           if r.get("t_aux") else "")
        + (f" Отход на заострение прутка — {fmt(r['point_loss'] * 100, 2)} %."
           if r.get("point_loss") else ""))
    rows = [(n, fmt(v, 0), fmt(v / r["conversion"] * 100, 1)) for n, v in r["items"]]
    rows.append(("ИТОГО передел", fmt(r["conversion"], 0), "100,0"))
    if c["full"]:
        rows += [(n, fmt(v, 0), "") for n, v in r["full_items"]]
        rows.append(("ИТОГО полная себестоимость", fmt(r["full"], 0), ""))
    t = page.cost_table
    t.blockSignals(True)
    fill_table(t, rows)
    full_names = {n for n, _ in r["full_items"]}
    for i, row in enumerate(rows):
        name, first = row[0], t.item(i, 0)
        right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        t.item(i, 1).setTextAlignment(right)
        t.item(i, 2).setTextAlignment(right)
        if name.startswith("ИТОГО"):
            for j in range(3):
                it = t.item(i, j)
                f = it.font()
                f.setBold(True)
                it.setFont(f)
            continue
        sec = ITEM_SECTION.get(name, "Полная себестоимость" if name in full_names else None)
        color = SECTION_COLORS.get(sec, "#8C96A0")
        first.setIcon(dot_icon(color))
        first.setFlags(first.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        first.setCheckState(Qt.CheckState.Unchecked if name in page.cost_skip
                            else Qt.CheckState.Checked)
        if name not in full_names:
            val = dict(r["items"])[name]
            t.item(i, 2).setData(SHARE_ROLE, (val / r["conversion"], color))
    t.blockSignals(False)


def _on_check(page, item):
    """Галочка у статьи: включать ли её в экспорт."""
    if item.column() != 0 or not item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
        return
    if item.checkState() == Qt.CheckState.Checked:
        page.cost_skip.discard(item.text())
    else:
        page.cost_skip.add(item.text())


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
    if cost.get("blank") in BLANKS:
        page.cost_blank.setCurrentText(cost["blank"])
    page.cost_full.setChecked(bool(cost.get("full")))
    for key, field in page.cost_f.items():
        if key in cost and cost[key] is not None:
            field.setText(fmt(cost[key], 6).rstrip("0").rstrip(","))


def export(page):
    """Кнопка на вкладке «Себестоимость»: общее окно экспорта с отмеченной себестоимостью."""
    page.export(preset={"params", "cost", "cost_in"})


def has_cost(page):
    return bool((page.res or {}).get("cost") and page.cost_inputs)


def cost_sheets(page, items=True, inputs=True):
    """Листы для книги Excel: статьи (только отмеченные галочками) и цены с нормами."""
    r, c = page.res["cost"], page.cost_inputs
    sheets = []
    if items:
        def picked(pairs):
            return [(n, v) for n, v in pairs if n not in page.cost_skip]
        rows = [[n, round(v, 2), round(v / r["conversion"] * 100, 2)]
                for n, v in picked(r["items"])]
        rows.append(["ИТОГО передел", round(r["conversion"], 2), 100.0])
        if c.get("full"):
            rows += [[n, round(v, 2), ""] for n, v in picked(r["full_items"])]
            rows.append(["ИТОГО полная себестоимость", round(r["full"], 2), ""])
        fills = ["yellow" if row[0].startswith("ИТОГО") else None for row in rows]
        skipped = [n for n, _ in r["items"] + r["full_items"] if n in page.cost_skip]
        info = [("Передел, руб/т годной", round(r["conversion"], 2)),
                ("Факт. производительность, кг/ч", round(r["q_f"], 1)),
                ("Электроэнергия, кВт·ч/т", round(r["kwh_t"], 1)),
                ("Выпуск, т/мес", round(r["out_month_t"], 1))]
        if skipped:
            info.append(("Не выгружены (сняты галочки)", "; ".join(skipped)))
        sheets.append(("Себестоимость", info, ["Статья", "руб/т годной", "Доля, %"], rows, fills))
    if inputs:
        labels = [(key, text) for _, fields in GROUPS for key, text, _ in fields if key in c]
        rows = [["Расчёт электроэнергии", c["energy_method"]]]
        rows += [[text, c[key]] for key, text in labels]
        sheets.append(("Цены и нормы", [], ["Параметр", "Значение"], rows, None))
    return sheets


def blank_info(page):
    """Заготовка для таблицы проходов (даже при выключенной себестоимости): (вид, кг бунта или
    м прутка) или None, если в поле ошибка."""
    bar = page.cost_blank.currentText() == BLANK_BAR
    try:
        val = page.cost_f["bar_m" if bar else "coil_kg"].value()
    except FieldError:
        return None
    return page.cost_blank.currentText(), val
