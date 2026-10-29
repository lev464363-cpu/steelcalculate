"""Свои марки: вводятся в «Материалы → Свои марки», хранятся в marki.json рядом с программой.

Каждая марка становится группой сталей для маршрута и оптимизатора (раздел «Свои марки» в
конце списка) и появляется в «Массе и упаковке» со своей плотностью. Справочник data/ не
меняется — его можно обновлять, не теряя своих марок."""
import os

from core.data import DENSITY_MAP, GROUPS
from core.paths import app_dir
from core.storage import DamagedFile, load_list, save_list
from core.util import InputError, fmt

GRADES_FILE = "marki.json"
FAMILY = "Свои марки"
# (ключ, подпись, пределы допустимого значения)
NUM_FIELDS = [("rho", "Плотность, г/см³", 1.0, 25.0),
              ("limit", "Предел обжатия до отжига, %", 1.0, 99.9),
              ("lam_max", "Макс. вытяжка за проход", 1.01, 2.0),
              ("sig0", "Прочность катанки, МПа", 50.0, 3000.0),
              ("sigf", "Прочность после обжатия, МПа", 50.0, 4000.0),
              ("red_ref", "…при суммарном обжатии, %", 1.0, 99.9),
              ("n", "Показатель упрочнения n", 0.05, 1.5),
              ("cp", "Теплоёмкость, Дж/(кг·К)", 100.0, 2000.0)]
_own = []               # имена групп, добавленных из marki.json


def grades_path():
    return os.path.join(app_dir(), GRADES_FILE)


def check_grades(rows):
    """Проверяет марки; InputError называет номер строки (с 1) и что в ней не так."""
    out, seen = [], set()
    for i, r in enumerate(rows, 1):
        name = str(r.get("name", "")).strip()
        if not name:
            raise InputError(f"Строка {i}: не указано название марки.")
        if name in GROUPS and name not in _own:
            raise InputError(f"Строка {i}: «{name}» уже есть среди встроенных групп — назови "
                             f"иначе (например, «{name}, свой»).")
        if name.lower() in seen:
            raise InputError(f"Строка {i}: марка «{name}» повторяется.")
        seen.add(name.lower())
        g = dict(name=name, note=str(r.get("note", "")).strip())
        for key, text, lo, hi in NUM_FIELDS:
            try:
                v = float(r[key])
            except (KeyError, TypeError, ValueError):
                raise InputError(f"Строка {i} ({name}): «{text}» должно быть числом.")
            if not lo <= v <= hi:
                raise InputError(f"Строка {i} ({name}): «{text}» — от {fmt(lo, 2)} до "
                                 f"{fmt(hi, 0)}.")
            g[key] = v
        if g["sigf"] <= g["sig0"]:
            raise InputError(f"Строка {i} ({name}): прочность после обжатия должна быть выше "
                             f"прочности катанки.")
        out.append(g)
    return out


def to_group(g):
    """Марка → группа сталей в том же виде, что в data/groups.json."""
    note = g["note"] or "Своя марка, данные введены вручную."
    return dict(name=g["name"], limit=g["limit"], lam_max=g["lam_max"], rho=g["rho"],
                cp=g["cp"], family=FAMILY, prep="", src=note,
                hardening=dict(sig0=g["sig0"], sigf=g["sigf"], n=g["n"], red_ref=g["red_ref"],
                               src="введено вручную (раздел «Свои марки»)."))


def apply_grades(rows):
    """Заменяет свои марки в списке групп и плотностей (встроенные не трогает)."""
    for name in _own:
        GROUPS.pop(name, None)
        DENSITY_MAP.pop(name, None)
    _own.clear()
    for g in rows:
        GROUPS[g["name"]] = to_group(g)
        DENSITY_MAP[g["name"]] = g["rho"]
        _own.append(g["name"])


def own_names():
    return list(_own)


def load_grades(path=None):
    """Читает и подключает свои марки. Ошибка в файле — пустой список: отложить повреждённый
    файл в копию и сообщить пользователю должен раздел «Свои марки»."""
    try:
        rows = check_grades(load_list(path or grades_path(), quarantine=False))
    except (DamagedFile, InputError, OSError):
        rows = []
    apply_grades(rows)
    return rows


def save_grades(rows, path=None):
    rows = check_grades(rows)
    save_list(rows, path or grades_path())
    apply_grades(rows)
    return rows


load_grades()
