"""Подвкладка «Свои марки»: марки и группы сталей, введённые вручную, — для маршрута,
оптимизатора и массы."""
from PySide6.QtWidgets import QInputDialog

from core.data import GROUPS
from core.grades import FAMILY, NUM_FIELDS, grades_path, save_grades
from core.util import fmt
from ui.table_editor import TableEditorPage
from ui.widgets import button


class GradesPage(TableEditorPage):
    title = "Свои марки"
    hint = ("Свои марки и группы сталей. После сохранения они появляются в «Маршруте» и "
            "оптимизаторе (раздел «Свои марки» в конце списка групп) и в «Массе и упаковке». "
            "Данные — в файле marki.json рядом с программой.")
    COLUMNS = ([("name", "Марка / группа", "text")]
               + [(k, text, "num") for k, text, _, _ in NUM_FIELDS]
               + [("note", "Примечание", "note")])
    COPY_CLEAR = "name"
    COPY_TIP = "Те же параметры — останется вписать название новой марки."
    NOTE_PLACEHOLDER = "Например: ТУ на катанку, откуда взята прочность, особенности подготовки…"
    FOOTNOTE = ("Проще всего начать с кнопки «Заполнить из группы…»: подставятся параметры похожей "
                "встроенной группы, останется поправить свои. Прочность — лучше по сертификату "
                "катанки и замеру готовой проволоки; n можно подобрать по замеру в «Маршруте» "
                "(вкладка «Металл»).")

    def extra_buttons(self):
        b = button("Заполнить из группы…")
        b.setToolTip("Новая строка с параметрами выбранной встроенной группы.")
        b.clicked.connect(self.from_group)
        return [b]

    def from_group(self):
        names = [n for n, g in GROUPS.items() if g.get("family") != FAMILY]
        name, ok = QInputDialog.getItem(self, "Заполнить из группы", "Группа-образец:", names, 0,
                                        False)
        if not ok:
            return
        g, h = GROUPS[name], GROUPS[name]["hardening"]
        src = dict(rho=g["rho"], limit=g["limit"], lam_max=g["lam_max"], sig0=h["sig0"],
                   sigf=h["sigf"], red_ref=h["red_ref"], n=h["n"], cp=g.get("cp", 470))
        vals = [""] + [fmt(src[k], 4).rstrip("0").rstrip(",") for k, _, _, _ in NUM_FIELDS]
        vals.append(f"По образцу группы «{name}».")
        self.add_row(vals)
        self.table.setCurrentCell(self.table.rowCount() - 1, 0)

    def path(self):
        return grades_path()

    def save_rows(self, rows):
        return save_grades(rows)

    def saved_text(self, saved):
        return (f"Сохранено марок: {len(saved)}. Они уже есть в списке групп «Маршрута» "
                f"(раздел «{FAMILY}») и в «Массе и упаковке».")

