"""Раздел «Вытяжка»: один проход."""
import math

from PySide6.QtWidgets import QGridLayout, QHBoxLayout

from core.drawing import heading_reduction
from core.util import area, fmt
from ui.widgets import Card, Page, cards_row, label, panel


class DrawPage(Page):
    title = "Вытяжка за проход"
    hint = "Вытяжка, обжатие и деформация для одной волоки."

    def build(self):
        p = panel()
        g = QGridLayout(p)
        g.setContentsMargins(18, 16, 18, 16)
        g.setHorizontalSpacing(16)
        self.d0 = self.add_field(g, 0, "Диаметр до волочения, мм", "3,0", "draw/d0")
        self.d1 = self.add_field(g, 1, "Диаметр после волочения, мм", "2,5", "draw/d1")
        row = QHBoxLayout()
        row.addWidget(p)
        row.addStretch()
        self.body.addLayout(row)
        self.c = [Card("Коэффициент вытяжки"), Card("Обжатие по площади", "%"),
                  Card("Логарифмическая деформация"), Card("Площадь сечения после", "мм²")]
        self.body.addLayout(cards_row(self.c))
        self.body.addWidget(label("Калиброванный пруток под холодную высадку", "section"))
        self.heading = Card("Рекомендуемое обжатие для готового диаметра", "%")
        self.heading_note = label("", "muted", True)
        hr = QHBoxLayout()
        hr.addWidget(self.heading, 1)
        hr.addWidget(self.heading_note, 3)
        self.body.addLayout(hr)
        self.body.addWidget(self.status)
        self.body.addStretch()

    def recalc(self):
        d0 = self.d0.value()
        d1 = self.d1.value()
        lam = (d0 / d1) ** 2
        self.c[0].set(fmt(lam))
        self.c[1].set(fmt((1 - 1 / lam) * 100, 2))
        self.c[2].set(fmt(2 * math.log(d0 / d1), 4))
        self.c[3].set(fmt(area(d1)))
        rec = heading_reduction(d1)
        if rec is None:
            self.heading.set("—")
            self.heading_note.setText("Рекомендация действует для прутков 6,5–34 мм.")
        else:
            red = (1 - 1 / lam) * 100
            self.heading.set(f"{fmt(rec[0], 1)}–{fmt(rec[1], 1)}")
            verdict = ("в рекомендуемом диапазоне" if rec[0] <= red <= rec[1] else
                       "меньше рекомендуемого" if red < rec[0] else "больше рекомендуемого")
            self.heading_note.setText(
                f"Сейчас обжатие {fmt(red, 1)} % — {verdict}. По авторскому свидетельству СССР "
                f"1752466 (ЧерМК) при таком обжатии пластичность металла перед высадкой "
                f"максимальна, брак при высадке минимален. Перед волочением — термообработка "
                f"и обточка на 3–4 % диаметра.")

    def clear_results(self):
        for c in self.c + [self.heading]:
            c.set("—")
        self.heading_note.setText("")
