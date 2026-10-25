"""Раздел «Аналитика»: практические советы по исследованиям и калькулятор структуры цены."""
import html

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QTextBrowser, QVBoxLayout, QWidget

from core.analytics import price_structure
from core.data import ANALYTICS, ANALYTICS_SIGN
from core.util import fmt
from ui import optimizer_panel
from ui.theme import T, px
from ui.widgets import Card, Page, button, cards_row, fill_table, label, make_table, panel
from ui.anim import AnimatedTabWidget


def article_html(a):
    e = html.escape
    out = [f"<h2 style='margin:0'>{e(a['title'])}</h2>",
           f"<p style='color:{T['muted']}'>{e(a.get('intro', ''))}</p>"]
    for s in a["sections"]:
        out.append(f"<h3 style='color:{T['accent']}; margin-top:14px'>{e(s['head'])}</h3><ul>")
        out += [f"<li style='margin-bottom:5px'>{e(p)}</li>" for p in s.get("points", [])]
        out.append("</ul>")
        if s.get("table"):
            cell = f"style='padding:4px 8px; border-bottom:1px solid {T['border']}'"
            head = f"style='padding:4px 8px; text-align:left; color:{T['muted']}; " \
                   f"border-bottom:2px solid {T['accent']}'"
            out.append("<table cellspacing='0' width='100%'><tr>"
                       + "".join(f"<th {head}>{e(h)}</th>" for h in s["table"]["head"]) + "</tr>")
            for row in s["table"]["rows"]:
                out.append("<tr>" + "".join(f"<td {cell}>{e(str(x))}</td>" for x in row) + "</tr>")
            out.append("</table>")
        if s.get("sources"):
            out.append(f"<p style='color:{T['muted']}; font-size:small'>Источники: "
                       f"{e(s['sources'])}</p>")
    out.append(f"<table width='100%' cellpadding='12' style='margin-top:14px; "
               f"background:{T['accent_soft']}'><tr><td>"
               f"<h3 style='margin-top:0'>Выводы</h3><ul>")
    out += [f"<li style='margin-bottom:6px'>{e(c)}</li>" for c in a["conclusion"]]
    out.append(f"</ul><p align='right'><i>— {e(ANALYTICS_SIGN)}</i></p></td></tr></table>")
    return "".join(out)


class AnalyticsPage(Page):
    title = "Аналитика"
    hint = "Факты — из открытых источников (указаны под каждым блоком); выводы — моё мнение " \
           "как ассистента, а не норматив: проверяй их на своём производстве."

    def build(self):
        self.tabs = AnimatedTabWidget()
        self.views = []
        for a in ANALYTICS:
            host = QWidget()
            lay = QVBoxLayout(host)
            lay.setContentsMargins(0, 12, 0, 0)
            view = QTextBrowser()
            view.setMinimumHeight(px(380))
            lay.addWidget(view, 1)
            self.views.append((view, a))
            if a["title"] == "Ценообразование":
                self._build_calc(lay)
            self.tabs.addTab(host, a["title"])
        titles = [a["title"] for a in ANALYTICS]
        pos = next((i + 1 for i, t in enumerate(titles) if t.startswith("Оптимальные")), 0)
        optimizer_panel.build(self, self.tabs, pos)
        self.body.addWidget(self.tabs, 1)
        self.render()

    def _build_calc(self, lay):
        lay.addWidget(label("Калькулятор структуры цены", "section"))
        row = QHBoxLayout()
        p = panel()
        g = QGridLayout(p)
        g.setContentsMargins(16, 12, 16, 12)
        g.setHorizontalSpacing(12)
        self.c_wire = self.add_field(g, 0, "Цена проволоки с НДС, руб/кг", "155", "an/wire")
        self.c_rod = self.add_field(g, 1, "Цена катанки с НДС, руб/т", "53300", "an/rod")
        self.c_conv = self.add_field(g, 2, "Передел, руб/т", "20000", "an/conv")
        self.c_pack = self.add_field(g, 3, "Упаковка, руб/кг", "12", "an/pack")
        self.c_yield = self.add_field(g, 4, "Выход годного, %", "97", "an/yield")
        self.c_vat = self.add_field(g, 5, "НДС, %", "22", "an/vat")
        take = button("Передел и упаковка из маршрута")
        g.addWidget(take, 6, 0, 1, 2)
        take.clicked.connect(self.take_from_route)
        row.addWidget(p)
        right = QVBoxLayout()
        self.cards = [Card("Цена без НДС", "руб/кг"), Card("Доля катанки", "%"),
                      Card("Остаток на сбыт и прибыль", "руб/кг")]
        right.addLayout(cards_row(self.cards))
        self.table = make_table(["Статья", "руб/кг без НДС", "Доля цены, %"])
        self.table.setMinimumHeight(px(170))
        right.addWidget(self.table)
        right.addWidget(self.status)
        row.addLayout(right, 1)
        lay.addLayout(row)

    def render(self):
        for view, a in self.views:
            view.setHtml(article_html(a))

    def recalc(self):
        r = price_structure(self.c_wire.value(), self.c_rod.value(),
                            self.c_conv.value(allow_zero=True), self.c_pack.value(allow_zero=True),
                            self.c_yield.value(), self.c_vat.value(allow_zero=True))
        rod_share = r["parts"][0][2]
        self.cards[0].set(fmt(r["wire"], 1))
        self.cards[1].set(fmt(rod_share, 0))
        self.cards[2].set(fmt(r["rest"], 1))
        fill_table(self.table, [(n, fmt(v, 1), fmt(s, 1)) for n, v, s in r["parts"]],
                   [None, None, None, (None, T["warn"]) if r["rest"] < 0 else None])
        if r["rest"] < 0:
            self.status.setText("Цена не покрывает катанку, передел и упаковку.")

    def clear_results(self):
        for c in self.cards:
            c.set("—")
        self.table.setRowCount(0)

    def on_theme(self):
        self.render()
        self.safe_recalc()

    def take_from_route(self):
        from ui.pages.route import RoutePage
        route = self.win.page_of(RoutePage)
        cost = route.res.get("cost") if route.rows and getattr(route, "res", None) else None
        if not cost:
            self.status.setText("В маршруте нет рассчитанной себестоимости: включи её на вкладке "
                                "«Экономика» маршрута.")
            return
        self.c_conv.setText(fmt(cost["conversion"], 0))
        ci = route.cost_inputs or {}
        if ci.get("full") and ci.get("pack_kg"):
            self.c_pack.setText(fmt(ci["pack_price"] / ci["pack_kg"], 1))
