"""Раздел «Техкарты и сравнение»: сохранённые маршруты, открытие, PDF, сравнение 2–3 вариантов."""
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QMessageBox, QTableWidgetItem)

from core.cards import compare, load_cards, save_cards
from core.cost import cost_for_route
from core.mills import find_mill, load_mills
from core.storage import DamagedFile
from core.route_plan import plan_route
from core.util import InputError, fmt
from ui.pdf import save_card_pdf
from ui.theme import T, px
from ui.widgets import Page, button, fill_table, label, make_table, tab_box
from ui.anim import AnimatedTabWidget

HEAD = ["Название", "Стан", "Группа сталей", "Маршрут, мм", "Проходов", "Отжигов", "Мин. запас прочности",
        "Произв., кг/ч", "Передел, руб/т", "Изменена"]


class CardsPage(Page):
    title = "Техкарты"
    hint = "Двойной щелчок — открыть техкарту в маршруте. Для сравнения выдели 2–3 с Ctrl. " \
           "Себестоимость считается по ценам, сохранённым в техкарте."

    def build(self):
        self.cards, self.results, self.compared = [], [], []
        self.tabs = AnimatedTabWidget()
        self.body.addWidget(self.tabs, 1)
        lst = tab_box(self.tabs, "Список")
        self.table = make_table(HEAD)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setMinimumHeight(px(260))
        lst.addWidget(self.table, 1)
        bar = QHBoxLayout()
        b_open = button("Открыть в маршруте", primary=True)
        b_cmp = button("Сравнить выбранные")
        b_pdf = button("В PDF")
        b_del = button("Удалить")
        for b in (b_open, b_cmp, b_pdf, b_del):
            bar.addWidget(b)
        bar.addStretch()
        lst.addLayout(bar)
        lst.addWidget(self.status)
        cmp = tab_box(self.tabs, "Сравнение")
        self.cmp_note = label("Выдели в списке 2–3 техкарты (с Ctrl) и нажми «Сравнить выбранные». "
                              "Лучшее значение в каждой строке выделено.", "muted", True)
        cmp.addWidget(self.cmp_note)
        self.cmp = make_table(["Показатель"])
        self.cmp.setMinimumHeight(px(360))
        cmp.addWidget(self.cmp, 1)
        b_open.clicked.connect(self.open_selected)
        b_cmp.clicked.connect(self.compare_selected)
        b_pdf.clicked.connect(self.pdf_selected)
        b_del.clicked.connect(self.delete_selected)
        self.table.doubleClicked.connect(lambda *_: self.open_selected())
        self.refresh()

    def on_show(self):
        self.refresh()

    def on_theme(self):
        self.refresh()
        if self.compared:
            self.show_compare(self.compared)

    def refresh(self):
        self.status.setText("")
        try:
            self.cards = load_cards()
        except (OSError, ValueError) as e:
            self.cards = []
            self.status.setText(f"Не удалось прочитать файл техкарт: {e}")
        self.results, rows, colors = [], [], []
        try:
            mills = load_mills()
        except DamagedFile as e:
            mills = []
            self.status.setText(f"{self.status.text()}\n{e}".strip())
        except (OSError, ValueError):
            mills = []
        for c in self.cards:
            try:
                r = plan_route(c["params"], c["group"], find_mill(mills, c.get("mill")))
            except (InputError, KeyError, TypeError, ValueError, ZeroDivisionError):
                r = None
            if r is not None:
                try:
                    r["cost"] = cost_for_route(c["cost"], c["params"], r) if c.get("cost") \
                        else None
                except (InputError, KeyError, TypeError, ValueError, ZeroDivisionError):
                    r["cost"] = None
            self.results.append(r)
            p = c.get("params", {})
            route = f"{fmt(p['d0'], 2)} → {fmt(p['dk'], 2)}" if "d0" in p and "dk" in p else "—"
            if r:
                cost = fmt(r["cost"]["conversion"], 0) if r["cost"] else "—"
                rows.append((c["name"], c.get("mill") or "—", c["group"], route, r["n"],
                             r["anneals"], fmt(r["gamma_min"], 2), fmt(r["productivity"], 0),
                             cost, c.get("updated", "")))
                colors.append((None, T["warn"]) if r["warnings"] else None)
            else:
                rows.append((c["name"], c.get("mill") or "—", c.get("group", ""), route,
                             "—", "—", "—", "—", "—", "ошибка в данных"))
                colors.append((T["warn_soft"], T["warn"]))
        fill_table(self.table, rows, colors)
        if not self.cards and not self.status.text():
            self.status.setText("Техкарт пока нет. Рассчитай маршрут и нажми «Сохранить техкарту» "
                                "в разделе «Маршрут и скорости».")

    def selected(self):
        return sorted({i.row() for i in self.table.selectionModel().selectedRows()})

    def _one(self):
        idx = self.selected()
        if len(idx) != 1:
            QMessageBox.information(self, "Техкарты", "Выдели одну техкарту.")
            return None
        return idx[0]

    def open_selected(self):
        i = self._one()
        if i is not None:
            self.win.open_card(self.cards[i])

    def pdf_selected(self):
        i = self._one()
        if i is None:
            return
        c, r = self.cards[i], self.results[i]
        if r is None:
            QMessageBox.warning(self, "Техкарты", "В этой техкарте ошибка в данных: открой её в "
                                                  "маршруте, исправь и сохрани заново.")
            return
        save_card_pdf(self, c["name"], c.get("mill", ""), c["group"], c["params"], r,
                      c.get("note", ""))

    def delete_selected(self):
        idx = self.selected()
        if not idx:
            QMessageBox.information(self, "Техкарты", "Выдели техкарты для удаления.")
            return
        names = [self.cards[i]["name"] for i in idx]
        if QMessageBox.question(self, "Удалить", "Удалить техкарты?\n\n" + "\n".join(names)) \
                != QMessageBox.StandardButton.Yes:
            return
        cards = [c for i, c in enumerate(self.cards) if i not in idx]
        try:
            save_cards(cards)
        except OSError as e:
            QMessageBox.warning(self, "Техкарты", f"Не удалось сохранить:\n{e}")
            return
        self.compared = []
        self.cmp.setRowCount(0)
        self.refresh()

    def compare_selected(self):
        idx = self.selected()
        if not 2 <= len(idx) <= 3:
            QMessageBox.information(self, "Сравнение", "Выдели 2 или 3 техкарты (с клавишей Ctrl).")
            return
        if any(self.results[i] is None for i in idx):
            QMessageBox.warning(self, "Сравнение", "В одной из техкарт ошибка в данных.")
            return
        self.compared = [self.cards[i]["name"] for i in idx]
        self.show_compare(self.compared)
        self.tabs.setCurrentIndex(1)

    def show_compare(self, names):
        pairs = [(c, r) for c, r in zip(self.cards, self.results) if c["name"] in names and r]
        if len(pairs) < 2:
            self.cmp.setRowCount(0)
            return
        cards, results = [p[0] for p in pairs], [p[1] for p in pairs]
        table = compare(cards, results)
        self.cmp.setColumnCount(1 + len(cards))
        self.cmp.setHorizontalHeaderLabels(["Показатель"] + [c["name"] for c in cards])
        self.cmp.setRowCount(len(table))
        for r, (title, texts, best) in enumerate(table):
            self.cmp.setItem(r, 0, QTableWidgetItem(title))
            for j, text in enumerate(texts):
                it = QTableWidgetItem(text)
                if best == j:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                    it.setBackground(QBrush(QColor(T["accent_soft"])))
                self.cmp.setItem(r, j + 1, it)
        self.cmp_note.setText("Лучшее значение в каждой строке выделено. Если значения равны, "
                              "выделения нет.")
