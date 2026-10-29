"""Технологическая карта в PDF: средства самого Qt, без дополнительных библиотек."""
import html
import os
from datetime import date

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QFont, QPageLayout, QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import QFileDialog, QMessageBox

from core.util import fmt
from ui.popup import notify


def _e(x):
    return html.escape(str(x))


def _target(p):
    """Готовый размер: диаметр круга или профиль с эквивалентным диаметром."""
    from core import profiles as prof
    shape = p.get("shape") or prof.ROUND
    if shape == prof.ROUND:
        return f"{fmt(p['dk'], 2)} мм"
    return f"{prof.label(shape, p['size'])} (экв. Ø {fmt(p['dk'], 2)} мм)"


def card_html(name, mill, group, p, res, note=""):
    info = [("Стан", mill or "—"), ("Группа сталей", group),
            ("Маршрут", f"{fmt(p['d0'], 2)} → {_target(p)} за {res['n']} проходов"),
            ("Общая вытяжка / обжатие", f"{fmt(res['total'], 2)} / "
                                        f"{fmt((1 - 1 / res['total']) * 100, 1)} %"),
            ("Перевес обжатия в начале", fmt(p["ratio"], 2)),
            ("Скорость волочильного стана на финише", f"{fmt(p['v'], 1)} м/с"),
            ("Волоки: полуугол / трение", f"{fmt(p['alpha'], 1)}° / {fmt(p['mu'], 3)}"),
            ("Противонатяжение / σт/σв", f"{fmt(p.get('sq', 0), 0)} МПа / "
                                         f"{fmt(p.get('ys', 0.85), 2)}"),
            ("Предел обжатия до отжига", f"{fmt(p['limit'], 0)} %"),
            ("Отжигов", str(res["anneals"])),
            ("Мин. запас прочности", f"{fmt(res['gamma_min'], 2)} (допустимо от "
                                     f"{fmt(p['gmin'], 2)})"),
            ("Прочность готовой проволоки", f"{fmt(res['sig_end'], 0)} МПа"
             + (f" (требование {fmt(p['sig_min'], 0) if p.get('sig_min') else '—'}–"
                f"{fmt(p['sig_max'], 0) if p.get('sig_max') else '—'}: "
                f"{'соответствует' if res['strength_ok'] else 'НЕ соответствует'})"
                if p.get("sig_min") or p.get("sig_max") else "")),
            ("Мощность на волочение", f"{fmt(res['power'], 1)} кВт"),
            ("Температура проволоки: макс. / на намотке",
             f"{fmt(res['t_max'], 0)} / {fmt(res['t_wind'], 0)} °C" if res.get("thermal") else "—"),
            ("Производительность", f"{fmt(res['productivity'], 0)} кг/ч")]
    left = "".join(f"<tr><td class='k'>{_e(k)}</td><td>{_e(v)}</td></tr>" for k, v in info)
    heads = ["№", "Диаметр вход, мм", "Диаметр выход, мм", "Вытяжка", "Обжатие, %", "Накоп., %",
             "Прочность, МПа", "Запас прочности", "Усилие, кН", "Скорость, м/с",
             "Температура, °C", "Примечание"]
    rows = ""
    temps = res.get("thermal") or [None] * len(res["rows"])
    for r, f, t in zip(res["rows"], res["forces"], temps):
        cls = " class='ann'" if r["anneal"] else (" class='low'" if f["gamma"] < p["gmin"] else "")
        cells = [r["i"], fmt(r["d_in"]), fmt(r["d_out"]), fmt(r["lam"]), fmt(r["red"], 1),
                 fmt(r["red_cum"], 1), fmt(f["sig_out"], 0), fmt(f["gamma"], 2),
                 fmt(f["P"] / 1000, 2), fmt(r["v"], 2), fmt(t["t_out"], 0) if t else "—",
                 r["notes"]]
        rows += f"<tr{cls}>" + "".join(f"<td>{_e(c)}</td>" for c in cells) + "</tr>"
    warns = "".join(f"<li>{_e(w)}</li>" for w in res["warnings"])
    cost_html = ""
    cr = res.get("cost")
    if cr:
        crow = "".join(f"<tr><td>{_e(n)}</td><td align='right'>{fmt(v, 0)}</td>"
                       f"<td align='right'>{fmt(v / cr['conversion'] * 100, 1)}</td></tr>"
                       for n, v in cr["items"])
        crow += (f"<tr><td><b>ИТОГО передел</b></td><td align='right'><b>"
                 f"{fmt(cr['conversion'], 0)}</b></td><td align='right'>100,0</td></tr>")
        for n, v in cr["full_items"]:
            crow += f"<tr><td>{_e(n)}</td><td align='right'>{fmt(v, 0)}</td><td></td></tr>"
        if cr["full_items"]:
            crow += (f"<tr><td><b>ИТОГО полная себестоимость</b></td><td align='right'><b>"
                     f"{fmt(cr['full'], 0)}</b></td><td></td></tr>")
        cost_html = (f"<h3>Себестоимость передела</h3>"
                     f"<p class='sub'>Электроэнергия {fmt(cr['kwh_t'], 0)} кВт·ч/т; фактическая "
                     f"производительность {fmt(cr['q_f'], 0)} кг/ч; выпуск "
                     f"{fmt(cr['out_month_t'], 0)} т/мес.</p>"
                     f"<table width='55%'><tr><th>Статья</th><th>руб/т годной</th>"
                     f"<th>Доля, %</th></tr>{crow}</table>")
    return f"""
    <html><head><style>
      body {{ font-family: 'Segoe UI', Arial; font-size: 9pt; }}
      h1 {{ font-size: 15pt; margin: 0; }}
      h3 {{ font-size: 11pt; margin-bottom: 2px; }}
      .sub {{ color: #555; }}
      table {{ border-collapse: collapse; }}
      td, th {{ border: 1px solid #999; padding: 3px 6px; }}
      th {{ background: #eee; }}
      td.k {{ color: #444; }}
      tr.ann td {{ background: #fff0c2; }}
      tr.low td {{ background: #fbe4e2; }}
    </style></head><body>
    <h1>Технологическая карта волочения</h1>
    <p class='sub'><b>{_e(name)}</b> &nbsp;·&nbsp; дата печати {date.today().strftime('%d.%m.%Y')}</p>
    <table width='60%'>{left}</table>
    <p></p>
    <table width='100%'><tr>{''.join(f'<th>{_e(h)}</th>' for h in heads)}</tr>{rows}</table>
    <p class='sub'>Жёлтым — отжиг перед проходом, красным — запас прочности ниже допустимого.
    Усилие — по формуле Зибеля{' с противонатяжением' if p.get('sq') else ', без противонатяжения'}.</p>
    {'<p><b>Замечания расчёта:</b></p><ul>' + warns + '</ul>' if warns else ''}
    {cost_html}
    {'<p><b>Примечание:</b> ' + _e(note) + '</p>' if note else ''}
    <p></p><p>Технолог ____________________ &nbsp;&nbsp;&nbsp;&nbsp;
    Начальник участка ____________________ &nbsp;&nbsp;&nbsp;&nbsp;
    Утверждаю ____________________</p>
    </body></html>"""


