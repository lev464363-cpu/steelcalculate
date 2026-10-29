"""Квадратные и шестигранные профили: геометрия сечения и вытяжки маршрута.

Размер профиля a: квадрат — сторона, шестигранник — размер под ключ (между гранями).
Углы скруглены радиусом r. Площадь многоугольника с внутренним углом β при каждом угле
уменьшается на r²·(ctg(β/2) − (π − β)/2):
    квадрат:       S = a² − (4 − π)·r²;
    шестигранник:  S = (√3/2)·a² − 6·(ctg 60° − π/6)·r².
Эквивалентный круг — той же площади: dэкв = √(4S/π). Маршрут, усилия, масса и скорости
считаются по эквивалентному кругу; фасонные проходы помечаются в таблице.

Способы получения:
  из круга       — круглые проходы, затем n_shape проходов через фасонные волоки;
                   общая вытяжка фасонных проходов λф задаётся (Ø круга перед ними
                   = √(4·λф·Sк/π)) и делится между ними поровну;
  из профиля     — горячекатаный профиль размера a₀ калибруется n_shape проходами того же
                   профиля, вытяжка поровну: λ = (S₀/Sк)^(1/n)."""
import math

ROUND, SQUARE, HEX = "круг", "квадрат", "шестигранник"
SHAPES = [ROUND, SQUARE, HEX]
FROM_ROUND, FROM_PROFILE = "из круга", "из горячекатаного профиля"
WAYS = [FROM_ROUND, FROM_PROFILE]
# внутренний угол и число углов
_POLY = {SQUARE: (math.pi / 2, 4), HEX: (2 * math.pi / 3, 6)}


def sharp_area(shape, a):
    return a * a if shape == SQUARE else math.sqrt(3) / 2 * a * a


def area(shape, a, r=0.0):
    """Площадь сечения, мм²; для круга a — диаметр."""
    if shape == ROUND:
        return math.pi * a * a / 4
    beta, k = _POLY[shape]
    return sharp_area(shape, a) - k * r * r * (1 / math.tan(beta / 2) - (math.pi - beta) / 2)


def eq_diameter(shape, a, r=0.0):
    return math.sqrt(4 * area(shape, a, r) / math.pi)


def across_corners(shape, a, r=0.0):
    """Диаметр описанной окружности с учётом скругления углов, мм."""
    if shape == ROUND:
        return a
    beta, _ = _POLY[shape]
    r_sharp = a / math.sqrt(2) if shape == SQUARE else a / math.sqrt(3)   # центр → острый угол
    return 2 * (r_sharp - r / math.sin(beta / 2) + r)


def max_radius(shape, a):
    """Наибольший радиус скругления — при нём угол превращается во вписанную окружность."""
    return a / 2


def check(shape, a, r):
    from core.util import InputError
    if a <= 0:
        raise InputError("Размер профиля должен быть больше нуля.")
    if not 0 <= r < max_radius(shape, a):
        raise InputError(f"Радиус скругления углов — от 0 до {max_radius(shape, a):g} мм.")


def shaped_lams(p, n):
    """Вытяжки проходов маршрута на профиль (p — параметры маршрута, n — всего проходов).
    Возвращает (вытяжки, номера фасонных проходов с 1, Ø круга перед фасонными или None)."""
    from core.drawing import distribute
    from core.util import InputError, fmt
    shape, a, r = p["shape"], p["size"], p.get("corner_r") or 0.0
    n_sh = int(p.get("n_shape") or 1)
    if n_sh < 1 or n_sh > n:
        raise InputError(f"Фасонных проходов — от 1 до {n}.")
    s_end = area(shape, a, r)
    if p.get("way") == FROM_PROFILE:
        if n != n_sh:
            raise InputError("При калибровке горячекатаного профиля все проходы фасонные: число "
                             "проходов = числу фасонных проходов.")
        s0 = area(shape, p["size0"], r)
        if s0 <= s_end:
            raise InputError("Горячекатаный профиль должен быть больше готового.")
        lam = (s0 / s_end) ** (1 / n)
        return [lam] * n, list(range(1, n + 1)), None
    lam_sh = p.get("lam_shape") or 1.15
    if lam_sh <= 1:
        raise InputError("Вытяжка в фасонной волоке должна быть больше 1.")
    d_round = math.sqrt(4 * lam_sh * s_end / math.pi)    # Ø круга перед первой фасонной
    if d_round >= p["d0"]:
        raise InputError(f"Круг перед фасонной волокой (Ø {fmt(d_round, 2)} мм) не меньше исходного "
                         f"диаметра: уменьши вытяжку в фасонной волоке или возьми катанку больше.")
    n_round = n - n_sh
    if n_round < 1:
        raise InputError("Нужен хотя бы один круглый проход до фасонной волоки.")
    lam_round = (p["d0"] / d_round) ** 2
    lams = distribute(lam_round, n_round, p["ratio"])
    if min(lams) <= 1.0:
        best = max((k for k in range(1, n_round + 1)
                    if min(distribute(lam_round, k, p["ratio"])) > 1.0), default=1)
        raise InputError(f"Круглой части маршрута (Ø {fmt(p['d0'], 2)} → Ø {fmt(d_round, 2)} мм, "
                         f"вытяжка {fmt(lam_round, 2)}) хватит {best} проход(а); сейчас "
                         f"{n_round}. Уменьши "
                         f"число проходов до {best + n_sh} или нажми «Подобрать число проходов».")
    # вытяжка λф (круг → готовый профиль) делится поровну между фасонными проходами
    lams += [lam_sh ** (1 / n_sh)] * n_sh
    return lams, list(range(n_round + 1, n + 1)), d_round


def size_from_area(shape, s, r=0.0):
    """Размер профиля (сторона / под ключ) по площади сечения при том же радиусе углов."""
    if shape == ROUND:
        return math.sqrt(4 * s / math.pi)
    beta, k = _POLY[shape]
    coef = 1.0 if shape == SQUARE else math.sqrt(3) / 2
    return math.sqrt((s + k * r * r * (1 / math.tan(beta / 2) - (math.pi - beta) / 2)) / coef)


def label(shape, a):
    return f"{shape} {a:g} мм".replace(".", ",") if shape != ROUND else f"Ø {a:g} мм"
