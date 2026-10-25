"""Загрузка справочников из папки data. Ошибки в файлах сообщаются понятным текстом."""
import json
import os

from core.paths import data_dir


class DataError(Exception):
    pass


def _load(name):
    path = os.path.join(data_dir(), name)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise DataError(f"Не найден файл справочника: {path}")
    except json.JSONDecodeError as e:
        raise DataError(f"Ошибка в файле {name}, строка {e.lineno}: {e.msg}.\n"
                        f"Скорее всего, пропущена запятая или кавычка после последней правки.")


_groups = _load("groups.json")["groups"]
_materials = _load("materials.json")["categories"]
_packages = _load("packages.json")

# Группы сталей для маршрута: имя -> параметры (вместе с упрочнением)
GROUPS = {g["name"]: g for g in _groups}

# Справочник: категория -> список марок; признак фильтра по виду проволоки
REFERENCE = {c["category"]: c["items"] for c in _materials}
FILTER_BY_KIND = {c["category"]: c.get("filter_by_kind", False) for c in _materials}
DENSITY_MAP = {it["name"]: it["rho"] for items in REFERENCE.values() for it in items}

PACKAGES = [(p["name"], p["kg"]) for p in _packages["packages"]]

# Аналитика: статьи и подпись выводов (файл необязательный)
try:
    _an = _load("analytics.json")
    ANALYTICS, ANALYTICS_SIGN = _an["articles"], _an.get("signature", "")
except DataError:
    ANALYTICS, ANALYTICS_SIGN = [], ""

# Сравнение НТД России и Китая (файл необязательный)
try:
    STANDARDS = _load("standards.json")["blocks"]
except DataError:
    STANDARDS = []
DIE_TYPES = _packages["die_types"]