def operator_html(name, mill, group, p, res, dies=None):
    """Маршрутная карта для оператора: только то, что нужно у стана, и графы для замеров.
    dies — рекомендации по волокам (core.dies.plan_dies): номер фильеры из журнала и угол."""
    per = (res.get("mill") or {}).get("per") or [None] * len(res["rows"])
    dies = dies if dies and len(dies) == len(res["rows"]) else [None] * len(res["rows"])
    temps = res.get("thermal") or [None] * len(res["rows"])
    stages = 1 + sum(1 for r in res["rows"] if r["anneal"])
    info = [("Техкарта", name), ("Стан", mill or "—"), ("Группа сталей", group),
            ("Маршрут", f"{fmt(p['d0'], 2)} → {_target(p)}, проходов {res['n']}"
                        + (f", этапов {stages} (отжигов {res['anneals']})" if stages > 1 else "")),
            ("Скорость на финише", f"{fmt(p['v'], 1)} м/с"),
            ("Противонатяжение", f"{fmt(p['sq'], 0)} МПа" if p.get("sq") else "нет")]
    left = "".join(f"<tr><td class='k'>{_e(k)}</td><td><b>{_e(v)}</b></td></tr>" for k, v in info)
    heads = ["№", "Барабан", "Размер волоки, мм", "Фильера №", "Угол 2α, °", "Скорость, м/с",
             "Обороты, об/мин", "T на барабане (расчёт), °C", "Замер Ø, мм", "Фильера заменена", "Отметка"]
    rows = ""
    for r, m, d, t in zip(res["rows"], per, dies, temps):
        if r["anneal"]:
            rows += (f"<tr class='ann'><td colspan='{len(heads)}'><b>ОТЖИГ — далее новый прогон "
                     f"с диаметра {fmt(r['d_in'])} мм</b></td></tr>")
        cells = [r["i"], m["drum"] if m else "—", r.get("profile") or fmt(r["d_out"]),
                 (d["stock"] or "подобрать") if d else "—", d["two_std"] if d else "—",
                 fmt(r["v"], 2), fmt(r["rpm"], 0) if r.get("rpm") else "—",
                 fmt(t["t_drum"], 0) if t else "—", "", "", ""]
        rows += "<tr>" + "".join(f"<td>{_e(c)}</td>" for c in cells) + "</tr>"
    return f"""
    <html><head><style>
      body {{ font-family: 'Segoe UI', Arial; font-size: 10pt; }}
      h1 {{ font-size: 15pt; margin: 0; }}
      .sub {{ color: #555; }}
      table {{ border-collapse: collapse; }}
      td, th {{ border: 1px solid #666; padding: 5px 7px; }}
      th {{ background: #eee; }}
      td.k {{ color: #444; }}
      tr.ann td {{ background: #fff0c2; }}
    </style></head><body>
    <h1>Маршрутная карта волочения</h1>
    <p class='sub'>Для оператора стана &nbsp;·&nbsp; дата печати {date.today().strftime('%d.%m.%Y')}</p>
    <table width='60%'>{left}</table>
    <p></p>
    <table width='100%'><tr>{''.join(f'<th>{_e(h)}</th>' for h in heads)}</tr>{rows}</table>
    <p class='sub'>Ø волоки — выходной диаметр прохода. «Подобрать» — подходящей фильеры в журнале
    нет. Температура — расчётная, для контроля пирометром.</p>
    <p></p><p>Смена ________ &nbsp;&nbsp;&nbsp; Дата ____________ &nbsp;&nbsp;&nbsp;
    Партия / плавка ________________ &nbsp;&nbsp;&nbsp; Масса, кг ________</p>
    <p>Оператор ____________________ &nbsp;&nbsp;&nbsp;&nbsp;
    Мастер ____________________ &nbsp;&nbsp;&nbsp;&nbsp; Технолог ____________________</p>
    </body></html>"""


