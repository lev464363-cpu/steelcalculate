"""Связка с DEFORM: выгрузка геометрии проходов и загрузка результатов расчёта как поправок.

Выгрузка (папка на маршрут), для каждого прохода i:
    pass_i_die.stl        — волока (тело вращения): заходный конус 2α, калибрующий поясок,
                            выходной конус; внутренний контур — по рабочему диаметру прохода;
    pass_i_workpiece.stl  — заготовка, уже вошедшая в волоку (для установившегося режима):
                            Ø входа → конус по волоке → Ø выхода;
    pass_i_profile.dxf    — те же контуры в осевом сечении (r, z) — для DEFORM-2D или эскиза;
    route.csv             — параметры проходов: диаметры, угол, поясок, скорость, трение, усилие;
    results_template.csv  — таблица для результатов DEFORM по проходам.
Единицы — мм; ось волочения — Z, проволока движется в +Z.

Загрузка: заполненный results_template.csv (усилие, деформация за проход на поверхности и в
оси, максимальная повреждаемость). По нему считаются поправки к модели очага деформации:
    k_force — усилие DEFORM / усилие программы (по формуле Зибеля), среднее по проходам;
    k_shear — (εпов − εось) DEFORM / то же по модели Avitzur, среднее по проходам;
    Δпред — наименьший Δ прохода, где повреждаемость достигла критической (если задана).
Поправки хранятся в deform.json рядом с программой и применяются к маршрутам той же группы."""
import csv
import io
import math
import os
from datetime import date

from core.dies import bearing_share, delta
from core.paths import app_dir
from core.storage import load_list, save_list
from core.util import InputError, fmt, num

CALIB_FILE = "deform.json"
SEGMENTS = 96                       # шагов по окружности в STL

RESULT_HEADERS = ["Проход", "Усилие, кН", "Деформация за проход: поверхность",
                  "Деформация за проход: ось", "Повреждаемость макс."]
RESULT_KEYS = ["i", "force_kN", "eps_surface", "eps_center", "damage"]


# ---------------- геометрия ----------------

def die_profile(d_in, d_out, alpha_deg, bearing_mm):
    """Осевое сечение волоки — замкнутый контур (r, z), мм. Вход — при z = 0."""
    a = math.radians(alpha_deg)
    r_in, r_out = d_in / 2, d_out / 2
    r_entry = r_in * 1.15                          # заход чуть шире заготовки
    z_cone = (r_entry - r_out) / math.tan(a)
    z_bear = z_cone + bearing_mm
    r_back = r_out * 1.25                          # выходной конус 2·30°
    z_back = z_bear + (r_back - r_out) / math.tan(math.radians(30))
    r_outer = max(r_in * 3, r_in + 6)              # наружный диаметр вставки
    inner = [(r_entry, 0.0), (r_out, z_cone), (r_out, z_bear), (r_back, z_back)]
    # внутренний контур, затем наружный в обратную сторону — замкнутое кольцевое сечение
    return inner + [(r_outer, z_back), (r_outer, 0.0)], dict(z_cone=z_cone, z_bear=z_bear,
                                                            z_end=z_back, r_outer=r_outer)


def workpiece_profile(d_in, d_out, alpha_deg, bearing_mm, lead=None, tail=None):
    """Заготовка в волоке: цилиндр Ø входа до встречи с конусом, конус по волоке, поясок и
    вышедший конец Ø выхода. Контур от оси (r = 0) — сплошное тело."""
    a = math.radians(alpha_deg)
    r_in, r_out = d_in / 2, d_out / 2
    r_entry = r_in * 1.15
    z_touch = (r_entry - r_in) / math.tan(a)       # где заготовка касается конуса
    z_cone = (r_entry - r_out) / math.tan(a)
    lead = lead if lead is not None else 3 * d_in
    tail = tail if tail is not None else 2 * d_out
    z0, z1 = z_touch - lead, z_cone + bearing_mm + tail
    return [(0.0, z0), (r_in, z0), (r_in, z_touch), (r_out, z_cone), (r_out, z1), (0.0, z1)]


def revolve_stl(profile, name, segments=SEGMENTS):
    """ASCII STL тела вращения замкнутого контура (r, z) вокруг оси Z; нормали — наружу."""
    out = io.StringIO()
    out.write(f"solid {name}\n")
    pts = list(profile)
    # обход контура против часовой стрелки в плоскости (r, z) даёт нормали внутрь — развернуть
    area2 = sum(pts[j][0] * pts[(j + 1) % len(pts)][1] - pts[(j + 1) % len(pts)][0] * pts[j][1]
                for j in range(len(pts)))
    if area2 > 0:
        pts.reverse()
    n = len(pts)
    for k in range(segments):
        t0, t1 = 2 * math.pi * k / segments, 2 * math.pi * (k + 1) / segments
        c0, s0, c1, s1 = math.cos(t0), math.sin(t0), math.cos(t1), math.sin(t1)
        for j in range(n):
            (ra, za), (rb, zb) = pts[j], pts[(j + 1) % n]
            if ra < 1e-9 and rb < 1e-9:
                continue                            # отрезок по оси — без площади
            a0, a1 = (ra * c0, ra * s0, za), (ra * c1, ra * s1, za)
            b0, b1 = (rb * c0, rb * s0, zb), (rb * c1, rb * s1, zb)
            for tri in ((a0, b0, b1), (a0, b1, a1)):
                if _degenerate(tri):
                    continue
                nx, ny, nz = _normal(tri)
                out.write(f"facet normal {nx:.6e} {ny:.6e} {nz:.6e}\n outer loop\n")
                for v in tri:
                    out.write(f"  vertex {v[0]:.6e} {v[1]:.6e} {v[2]:.6e}\n")
                out.write(" endloop\nendfacet\n")
    out.write(f"endsolid {name}\n")
    return out.getvalue()


