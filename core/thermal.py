"""Температура проволоки по проходам: нагрев в волоке и охлаждение на барабане.

Нагрев: работа волочения на единицу объёма равна напряжению волочения σвол, почти вся она
превращается в тепло (до 90 % остаётся в проволоке — Радионова и др., Metals, 2022):
    ΔT = k · σвол / (c · ρ),  k = 0,9.
Охлаждение на барабане: снимается доля η перегрева над температурой охлаждающей воды:
    Tпосле = Tв + (Tвых − Tв) · (1 − η).
Если задана опорная скорость vоп (при ней на чистовом барабане снимается η), то по закону
экспоненциального остывания (как в модели Радионовой и др.: exp(−2·Bi·Fo), Fo ~ время, время на
барабане ~ 1/v, постоянная остывания ~ d) на барабане прохода i остаётся доля перегрева
    (1 − η) ^ ((vоп / vᵢ) · (dₖ / dᵢ)):
медленные и тонкие участки остывают сильнее, разгон стана ухудшает охлаждение.
После отжига проволока снова холодная (температура заготовки).
"""
K_HEAT = 0.9          # доля работы волочения, остающаяся в проволоке
T_AGING = 180.0       # выше — условия для статического деформационного старения (180–200 °C)
T_WINDING = 100.0     # тёплая намотка: при 100–140 °C на катушке идёт старение


def remaining_share(cool_pct, v_ref, v_i, d_k, d_i):
    """Доля перегрева, остающаяся после барабана (см. описание модуля)."""
    keep = 1 - cool_pct / 100
    if v_ref is None or keep <= 0:
        return keep
    return keep ** ((v_ref / v_i) * (d_k / d_i))


def wire_temperatures(rows, forces, rho, c, t0, tw, cool_pct, k_heat=K_HEAT, v_ref=None,
                      d_ref=None):
    """rho — г/см³, c — Дж/(кг·К); v_ref — опорная скорость охлаждения, м/с (None — доля
    охлаждения одинакова на всех барабанах). Возвращает по проходу t_in, dT, t_out, t_drum (°C)."""
    out, t_in = [], t0
    d_k = d_ref or (rows[-1].get("d_out", 1.0) if rows else 1.0)   # диаметр точки калибровки
    for r, f in zip(rows, forces):
        if r.get("anneal"):
            t_in = t0
        dt = k_heat * f["sig_d"] * 1e6 / (c * rho * 1000)
        t_out = t_in + dt
        keep = remaining_share(cool_pct, v_ref, r.get("v", 1.0), d_k, r.get("d_out", d_k))
        t_drum = tw + (t_out - tw) * keep
        out.append(dict(t_in=t_in, dT=dt, t_out=t_out, t_drum=t_drum))
        t_in = t_drum
    return out


def calibrate_cooling(rows, forces, rho, c, t0, tw, pass_no, t_meas, v_ref=None, d_ref=None):
    """Доля охлаждения η (%), при которой температура проволоки на барабане прохода pass_no
    равна замеренной. None — если замер недостижим при η от 0 до 100 %."""
    def t_at(cool):
        return wire_temperatures(rows, forces, rho, c, t0, tw, cool,
                                 v_ref=v_ref, d_ref=d_ref)[pass_no - 1]["t_drum"]
    hi_t, lo_t = t_at(0.0), t_at(100.0)          # без охлаждения — горячее всего
    if not lo_t - 1e-9 <= t_meas <= hi_t + 1e-9:
        return None
    lo, hi = 0.0, 100.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if t_at(mid) > t_meas:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
