"""Профили станов (файл stany.json рядом с программой) и проверка маршрута на стане."""
import os

from core.drawing import split_runs
from core.paths import app_dir
from core.storage import load_list, save_list
from core.util import fmt

MILLS_FILE = "stany.json"
DRIVE_INDIVIDUAL = "Индивидуальный привод барабанов"
DRIVE_COMMON = "Общий привод (вытяжки заданы кинематикой)"
DRIVES = [DRIVE_INDIVIDUAL, DRIVE_COMMON]


def mills_path():
    return os.path.join(app_dir(), MILLS_FILE)


def load_mills(path=None):
    """Повреждённый файл откладывается в резервную копию (DamagedFile), см. core.storage."""
    return load_list(path or mills_path())


def save_mills(mills, path=None):
    save_list(mills, path or mills_path())


def find_mill(mills, name):
    name = (name or "").strip().lower()
    return next((m for m in mills if m["name"].strip().lower() == name), None) if name else None


def check_mill(mill, rows, forces, v_fin):
    """Каждый этап маршрута (между отжигами) — отдельный прогон через стан: его проходы ставятся
    на последние барабаны (последний проход — на чистовой). Возвращает по проходу номер барабана,
    загрузку привода, скольжение; и предупреждения."""
    drums = int(mill["drums"])
    warnings, per = [], []
    stages, k = [], 0
    for st in split_runs(rows):            # прогон — проходы одной заправки стана
        stages.append((st, forces[k:k + len(st)]))
        k += len(st)
    too_long = [str(i + 1) for i, (st, _) in enumerate(stages) if len(st) > drums]
    if too_long:
        what = (f"проходов {len(rows)}" if len(stages) == 1 else
                f"этап(ы) {', '.join(too_long)} длиннее числа барабанов")
        warnings.append(f"Маршрут не помещается на стан «{mill['name']}»: {what}, а барабанов "
                        f"{drums}. Нужен второй стан, отжиг или меньше проходов.")
        return dict(per=[None] * len(rows), warnings=warnings, max_load=None, fits=False)
    v_top = max(st[-1]["v"] for st, _ in stages)
    if v_top > mill["v_max"] + 1e-9:
        warnings.append(f"Скорость на финише {fmt(v_top, 1)} м/с больше паспортной для стана "
                        f"«{mill['name']}» ({fmt(mill['v_max'], 1)} м/с).")
    common = mill.get("drive") == DRIVE_COMMON and mill.get("kin")
    overloaded, negative = [], []
    for st, st_forces in stages:
        u = None
        if common:
            # окружные скорости: чистовой барабан = скорость этапа на финише, к началу делим на λкин
            u = [0.0] * drums
            u[-1] = st[-1]["v"]
            for j in range(drums - 1, 0, -1):
                u[j - 1] = u[j] / mill["kin"][j - 1]
        first = drums - len(st)
        for i, (r, f) in enumerate(zip(st, st_forces)):
            j = first + i
            load = (f["power"] / (mill["eta"] / 100) / mill["p_motor"] * 100
                    if mill.get("p_motor") else None)
            slip = (1 - r["v"] / u[j]) * 100 if u else None
            if load is not None and load > 100:
                overloaded.append(r["i"])
            if slip is not None and slip < -0.5:
                negative.append(r["i"])
            per.append(dict(drum=j + 1, load=load, slip=slip))
    if overloaded:
        warnings.append(f"Перегрузка привода барабанов на проходах {', '.join(map(str, overloaded))}: "
                        f"мощность волочения больше мощности двигателя.")
    if negative:
        warnings.append(f"На проходах {', '.join(map(str, negative))} проволока обгоняет барабан "
                        f"(отрицательное скольжение): вытяжка в волоке должна быть не меньше "
                        f"кинематической вытяжки барабана, иначе — натяжение и обрывы.")
    loads = [x["load"] for x in per if x["load"] is not None]
    return dict(per=per, warnings=warnings, max_load=max(loads) if loads else None, fits=True)
