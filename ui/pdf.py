"""Технологическая карта в PDF: средства самого Qt, без дополнительных библиотек."""
import html
import os
from datetime import date

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QFont, QPageLayout, QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import QFileDialog, QMessageBox

from core.util import fmt


def _e(x):
    return html.escape(str(x))


def card_html(name, mill, group, p, res, note=""):
    info = [("Стан", mill or "—"), ("Группа сталей", group),
            ("Маршрут", f"{fmt(p['d0'], 2)} → {fmt(p['dk'], 2)} мм за {res['n']} проходов"),
            ("Общая вытяжка / обжатие", f"{fmt(res['total'], 2)} / "
                                        f"{fmt((1 - 1 / res['total']) * 100, 1)} %"),
            ("Перевес обжатия в начале", fmt(p["ratio"], 2)),
            ("Скорость волочильного стана на финише", f"{fmt(p['v'], 1)} м/с"),
            ("Волоки: полуугол / трение", f"{fmt(p['alpha'], 1)}° / {fmt(p['mu'], 3)}"),
            ("Предел обжатия до отжига", f"{fmt(p['limit'], 0)} %"),
            ("Отжигов", str(res["anneals"])),
            ("Мин. запас прочности", f"{fmt(res['gamma_min'], 2)} (допустимо от "
                                     f"{fmt(p['gmin'], 2)})"),
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
    Усилие — по формуле Зибеля, без противонатяжения.</p>
    {'<p><b>Замечания расчёта:</b></p><ul>' + warns + '</ul>' if warns else ''}
    {cost_html}
    {'<p><b>Примечание:</b> ' + _e(note) + '</p>' if note else ''}
    <p></p><p>Технолог ____________________ &nbsp;&nbsp;&nbsp;&nbsp;
    Начальник участка ____________________ &nbsp;&nbsp;&nbsp;&nbsp;
    Утверждаю ____________________</p>
    </body></html>"""


def save_card_pdf(parent, name, mill, group, p, res, note=""):
    safe = "".join(ch if ch.isalnum() or ch in " -_.,()" else "_" for ch in name).strip()
    start = os.path.join(os.path.expanduser("~"), (safe or "техкарта") + ".pdf")
    path, _ = QFileDialog.getSaveFileName(parent, "Сохранить техкарту в PDF", start, "PDF (*.pdf)")
    if not path:
        return
    try:
        writer = QPdfWriter(path)
        writer.setTitle(name)
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setPageOrientation(QPageLayout.Orientation.Landscape)
        writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)
        doc = QTextDocument()
        doc.setDefaultFont(QFont("Segoe UI", 9))
        doc.setHtml(card_html(name, mill, group, p, res, note))
        doc.print_(writer)
        del writer   # закрывает файл
    except Exception as e:  # покажем любую ошибку печати, а не упадём молча
        QMessageBox.warning(parent, "Не удалось создать PDF", f"{type(e).__name__}: {e}")
        return
    QMessageBox.information(parent, "Готово", f"Техкарта сохранена:\n{path}")