def _normal(tri):
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = tri
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return nx / ln, ny / ln, nz / ln


def _degenerate(tri):
    return len({tuple(round(c, 9) for c in v) for v in tri}) < 3


def profile_dxf(contours):
    """DXF (R12) с замкнутыми полилиниями в плоскости X = r, Y = z; contours — {слой: контур}."""
    lines = ["0", "SECTION", "2", "ENTITIES"]
    for layer, pts in contours.items():
        lines += ["0", "POLYLINE", "8", layer, "66", "1", "70", "1"]
        for r, z in pts:
            lines += ["0", "VERTEX", "8", layer, "10", f"{r:.6f}", "20", f"{z:.6f}", "30", "0.0"]
        lines += ["0", "SEQEND", "8", layer]
    lines += ["0", "ENDSEC", "0", "EOF"]
    return "\n".join(lines) + "\n"


def export_route(folder, rows, forces, p, group):
    """Пишет файлы для DEFORM в папку folder. Возвращает список созданных файлов."""
    os.makedirs(folder, exist_ok=True)
    files = []
    wet_from = 1.6
    with open(os.path.join(folder, "route.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Проход", "Ø вход, мм", "Ø выход, мм", "Вытяжка", "Полуугол α, °",
                    "Поясок, мм", "Δ очага", "Скорость, м/с", "Трение μ (Кулон)",
                    "Фактор трения m", "Противонатяжение, МПа", "Прочность на выходе, МПа",
                    "Усилие (Зибель), кН", "Отжиг перед проходом"])
        for r, f in zip(rows, forces):
            bear = bearing_share(group, r["d_out"] <= wet_from) * r["d_out"]
            w.writerow([r["i"], _c(r["d_in"], 4), _c(r["d_out"], 4), _c(r["lam"], 4),
                        _c(p["alpha"], 2), _c(bear, 3), _c(delta(math.radians(p["alpha"]),
                                                                  r["lam"]), 3),
                        _c(r["v"], 3), _c(p["mu"], 3), _c(math.sqrt(3) * p["mu"], 3),
                        _c(f.get("sig_q", 0.0), 1), _c(f["sig_out"], 0), _c(f["P"] / 1000, 3),
                        "да" if r["anneal"] else ""])
            die, _ = die_profile(r["d_in"], r["d_out"], p["alpha"], bear)
            wp = workpiece_profile(r["d_in"], r["d_out"], p["alpha"], bear)
            for fname, text in ((f"pass_{r['i']:02d}_die.stl", revolve_stl(die, "die")),
                                (f"pass_{r['i']:02d}_workpiece.stl",
                                 revolve_stl(wp, "workpiece")),
                                (f"pass_{r['i']:02d}_profile.dxf",
                                 profile_dxf({"DIE": die, "WORKPIECE": wp}))):
                with open(os.path.join(folder, fname), "w", encoding="ascii") as fh:
                    fh.write(text)
                files.append(fname)
    files.insert(0, "route.csv")
    with open(os.path.join(folder, "results_template.csv"), "w", newline="",
              encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(RESULT_HEADERS)
        for r in rows:
            w.writerow([r["i"], "", "", "", ""])
    files.append("results_template.csv")
    with open(os.path.join(folder, "ПРОЧТИ_DEFORM.txt"), "w", encoding="utf-8") as fh:
        fh.write(README)
    files.append("ПРОЧТИ_DEFORM.txt")
    return files


def _c(x, nd):
    return fmt(x, nd)


README = """Файлы для DEFORM, выгруженные из «Калькулятора волочения».

Единицы — мм. Ось волочения — Z, проволока движется в +Z. Начало координат — вход в волоку.
pass_NN_die.stl        — волока (жёсткий инструмент). Внутренний диаметр пояска = Ø выхода.
pass_NN_workpiece.stl  — заготовка, уже вошедшая в волоку (пластичный объект).
pass_NN_profile.dxf    — осевое сечение: слои DIE и WORKPIECE (для DEFORM-2D или эскиза).
route.csv              — параметры проходов: скорость, трение (μ и фактор m), противонатяжение.

Для DEFORM-3D обычно достаточно сектора 1/4 или 1/8 — отрежьте его плоскостями симметрии.
Скорость волочения задаётся перемещением заготовки (или волоки) по Z.

Результаты: заполните results_template.csv по каждому рассчитанному проходу
  Усилие, кН                         — установившееся усилие волочения (Load prediction);
  Деформация за проход: поверхность  — Strain-Effective у поверхности на выходе из пояска;
  Деформация за проход: ось          — Strain-Effective в оси там же;
  Повреждаемость макс.               — Damage (Cockcroft–Latham), максимум в оси.
Если заготовка в DEFORM начиналась без накопленной деформации, вписывайте значения как есть;
если с накопленной — разность выход минус вход. Пустые ячейки допустимы.
Затем в программе: «Маршрут → Деформация → Загрузить результаты DEFORM».
"""


# ---------------- результаты и поправки ----------------

def parse_results(text):
    """Строки результатов из CSV (разделитель ; , или табуляция; дробная часть — запятая или
    точка). Возвращает [{i, force_kN, eps_surface, eps_center, damage}] — без пустых."""
    sample = text[:2000]
    delim = ";" if sample.count(";") >= sample.count("\t") else "\t"
    if delim == ";" and sample.count(";") == 0:
        delim = ","
    rows = []
    for k, cells in enumerate(csv.reader(io.StringIO(text), delimiter=delim)):
        if not cells or not "".join(cells).strip():
            continue
        try:
            i = int(num(cells[0]))
        except (ValueError, IndexError):
            if k == 0:
                continue                           # заголовок
            raise InputError(f"Строка {k + 1}: в первом столбце должен быть номер прохода.")
        row = dict(i=i)
        for key, cell in zip(RESULT_KEYS[1:], cells[1:]):
            cell = cell.strip()
            if cell:
                try:
                    row[key] = num(cell)
                except ValueError:
                    raise InputError(f"Строка {k + 1}: «{cell}» — не число.")
        if len(row) > 1:
            rows.append(row)
    if not rows:
        raise InputError("В файле нет заполненных строк результатов.")
    return rows


class Calibration:
    """Поправки к модели по расчётам DEFORM."""

    def __init__(self, k_force=1.0, k_shear=1.0, delta_limit=None, name="", group="",
                 n_points=0):
        self.k_force, self.k_shear, self.delta_limit = k_force, k_shear, delta_limit
        self.name, self.group, self.n_points = name, group, n_points

    @classmethod
    def from_dict(cls, d):
        return cls(d.get("k_force", 1.0), d.get("k_shear", 1.0), d.get("delta_limit"),
                   d.get("name", ""), d.get("group", ""), len(d.get("points", [])))


def calibrate(results, model_rows, forces, damage_crit=None):
    """Сопоставляет результаты DEFORM с моделью по номерам проходов.
    model_rows — проходы core.deform_model (eps по сечению), forces — из plan_route.
    Возвращает словарь калибровки с точками сравнения."""
    by_i = {m["i"]: (m, f) for m, f in zip(model_rows, forces)}
    pts, kf, ks, bad = [], [], [], []
    for r in results:
        if r["i"] not in by_i:
            raise InputError(f"Прохода № {r['i']} нет в текущем маршруте.")
        m, f = by_i[r["i"]]
        pt = dict(r, lam=m["lam"], delta=m["delta"], model_force_kN=f["P"] / 1000,
                  model_surface=m["surface"], model_center=m["center"])
        if r.get("force_kN"):
            kf.append(r["force_kN"] / (f["P"] / 1000))
        if r.get("eps_surface") is not None and r.get("eps_center") is not None:
            dm = m["surface"] - m["center"]
            if dm > 1e-9:
                ks.append(max(r["eps_surface"] - r["eps_center"], 0.0) / dm)
        if damage_crit and r.get("damage") is not None and r["damage"] >= damage_crit:
            bad.append(m["delta"])
        pts.append(pt)
    return dict(k_force=sum(kf) / len(kf) if kf else 1.0,
                k_shear=sum(ks) / len(ks) if ks else 1.0,
                delta_limit=min(bad) if bad else None, damage_crit=damage_crit,
                n_force=len(kf), n_shear=len(ks), points=pts)


def calib_path():
    return os.path.join(app_dir(), CALIB_FILE)


def load_calibrations(path=None):
    return load_list(path or calib_path())


def save_calibration(entry, path=None):
    """Добавляет калибровку; у одной группы активна последняя сохранённая."""
    rows = load_calibrations(path)
    for r in rows:
        if r.get("group") == entry["group"]:
            r["active"] = False
    rows.append(dict(entry, active=True, date=date.today().strftime("%d.%m.%Y")))
    save_list(rows, path or calib_path())
    return rows


def active_calibration(group, rows=None):
    """Активная калибровка группы, иначе None. На другие группы не переносится: поправки
    зависят от металла и смазки."""
    try:
        rows = rows if rows is not None else load_calibrations()
    except (OSError, ValueError):
        return None
    same = [r for r in rows if r.get("group") == group and r.get("active")]
    return Calibration.from_dict(same[-1]) if same else None
