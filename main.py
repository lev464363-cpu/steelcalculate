# -*- coding: utf-8 -*-
"""
Калькулятор волочения — запуск программы.
Открой этот файл в IDLE и нажми F5 (или запусти двойным кликом).

Структура папки:
    core/   — расчёты (формулы), без интерфейса
    data/   — справочники в файлах .json, их можно править
    ui/     — окно программы и разделы
    tests/  — проверка расчётов: открыть tests/test_calc.py и нажать F5
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def ensure_pyside6():
    """Если PySide6 нет, ставит её в тот же Python, которым запущена программа."""
    try:
        import PySide6  # noqa: F401
        return True
    except ImportError:
        pass
    import struct
    import subprocess
    bits = struct.calcsize("P") * 8
    print("Библиотека PySide6 не найдена.")
    print(f"Python: {sys.version.split()[0]}, {bits}-бит, файл: {sys.executable}")
    if bits == 32:
        print("\nУ тебя 32-битный Python, а PySide6 работает только с 64-битным.")
        print("Скачай 64-битный установщик Python с python.org и запусти программу снова.")
        return False
    print("\nПробую установить автоматически, это займёт 1–3 минуты...\n")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--user",
                               "PySide6", "openpyxl"])
    except (subprocess.CalledProcessError, OSError) as e:
        print(f"\nУстановка не удалась: {e}")
        print("Скопируй весь текст из этого окна и пришли его — разберёмся.")
        return False
    import importlib
    import site
    importlib.invalidate_caches()
    user_site = site.getusersitepackages()
    if user_site not in sys.path:
        sys.path.append(user_site)
    try:
        import PySide6  # noqa: F401
    except ImportError:
        print("\nУстановка прошла, но библиотека пока не видна. Запусти программу ещё раз.")
        return False
    return True


def main():
    if not ensure_pyside6():
        input("\nНажми Enter, чтобы закрыть...")
        sys.exit(1)
    from core.data import DataError
    try:
        from ui.main_window import run
    except DataError as e:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication(sys.argv)  # noqa: F841
        QMessageBox.critical(None, "Ошибка в справочнике", str(e))
        sys.exit(1)
    run()


if __name__ == "__main__":
    main()
