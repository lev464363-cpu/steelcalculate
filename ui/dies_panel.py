"""Вкладка «Волоки» в результатах маршрута: угол, поясок, материал по проходам, подбор из журнала."""
import os
import statistics

from PySide6.QtWidgets import (QApplication, QGridLayout, QHBoxLayout, QInputDialog, QMessageBox,
                               QVBoxLayout, QWidget)

from core.dies import book_batch, load_journal, plan_dies
from core.paths import app_dir
from core.storage import DamagedFile, load_list, save_list
from core.util import fmt
from ui.theme import T, px
from ui.widgets import Card, button, fill_table, label, make_table

HEAD = ["№", "Диаметр на выходе, мм", "Вытяжка", "Угол волоки по расчёту, °",
        "Угол волоки рекомендуемый, °", "Параметр очага деформации", "Калибрующий поясок, мм",
        "Материал", "Смазка", "В журнале", "Примечание"]


def build_results(page, tabs):
    host = QWidget()
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 12, 0, 0)
    lay.setSpacing(10)
    page.die_cards = [Card("Рабочий угол волоки", "°"), Card("Подобрано из журнала"),
                      Card("Нужно заказать")]
    cg = QGridLayout()
    cg.setSpacing(12)
    for i, c in enumerate(page.die_cards):
        cg.addWidget(c, 0, i)
    lay.addLayout(cg)
    g = QGridLayout()
    g.setHorizontalSpacing(12)
    page.wet_from = page.add_field(g, 0, "Мокрое волочение с диаметра, мм", "1,6", "route/wetfrom")
    page.match_pct = page.add_field(g, 0, "Подбор из журнала: номинал ±, %", "1", "route/matchpct",
                                    col=2)
    lay.addLayout(g)
    page.die_table = make_table(HEAD)
    page.die_table.setMinimumHeight(px(260))
    lay.addWidget(page.die_table, 1)
    bar = QHBoxLayout()
    b_copy = button("Скопировать список к заказу")
    b_apply = button("Взять рекомендованный угол в расчёт")
    b_book = button("Записать партию в журнал…")
    b_book.setToolTip("Добавить тоннаж партии к наработке фильер, подобранных из журнала.")
    bar.addWidget(b_copy)
    bar.addWidget(b_apply)
    bar.addWidget(b_book)
    bar.addStretch()
    lay.addLayout(bar)
    page.die_msg = label("", "muted", True)
    lay.addWidget(page.die_msg)
    lay.addWidget(label(
        "Угол по расчёту — минимум усилия волочения по формуле Зибеля. Рекомендуемый приведён к "
        "практике: 12–14° на основных проходах, 10–12° на чистовом и для высокоуглеродистой стали, "
        "около 10° для тонкой проволоки. Параметр очага деформации больше 3 — предупреждение, "
        "больше 4 — риск разрыва сердцевины. Формулы — «Справочник → Формулы».",
        "note", True))
    b_copy.clicked.connect(lambda: copy_order(page))
    b_apply.clicked.connect(lambda: apply_angle(page))
    b_book.clicked.connect(lambda: book(page))
    tabs.addTab(host, "Волоки")
    page.die_plan = []


def show(page, res, p, group):
    try:
        wet_from = page.wet_from.value(allow_zero=True)
        match = page.match_pct.value(allow_zero=True)
    except Exception as e:          # FieldError — показываем, маршрут не ломаем
        page.die_msg.setText(str(e))
        return
    page.die_plan = plan_dies(res["rows"], group, p["mu"], wet_from, load_journal(), match)
    angles = [x["two_std"] for x in page.die_plan]
    have = sum(1 for x in page.die_plan if x["stock"])
    page.die_cards[0].set(f"{min(angles)}–{max(angles)}" if min(angles) != max(angles)
                          else str(angles[0]))
    page.die_cards[1].set(f"{have} из {len(page.die_plan)}")
    page.die_cards[2].set(str(len(page.die_plan) - have))
    rows, colors = [], []
    for x in page.die_plan:
        rows.append((x["i"], fmt(x["d_out"], 3), fmt(x["lam"], 3), fmt(x["two_opt"], 1),
                     x["two_std"], fmt(x["delta"], 2), fmt(x["bearing"], 2), x["material"],
                     "мокрое" if x["wet"] else "сухое", x["stock"] or "—", x["notes"]))
        colors.append((T["warn_soft"], T["warn"]) if "риск" in x["notes"] else
                      (None, None) if x["stock"] else (T["anneal"], None))
        # Δ 3–4 на чистовом проходе — предупреждение без красного
    fill_table(page.die_table, rows, colors)
    page.die_msg.setText("Жёлтым — волоки нет в журнале (к заказу). Расчёт усилий сейчас ведётся с "
                         f"полууглом {fmt(p['alpha'], 1)}° для всех проходов.")


def clear(page):
    for c in page.die_cards:
        c.set("—")
    page.die_table.setRowCount(0)
    page.die_plan = []


def copy_order(page):
    need = [x for x in page.die_plan if not x["stock"]]
    if not need:
        page.die_msg.setText("Все волоки маршрута есть в журнале — заказывать нечего.")
        return
    lines = ["№\tДиаметр, мм\tРабочий угол, °\tКалибрующий поясок, мм\tМатериал"]
    lines += [f"{x['i']}\t{fmt(x['d_out'], 3)}\t{x['two_std']}\t{fmt(x['bearing'], 2)}\t"
              f"{x['material']}" for x in need]
    QApplication.clipboard().setText("\n".join(lines))
    page.die_msg.setText(f"Список из {len(need)} волок скопирован — вставь в письмо или Excel.")


def apply_angle(page):
    if not page.die_plan:
        return
    half = statistics.median(x["two_std"] for x in page.die_plan) / 2
    page.alpha.setText(fmt(half, 1))
    page.die_msg.setText(f"В расчёт взят полуугол {fmt(half, 1)}° (медиана рекомендованных); "
                         f"усилия, нагрев и запас прочности пересчитаны.")


def book(page):
    """Партия протянута по маршруту: её тоннаж добавляется к наработке фильер из журнала."""
    ids = [x["stock"] for x in page.die_plan if x["stock"]]
    if not ids:
        page.die_msg.setText("В маршруте нет фильер из журнала — записывать нечего.")
        return
    tons, ok = QInputDialog.getDouble(page, "Партия", f"Масса протянутой партии, т (фильер из "
                                      f"журнала: {len(ids)}):", 0.0, 0.0, 100000.0, 3)
    if not ok or tons <= 0:
        return
    note = " ".join(x for x in (page.mill.currentText().strip(), f"{fmt(page.p['dk'], 2)} мм") if x)
    path = os.path.join(app_dir(), "filery.json")
    try:
        journal = load_list(path)
        missing = book_batch(journal, ids, tons, note)
        save_list(journal, path)
    except (DamagedFile, OSError) as e:
        QMessageBox.warning(page, "Журнал фильер", f"Партия не записана:\n{e}")
        return
    done = [i for i in ids if i not in missing]
    page.die_msg.setText(f"Партия {fmt(tons, 3)} т записана: фильеры {', '.join(done)}."
                         + (f" Не найдены в работе: {', '.join(missing)}." if missing else ""))
    page.safe_recalc()        # износ изменился — подбор из журнала обновится
