# -*- coding: utf-8 -*-
"""Сборка программы в один .exe для компьютера без Python (Windows).

Запуск: открой этот файл в IDLE и нажми F5 — нужен интернет для установки PyInstaller.
Готовое лежит в папке dist/: «Калькулятор волочения.exe», папка data со справочниками и
ПРОЧТИ.txt. Эту папку целиком можно копировать на другой компьютер.
Сборка делается под ту систему, на которой запущена: .exe — только на Windows."""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "Калькулятор волочения"
PYINSTALLER = "pyinstaller==6.22.3"


def main():
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r",
                           os.path.join(HERE, "requirements.txt"), PYINSTALLER])
    dist = os.path.join(HERE, "dist")
    if os.path.isdir(dist):
        shutil.rmtree(dist)
    subprocess.check_call([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", NAME,
        # справочники внутри .exe — запасной вариант, если рядом нет папки data
        "--add-data", os.path.join(HERE, "data") + os.pathsep + "data",
        "--distpath", dist, "--workpath", os.path.join(HERE, "build"),
        "--specpath", os.path.join(HERE, "build"),
        os.path.join(HERE, "main.py")], cwd=HERE)
    # справочники рядом с .exe — чтобы их можно было править в Блокноте
    shutil.copytree(os.path.join(HERE, "data"), os.path.join(dist, "data"))
    shutil.copy(os.path.join(HERE, "ПРОЧТИ.txt"), dist)
    print(f"\nГотово: {dist}")


if __name__ == "__main__":
    main()
