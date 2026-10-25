"""Раздел «Справочник» с подвкладками по группам материалов, формулам и НТД."""
import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLineEdit, QTextBrowser,
                               QVBoxLayout, QWidget)

from core.data import FILTER_BY_KIND, REFERENCE, STANDARDS
from core.formulas import SECTIONS as FORMULA_SECTIONS
from core.util import fmt
from ui.theme import T, px
from ui.widgets import Page, fill_table, label, make_table, panel
from ui.anim import AnimatedTabWidget


class RefTab(QWidget):
    """Одна подвкладка справочника: поиск, таблица, карточка выбранной марки."""

    def __init__(self, items, with_kind=False):
        super().__init__()
        self.setObjectName("refTab")
        self.items = items
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 14, 0, 0)
        lay.setSpacing(12)
        top = QHBoxLayout()
        self.flt = None
        if with_kind:
            self.flt = QComboBox()
            self.flt.addItems(["Все", "Сплошная", "Порошковая"])
            top.addWidget(self.flt)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по марке, аналогу или стандарту")
        top.addWidget(self.search, 1)
        lay.addLayout(top)
        self.table = make_table(["Марка", "Аналоги (EN / AISI / UNS)", "Плотность, г/см³",
                                 "Стандарт"])
        self.table.setMinimumHeight(px(260))
        lay.addWidget(self.table, 1)
        p = panel()
        pl = QVBoxLayout(p)
        pl.setContentsMargins(18, 14, 18, 14)
        self.details = label("Выбери марку в таблице.", None, True)
        self.details.setTextFormat(Qt.TextFormat.RichText)
        pl.addWidget(self.details)
        lay.addWidget(p)
        if self.flt:
            self.flt.currentIndexChanged.connect(self.fill)
        self.search.textChanged.connect(self.fill)
        self.table.itemSelectionChanged.connect(self.show_details)
        self.fill()

    def fill(self, *args):
        q = self.search.text().strip().lower()
        kind = self.flt.currentText() if self.flt else "Все"
        self.shown = [it for it in self.items
                      if (kind == "Все" or it.get("kind") == kind)
                      and (not q or q in it["name"].lower() or q in it["analog"].lower()
                           or q in it["std"].lower())]
        fill_table(self.table, [(it["name"], it["analog"], fmt(it["rho"], 2), it["std"])
                                for it in self.shown])

    def show_details(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        it = self.shown[rows[0].row()]
        sub = ", ".join(x for x in (it.get("kind", "").lower(), it.get("type", "").lower(),
                                    it["std"]) if x)
        self.details.setText(
            f"<b style='font-size:12pt'>{it['name']}</b> &nbsp; "
            f"<span style='color:{T['muted']}'>{sub}</span>"
            f"<p><b>Аналоги:</b> {it['analog']}<br><b>Плотность:</b> {fmt(it['rho'], 2)} г/см³</p>"
            f"<p><b>Состав, %:</b> {it['comp']}</p><p><b>Применение:</b> {it['use']}</p>")


class ReferencePage(Page):
    title = "Справочник"
    hint = "Марки, аналоги и плотности; на вкладке «Формулы» — все формулы расчётов программы."

    def build(self):
        self.tabs = AnimatedTabWidget()
        self.tab_list = []
        for cat, items in REFERENCE.items():
            tab = RefTab(items, with_kind=FILTER_BY_KIND.get(cat, False))
            self.tab_list.append(tab)
            self.tabs.addTab(tab, f"{cat}  ({len(items)})")
        self.formulas = QTextBrowser()
        self.formulas.setOpenExternalLinks(False)
        self.formulas.setMinimumHeight(px(420))
        self.tabs.addTab(self.formulas, "Формулы")
        self.render_formulas()
        ntd = QWidget()
        nl = QVBoxLayout(ntd)
        nl.setContentsMargins(0, 14, 0, 0)
        self.ntd_pick = QComboBox()
        self.ntd_pick.addItems([b["title"] for b in STANDARDS])
        nl.addWidget(self.ntd_pick)
        self.ntd = QTextBrowser()
        self.ntd.setMinimumHeight(px(420))
        nl.addWidget(self.ntd, 1)
        nl.addWidget(label("Требования изложены своими словами по открытым публикациям стандартов, "
                           "это не официальный текст. Перед применением сверяйся с действующими "
                           "редакциями.", "note", True))
        self.tabs.addTab(ntd, "НТД: Россия и Китай")
        self.ntd_pick.currentIndexChanged.connect(self.render_ntd)
        self.render_ntd()
        self.body.addWidget(self.tabs, 1)
        self.body.addWidget(label("Составы, плотности и аналоги — справочно. Аналог с пометкой «≈» "
                                  "близок, но не идентичен. Перед применением сверяйся с "
                                  "действующими стандартами, ТУ и сертификатом.", "note", True))

    def render_formulas(self):
        parts = [f"<p style='color:{T['muted']}'>Все формулы, по которым считает программа. "
                 f"Обозначения: d — диаметр, мм; λ — вытяжка; ε — деформация; σ — напряжение, МПа; "
                 f"v — скорость, м/с.</p>"]
        for title, items in FORMULA_SECTIONS:
            parts.append(f"<h3 style='color:{T['accent']}; margin-top:14px'>{title}</h3>")
            for name, formula, note in items:
                parts.append(f"<p style='margin:6px 0 0 0'><b>{name}</b></p>")
                if formula:
                    parts.append(f"<p style='margin:2px 0 0 18px; font-size:large'>{formula}</p>")
                if note:
                    parts.append(f"<p style='margin:2px 0 0 18px; color:{T['muted']}'>{note}</p>")
        self.formulas.setHtml("".join(parts))

    def render_ntd(self, *args):
        if not STANDARDS:
            self.ntd.setHtml("Файл data/standards.json не найден.")
            return
        b = STANDARDS[max(0, self.ntd_pick.currentIndex())]
        e = html.escape
        cell = f"style='padding:6px 10px; border-bottom:1px solid {T['border']}; vertical-align:top'"
        head = f"style='padding:6px 10px; text-align:left; color:{T['muted']}; " \
               f"border-bottom:2px solid {T['accent']}'"
        out = [f"<h3 style='color:{T['accent']}'>{e(b['title'])}</h3>",
               f"<p><b>Россия:</b> {e(b['ru'])}<br><b>Китай:</b> {e(b['cn'])}</p>",
               f"<table width='100%' cellspacing='0'><tr><th {head}>Параметр</th>"
               f"<th {head}>Россия</th><th {head}>Китай</th></tr>"]
        for p, ru, cn in b["rows"]:
            out.append(f"<tr><td {cell}><b>{e(p)}</b></td><td {cell}>{e(ru)}</td>"
                       f"<td {cell}>{e(cn)}</td></tr>")
        out.append("</table>")
        if b.get("grades"):
            out.append(f"<h4 style='margin-top:16px'>Соответствие марок</h4>"
                       f"<table width='100%' cellspacing='0'><tr><th {head}>Марка РФ</th>"
                       f"<th {head}>Состав, %</th><th {head}>Марка КНР</th>"
                       f"<th {head}>Состав, %</th></tr>")
            for g in b["grades"]:
                out.append("<tr>" + "".join(f"<td {cell}>{e(x)}</td>" for x in g) + "</tr>")
            out.append("</table>")
        out.append(f"<h4 style='margin-top:16px'>Вывод</h4><p>{e(b['conclusion'])}</p>")
        out.append(f"<p style='color:{T['muted']}'>Пункты стандартов: {e(b['sources'])}</p>")
        self.ntd.setHtml("".join(out))

    def on_theme(self):
        for tab in self.tab_list:
            tab.show_details()
        self.render_formulas()
        self.render_ntd()
