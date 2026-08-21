from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

D = Decimal
UNITS = ("buc", "ml", "m2", "m3", "kg", "tona", "ora", "set", "sac", "palet", "l")
RESOURCE_TYPES = ("MATERIAL", "LABOR", "EQUIPMENT", "OTHER")

def dec(value) -> Decimal:
    return value if isinstance(value, Decimal) else D(str(value))

def q6(value) -> Decimal:
    return dec(value).quantize(D("0.000001"), rounding=ROUND_HALF_UP)

def q4(value) -> Decimal:
    return dec(value).quantize(D("0.0001"), rounding=ROUND_HALF_UP)

def money(value) -> Decimal:
    return dec(value).quantize(D("0.01"), rounding=ROUND_HALF_UP)

def gross_from_net_exact(net, vat_rate) -> Decimal:
    return q4(dec(net) * (D("1") + dec(vat_rate) / D("100")))

def net_from_gross_exact(gross, vat_rate) -> Decimal:
    return q4(dec(gross) / (D("1") + dec(vat_rate) / D("100")))

def recipe_quantity(item_quantity, quantity_per_unit, waste_percent) -> Decimal:
    return q6(dec(item_quantity) * dec(quantity_per_unit) * (D("1") + dec(waste_percent) / D("100")))

def convert_unit(quantity, from_unit: str, to_unit: str) -> Decimal:
    if from_unit not in UNITS or to_unit not in UNITS:
        raise ValueError("Unitate necunoscută.")
    value = dec(quantity)
    if from_unit == to_unit:
        return q6(value)
    if from_unit == "tona" and to_unit == "kg":
        return q6(value * D("1000"))
    if from_unit == "kg" and to_unit == "tona":
        return q6(value / D("1000"))
    raise ValueError(f"Conversia {from_unit} → {to_unit} nu este compatibilă.")

@dataclass(frozen=True)
class CostResult:
    quantity: Decimal
    unit_price_net: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    unit_price_gross: Decimal
    subtotal_net: Decimal
    subtotal_gross: Decimal

def calculate_cost(quantity, unit_price_net, vat_rate) -> CostResult:
    qty, net, vat = q6(quantity), q4(unit_price_net), dec(vat_rate)
    gross = gross_from_net_exact(net, vat)
    subtotal_net = money(qty * net)
    subtotal_gross = money(qty * gross)
    return CostResult(qty, net, vat, money(subtotal_gross - subtotal_net), gross, subtotal_net, subtotal_gross)

def aggregate_totals(lines: list[dict]) -> dict[str, Decimal]:
    totals = {key: D("0.00") for key in (*RESOURCE_TYPES, "TRANSPORT", "total_net", "vat", "total_gross")}
    for line in lines:
        kind = line["resource_type"]
        net, gross = money(line["subtotal_net"]), money(line["subtotal_gross"])
        totals[kind] = money(totals.get(kind, D("0")) + gross)
        totals["total_net"] = money(totals["total_net"] + net)
        totals["total_gross"] = money(totals["total_gross"] + gross)
    totals["vat"] = money(totals["total_gross"] - totals["total_net"])
    return totals