def _save_pdf(parent, title, default_name, html_text, what):
    safe = "".join(ch if ch.isalnum() or ch in " -_.,()" else "_" for ch in default_name).strip()
    start = os.path.join(os.path.expanduser("~"), (safe or what) + ".pdf")
    path, _ = QFileDialog.getSaveFileName(parent, title, start, "PDF (*.pdf)")
    if not path:
        return
    try:
        writer = QPdfWriter(path)
        writer.setTitle(default_name)
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setPageOrientation(QPageLayout.Orientation.Landscape)
        writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)
        doc = QTextDocument()
        doc.setDefaultFont(QFont("Segoe UI", 9))
        doc.setHtml(html_text)
        doc.print_(writer)
        del writer   # закрывает файл
    except Exception as e:  # покажем любую ошибку печати, а не упадём молча
        QMessageBox.warning(parent, "Не удалось создать PDF", f"{type(e).__name__}: {e}")
        return
    notify(parent, f"{what.capitalize()} сохранена", "ok", detail=path)


def save_card_pdf(parent, name, mill, group, p, res, note=""):
    _save_pdf(parent, "Сохранить техкарту в PDF", name,
              card_html(name, mill, group, p, res, note), "техкарта")


def save_operator_pdf(parent, name, mill, group, p, res, dies=None):
    _save_pdf(parent, "Сохранить маршрутную карту в PDF", "маршрутная карта " + name,
              operator_html(name, mill, group, p, res, dies), "маршрутная карта")
