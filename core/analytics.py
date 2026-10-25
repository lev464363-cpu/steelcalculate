"""Структура цены проволоки: сколько в ней катанки, передела, упаковки и что остаётся."""
from core.util import InputError


def price_structure(wire_price, rod_price_t, conv_t, pack_kg, yield_pct, vat_pct,
                    prices_with_vat=True):
    """wire_price — руб/кг; rod_price_t — руб/т; conv_t — передел, руб/т; pack_kg — упаковка,
    руб/кг. Цены проволоки и катанки при prices_with_vat — с НДС. Всё возвращается без НДС, руб/кг."""
    if not 0 < yield_pct <= 100:
        raise InputError("Выход годного — от 1 до 100 %.")
    k = 1 + vat_pct / 100 if prices_with_vat else 1.0
    wire = wire_price / k
    if wire <= 0:
        raise InputError("Цена проволоки должна быть больше нуля.")
    rod = rod_price_t / k / 1000 / (yield_pct / 100)
    conv = conv_t / 1000
    rest = wire - rod - conv - pack_kg
    parts = [("Катанка", rod), ("Передел", conv), ("Упаковка", pack_kg),
             ("Остаток: сбыт, накладные, прибыль", rest)]
    return dict(wire=wire, parts=[(n, v, v / wire * 100) for n, v in parts], rest=rest)
