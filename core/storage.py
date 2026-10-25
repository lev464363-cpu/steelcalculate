"""Чтение и запись файлов пользователя (журнал фильер, техкарты, станы) без потери данных.

Запись атомарная: сначала во временный файл рядом, затем замена — при сбое питания старый файл
остаётся целым. Повреждённый файл не перезаписывается: он переименовывается в резервную копию,
а программа начинает с пустого списка и сообщает, где лежит копия."""
import json
import os
from datetime import datetime


class DamagedFile(ValueError):
    """Файл пользователя повреждён; текст — для показа пользователю."""


def _backup_name(path):
    root, ext = os.path.splitext(path)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{root}.повреждён-{stamp}{ext}"
    k = 1
    while os.path.exists(name):
        k += 1
        name = f"{root}.повреждён-{stamp}-{k}{ext}"
    return name


def load_list(path, quarantine=True):
    """Список из JSON-файла; нет файла — пустой список.
    Повреждённый файл (или не список) при quarantine переименовывается в резервную копию и
    вызывает DamagedFile — следующее сохранение уже не затрёт прежние данные."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
        problem = "в файле не список записей"
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        problem = str(e)
    name = os.path.basename(path)
    if not quarantine:
        raise DamagedFile(f"Файл {name} повреждён: {problem}.")
    backup = _backup_name(path)
    os.replace(path, backup)
    raise DamagedFile(f"Файл {name} повреждён ({problem}).\n"
                      f"Он сохранён как {os.path.basename(backup)}, начинаю с пустого списка.")


def save_list(data, path):
    """Атомарная запись: временный файл, сброс на диск, замена."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
