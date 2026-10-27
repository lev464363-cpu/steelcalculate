"""Сохранение таблиц в Excel (.xlsx) или CSV — общий код для всех разделов."""
import csv
import os

from PySide6.QtWidgets import QFileDialog, QMessageBox

FILLS = {"yellow": "FFF0C2", "red": "FBE4E2"}


def save_table(parent, default_name, info, headers, rows, fills=None, *, sheet_name="Таблица", extra_sheets=()):
    """info — пары (параметр, значение) над таблицей; rows — строки таблицы;
    fills — подсветка строк: 'yellow', 'red' или None."""
    start = os.path.join(os.path.expanduser("~"), default_name + ".xlsx")
    path, _ = QFileDialog.getSaveFileName(parent, "Сохранить таблицу", start,
                                          "Excel (*.xlsx);;CSV для Excel (*.csv)")
    if not path:
        return
    fills = fills or [None] * len(rows)
    try:
        if path.lower().endswith(".xlsx"):
            try:
                _save_xlsx(path, info, headers, rows, fills,
                           sheet_name=sheet_name, extra_sheets=extra_sheets)
            except ImportError:
                QMessageBox.warning(parent, "Нужен openpyxl",
                                    "Для файлов Excel установи пакет командой\n"
                                    "pip install openpyxl\n\nСейчас сохраню в CSV.")
                path = os.path.splitext(path)[0] + ".csv"
                _save_csv(path, info, headers, rows)
        else:
            _save_csv(path, info, headers, rows)
        QMessageBox.information(parent, "Готово", f"Файл сохранён:\n{path}")
    except OSError as e:
        QMessageBox.warning(parent, "Не удалось сохранить", str(e))


def _save_xlsx(path, info, headers, rows, fills, *, sheet_name="Таблица", extra_sheets=()):
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    for k, val in info:
        ws.append([k, val])
    if info:
        ws.append([])
    ws.append(headers)
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True)
    for row, fill in zip(rows, fills):
        ws.append(row)
        if fill in FILLS:
            pf = PatternFill("solid", fgColor=FILLS[fill])
            for cell in ws[ws.max_row]:
                cell.fill = pf
    ws.column_dimensions["A"].width = 30 if info else 12
    for i in range(2, len(headers) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 14
    for title, sheet_rows in extra_sheets:
        extra = wb.create_sheet(title)
        for row in sheet_rows:
            extra.append(row)
        extra.column_dimensions["A"].width = 72
        extra.column_dimensions["B"].width = 28
        extra.column_dimensions["C"].width = 18
    wb.save(path)


def _save_csv(path, info, headers, rows):
    def cell(x):
        return str(x).replace(".", ",") if isinstance(x, float) else x
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        for k, val in info:
            w.writerow([k, cell(val)])
        if info:
            w.writerow([])
        w.writerow(headers)
        for row in rows:
            w.writerow([cell(x) for x in row])
