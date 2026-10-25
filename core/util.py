"""Общие вспомогательные функции: разбор чисел, форматирование, геометрия сечения."""
import math


class InputError(Exception):
    """Ошибка во входных данных, текст показывается пользователю."""


def num(s):
    s = str(s).strip().replace(",", ".")
    if not s:
        raise ValueError
    return float(s)


def fmt(x, nd=3):
    return f"{x:.{nd}f}".replace(".", ",")


def area(d):
    return math.pi * d * d / 4


def g_per_m(rho, d):
    # rho г/см³ × площадь мм² = граммы на 1 метр
    return rho * area(d)
