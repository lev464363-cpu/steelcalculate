"""Раздел «Омеднение»."""
from PySide6.QtWidgets import QGridLayout, QHBoxLayout

from core.coating import copper_note, copper_share, thickness_from_share
from core.util import fmt
from ui.widgets import Card, FieldError, Page, cards_row, label, panel


class CopperPage(Page):
    title = "Омеднение"
    hint = "Расход меди по толщине покрытия и обратный расчёт по анализу."

    def build(self):
        row = QHBoxLayout()
        row.setSpacing(16)
        p = panel()
        g = QGridLayout(p)
        g.setContentsMargins(18, 16, 18, 16)
        g.setHorizontalSpacing(16)
        g.addWidget(label("По толщине покрытия", "section"), 0, 0, 1, 2)
        self.d = self.add_field(g, 1, "Диаметр проволоки, мм", "1,2", "cu/d")
        self.t = self.add_field(g, 2, "Толщина медного слоя, мкм", "0,3", "cu/t")
        self.rho = self.add_field(g, 3, "Плотность стали, г/см³", "7,85", "cu/rho")
        self.T = self.add_field(g, 4, "Объём партии, т", "10", "cu/T")
        self.loss = self.add_field(g, 5, "Потери меди в процессе, %", "10", "cu/loss")
        row.addWidget(p)
        q = panel()
        g2 = QGridLayout(q)
        g2.setContentsMargins(18, 16, 18, 16)
        g2.setHorizontalSpacing(16)
        g2.addWidget(label("Обратный расчёт", "section"), 0, 0, 1, 2)
        self.pct = self.add_field(g2, 1, "Медь от покрытия, % масс.", "0,2", "cu/pct")
        g2.addWidget(label("Если анализ даёт общее содержание Cu, сначала вычти медь основного "
                           "металла по сертификату катанки. Ограничение ГОСТ 2246-70 (0,25 %) "
                           "относится только к неомеднённой проволоке; для омеднённой норма — по ТУ "
                           "(обычно ≤ 0,30 %), по AWS A5.18 — ≤ 0,50 %.", "note", True), 2, 0, 1, 2)
        g2.setRowStretch(3, 1)
        row.addWidget(q)
        row.addStretch()
        self.body.addLayout(row)
        self.c = [Card("Медь на 1 км", "г"), Card("Медь на 1 кг проволоки", "г"),
                  Card("Доля меди", "% масс."), Card("Расход на партию", "кг"),
                  Card("С учётом потерь", "кг")]
        self.body.addLayout(cards_row(self.c))
        self.cb = Card("Толщина слоя по анализу", "мкм")
        r2 = QHBoxLayout()
        r2.addWidget(self.cb)
        r2.addStretch(4)
        self.body.addLayout(r2)
        self.warn = label("", "error", True)
        self.body.addWidget(self.warn)
        self.body.addWidget(self.status)
        self.body.addStretch()

    def recalc(self):
        d = self.d.value()
        t = self.t.value() / 1000
        rho = self.rho.value()
        T_ = self.T.value()
        loss = self.loss.value(allow_zero=True)
        if loss >= 100:
            raise FieldError(self.loss, "Потери должны быть меньше 100 %.")
        if 2 * t >= d:
            raise FieldError(self.t, "Слой слишком толстый для такого диаметра.")
        cu, st, share = copper_share(d, t, rho)
        net = share * T_ * 1000
        self.c[0].set(fmt(cu * 1000, 1))
        self.c[1].set(fmt(share * 1000, 3))
        self.c[2].set(fmt(share * 100, 3))
        self.c[3].set(fmt(net, 2))
        self.c[4].set(fmt(net / (1 - loss / 100), 2))
        self.warn.setText(copper_note(share * 100))
        pct = self.pct.value(optional=True)
        if pct is None:
            self.cb.set("—")
            return
        p = pct / 100
        if p >= 1:
            raise FieldError(self.pct, "Доля меди должна быть меньше 100 %.")
        self.cb.set(fmt(thickness_from_share(d, p, rho) * 1000, 3))

    def clear_results(self):
        for c in self.c + [self.cb]:
            c.set("—")
        self.warn.setText("")
