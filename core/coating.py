"""Омеднение: доля и расход меди по толщине покрытия."""
import math

from core.util import area

RHO_CU = 8.94  # плотность меди, г/см³


def copper_share(d, t_mm, rho_st):
    cu = RHO_CU * math.pi * d * t_mm            # г/м
    st = rho_st * area(max(d - 2 * t_mm, 0))    # г/м
    return cu, st, cu / (cu + st)


def thickness_from_share(d, share, rho_st):
    """Обратная задача: толщина слоя (мм) по массовой доле меди (доля, не %)."""
    lo, hi = 0.0, d / 2 * 0.999
    for _ in range(200):
        mid = (lo + hi) / 2
        if copper_share(d, mid, rho_st)[2] < share:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def copper_note(pct):
    """Пояснение по меди от покрытия. ГОСТ 2246-70 (п. 3.13) ограничивает медь 0,25 % только для
    неомеднённой проволоки; для омеднённой норму задают ТУ (обычно ≤ 0,30 %), AWS A5.18 — ≤ 0,50 %."""
    if pct > 0.50:
        return ("Больше 0,50 %: превышен предел AWS A5.18 для ER70S-6 (медь в проволоке вместе с "
                "покрытием) и типовые нормы ТУ.")
    if pct > 0.30:
        return ("Больше 0,30 %: выше типовой нормы ТУ на омеднённую проволоку (например, ТУ 14-4-133-73); "
                "до предела AWS A5.18 (0,50 %) запас есть.")
    return ""
