from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from math import ceil, cos, radians

D = Decimal

def dec(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))

def money(value) -> Decimal:
    return dec(value).quantize(D("0.01"), rounding=ROUND_HALF_UP)

def gross_from_net(net, vat_rate) -> Decimal:
    return money(dec(net) * (D("1") + dec(vat_rate) / D("100")))

def net_from_gross(gross, vat_rate) -> Decimal:
    return money(dec(gross) / (D("1") + dec(vat_rate) / D("100")))

def vat_amount_from_net(net, vat_rate) -> Decimal:
    return money(gross_from_net(net, vat_rate) - money(net))

def with_waste(quantity, waste_percent) -> Decimal:
    return dec(quantity) * (D("1") + dec(waste_percent) / D("100"))

def packages_required(required_quantity, package_quantity) -> int:
    rq = dec(required_quantity)
    pq = dec(package_quantity)
    if rq < 0:
        raise ValueError("Cantitatea necesară nu poate fi negativă.")
    if pq <= 0:
        raise ValueError("Cantitatea per pachet trebuie să fie > 0.")
    return int((rq / pq).to_integral_value(rounding="ROUND_CEILING"))

def steel_kg_per_m(diameter_mm) -> Decimal:
    d = dec(diameter_mm)
    if d <= 0:
        raise ValueError("Diametrul trebuie să fie > 0.")
    return d * d / D("162")

def steel_total_kg(diameter_mm, bar_length_m, quantity, waste_percent=0) -> Decimal:
    base = steel_kg_per_m(diameter_mm) * dec(bar_length_m) * dec(quantity)
    return with_waste(base, waste_percent)

@dataclass(frozen=True)
class RoomGeometry:
    floor_area_m2: Decimal
    ceiling_area_m2: Decimal
    perimeter_m: Decimal
    wall_gross_m2: Decimal
    openings_m2: Decimal
    wall_net_m2: Decimal

def room_geometry(length_m, width_m, height_m, openings_m2=0) -> RoomGeometry:
    l, w, h, o = map(dec, (length_m, width_m, height_m, openings_m2))
    if min(l, w, h) <= 0 or o < 0:
        raise ValueError("Dimensiuni cameră invalide.")
    floor = l * w
    perimeter = D("2") * (l + w)
    gross = perimeter * h
    net = gross - o
    if net < 0:
        raise ValueError("Suprafața golurilor depășește suprafața pereților.")
    return RoomGeometry(floor, floor, perimeter, gross, o, net)

def roof_sloped_area(projected_area_m2, pitch_degrees) -> Decimal:
    area = dec(projected_area_m2)
    pitch = float(dec(pitch_degrees))
    if area < 0 or not (0 <= pitch < 90):
        raise ValueError("Date acoperiș invalide.")
    return area / dec(cos(radians(pitch)))

def concrete_volume(length_m, width_m, height_m, quantity=1) -> Decimal:
    vals = list(map(dec, (length_m, width_m, height_m, quantity)))
    if any(v < 0 for v in vals):
        raise ValueError("Dimensiunile nu pot fi negative.")
    return vals[0] * vals[1] * vals[2] * vals[3]

def stirrup_count(member_length_m, spacing_mm) -> int:
    length = dec(member_length_m)
    spacing_m = dec(spacing_mm) / D("1000")
    if length <= 0 or spacing_m <= 0:
        raise ValueError("Lungimea și pasul trebuie să fie > 0.")
    return ceil(float(length / spacing_m)) + 1

@dataclass(frozen=True)
class SupplierBasket:
    supplier: str
    material_cost: Decimal
    delivery_cost: Decimal
    complete: bool = True

    @property
    def landed_cost(self) -> Decimal:
        return money(self.material_cost + self.delivery_cost)

def cheapest_complete_supplier(baskets: list[SupplierBasket]) -> SupplierBasket | None:
    candidates = [b for b in baskets if b.complete]
    return min(candidates, key=lambda b: b.landed_cost) if candidates else None

def mixed_landed_cost(material_lines: list[tuple[str, Decimal]], delivery_by_supplier: dict[str, Decimal]) -> Decimal:
    used = {supplier for supplier, _ in material_lines}
    material_total = sum((dec(cost) for _, cost in material_lines), D("0"))
    delivery_total = sum((dec(delivery_by_supplier.get(s, 0)) for s in used), D("0"))
    return money(material_total + delivery_total)
