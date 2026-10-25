"""Пути к папкам программы: данные справочников и пользовательские файлы."""
import os
import sys


def app_dir():
    """Папка программы (рядом с main.py или .exe) — здесь хранятся файлы пользователя."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir():
    """Папка со справочниками. Для будущего .exe — внутри сборки, если рядом её нет."""
    local = os.path.join(app_dir(), "data")
    if os.path.isdir(local):
        return local
    return os.path.join(getattr(sys, "_MEIPASS", app_dir()), "data")
