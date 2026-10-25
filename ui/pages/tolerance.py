"""Раздел «Допуски и волоки»: поле допуска, размер новой волоки, запас на износ, проверка замера."""
from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel

from core.tolerance import (LEGACY, STANDARDS, check_measure, curvature, die_plan,
                            ovality_share, tolerance)
from core.util import InputError, fmt
from ui.widgets import Card, FieldError, Page, cards_row, label, panel

STATE_TEXT = {"ok": "в допуске", "near": "у верхней границы — готовить замену волоки",
              "out": "вне допуска"}


class TolerancePage(Page):
    title = "Допуски и волоки"
    hint = "Поле допуска, размер новой волоки и запас на износ."

    def build(self):
        p = panel()
        g = QGridLayout(p)
        g.setContentsMargins(18, 16, 18, 16)
        g.setHorizontalSpacing(16)
        g.addWidget(QLabel("Допуск"), 0, 0)
        self.std = QComboBox()
        self.std.addItems(STANDARDS)
        g.addWidget(self.std, 0, 1)
        self.d = self.add_field(g, 1, "Номинальный диаметр, мм", "1,2", "tol/d")
        self.reserve = self.add_field(g, 2, "Новая волока выше нижней границы на, % поля", "25",
                                      "tol/reserve")
        self.meas = self.add_field(g, 3, "Замер проволоки, мм (необязательно)", "", "tol/meas")
        row = QHBoxLayout()
        row.addWidget(p)
        row.addStretch()
        self.body.addLayout(row)
        self.c = [Card("Наибольший диаметр", "мм"), Card("Наименьший диаметр", "мм"),
                  Card("Поле допуска", "мкм")]
        self.c2 = [Card("Размер новой волоки", "мм"), Card("Запас на износ", "мкм"),
                   Card("Овальность, не более", "мм")]
        self.body.addLayout(cards_row(self.c))
        self.body.addLayout(cards_row(self.c2))
        self.state = label("", "section", True)
        self.body.addWidget(self.state)
        self.body.addWidget(self.status)
        self.body.addWidget(label(
            "ГОСТ 2246-70: все отклонения в минус; для травленой высоколегированной проволоки "
            "допуск на 50 % больше (п. 2.2); овальность — не более половины допуска (п. 2.3). "
            "ГОСТ 7417-75 и GB/T 905-1994 — поля h по ISO 286; для промежуточных диаметров "
            "по ГОСТ 7417 и GB/T 14957 допуск берётся по ближайшему большему размеру. "
            "Запас 25 % поля — стартовое значение: уточни с учётом упругого восстановления "
            "проволоки и точности замера волок.", "note", True))
        self.body.addStretch()
        self.combos["tol/std"] = self.std
        self.legacy = LEGACY
        self.std.currentIndexChanged.connect(self.safe_recalc)

    def recalc(self):
        d = self.d.value()
        try:
            up, low = tolerance(self.std.currentText(), d)
        except InputError as e:
            raise FieldError(self.d, str(e))
        res = self.reserve.value(allow_zero=True)
        if res >= 100:
            raise FieldError(self.reserve, "Запас должен быть меньше 100 % поля допуска.")
        std = self.std.currentText()
        share, ov_text = ovality_share(std)
        plan = die_plan(d, up, low, res, share)
        self.c[0].set(fmt(plan["d_max"], 3))
        self.c[1].set(fmt(plan["d_min"], 3))
        self.c[2].set(fmt(plan["field"] * 1000, 0))
        self.c2[0].set(fmt(plan["die_new"], 3))
        self.c2[1].set(fmt(plan["wear_allow"] * 1000, 0))
        self.c2[2].set(fmt(plan["ovality"], 3))
        curv = curvature(std, d)
        extra = f"Овальность — {ov_text}."
        if curv is not None:
            extra += f" Кривизна прутка — не более {fmt(curv, 2)} мм на 1 м (табл. 2)."
        m = self.meas.value(optional=True)
        self.state.setText((f"Замер {fmt(m, 3)} мм: {STATE_TEXT[check_measure(d, up, low, m)]}. "
                            if m is not None else "") + extra)

    def clear_results(self):
        for c in self.c + self.c2:
            c.set("—")
        self.state.setText("")
