"""Раздел «Масса и упаковка»."""
from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel

from core.data import DENSITY_MAP, PACKAGES, REFERENCE
from core.grades import own_names
from core.util import fmt, g_per_m
from ui.theme import px
from ui.widgets import Card, Page, cards_row, label, make_table, fill_table, panel


class MassPage(Page):
    title = "Масса и упаковка"
    hint = "Масса погонного метра, длина в бухте и в стандартной упаковке."

    def build(self):
        p = panel()
        g = QGridLayout(p)
        g.setContentsMargins(18, 16, 18, 16)
        g.setHorizontalSpacing(16)
        g.addWidget(QLabel("Материал"), 0, 0)
        self.mat = QComboBox()
        self.mat.setMaxVisibleItems(20)
        self.fill_materials()
        self.mat.setCurrentText("Св-08Г2С")
        g.addWidget(self.mat, 0, 1)
        self.rho = self.add_field(g, 1, "Плотность, г/см³", "7,85", "mass/rho")
        self.d = self.add_field(g, 2, "Диаметр, мм", "1,2", "mass/d")
        self.L = self.add_field(g, 3, "Длина, м", "1000", "mass/L")
        self.M = self.add_field(g, 4, "Масса бухты, кг", "15", "mass/M")
        g.addWidget(label("Для порошковой проволоки надёжнее взвесить 1 м и подставить фактическую "
                          "плотность.", "note", True), 5, 0, 1, 2)
        row = QHBoxLayout()
        row.addWidget(p)
        row.addStretch()
        self.body.addLayout(row)
        self.c = [Card("Масса 1 м", "г"), Card("Масса заданной длины", "кг"),
                  Card("Длина по массе бухты", "м")]
        self.body.addLayout(cards_row(self.c))
        self.body.addWidget(self.status)
        self.body.addWidget(label("Длина в стандартной упаковке", "section"))
        self.table = make_table(["Упаковка", "Масса нетто, кг", "Длина, м", "Длина, км"])
        self.table.setMinimumHeight(px(230))
        self.body.addWidget(self.table, 1)
        self.combos["mass/mat"] = self.mat
        self.mat.currentIndexChanged.connect(
            lambda *_: self.rho.setText(fmt(DENSITY_MAP.get(self.mat.currentText(), 7.85), 2)))

    def fill_materials(self):
        """Марки справочника и свои марки (раздел «Свои марки»); выбор сохраняется."""
        cur = self.mat.currentText()
        self.mat.blockSignals(True)
        self.mat.clear()
        for items in list(REFERENCE.values()) + [[dict(name=n) for n in own_names()]]:
            if not items:
                continue
            if self.mat.count():
                self.mat.insertSeparator(self.mat.count())
            for it in items:
                self.mat.addItem(it["name"])
        if cur:
            self.mat.setCurrentText(cur)
        self.mat.blockSignals(False)

    def on_show(self):
        self.fill_materials()

    def recalc(self):
        rho = self.rho.value()
        d = self.d.value()
        gpm = g_per_m(rho, d)
        L = self.L.value(optional=True)
        M = self.M.value(optional=True)
        self.c[0].set(fmt(gpm, 3))
        self.c[1].set(fmt(gpm * L / 1000, 3) if L else "—")
        self.c[2].set(fmt(M * 1000 / gpm, 0) if M else "—")
        rows = []
        for name, kg in PACKAGES:
            length = kg * 1000 / gpm
            rows.append((name, fmt(kg, 0), fmt(length, 0), fmt(length / 1000, 2)))
        fill_table(self.table, rows)

    def clear_results(self):
        for c in self.c:
            c.set("—")
        self.table.setRowCount(0)
