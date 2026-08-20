from decimal import Decimal
import pytest
from app.calc import (
    gross_from_net, net_from_gross, with_waste, packages_required,
    steel_kg_per_m, steel_total_kg, room_geometry, roof_sloped_area,
    concrete_volume, stirrup_count, SupplierBasket, cheapest_complete_supplier,
    mixed_landed_cost
)

def test_vat_roundtrip():
    gross = gross_from_net("100.00", "21")
    assert gross == Decimal("121.00")
    assert net_from_gross(gross, "21") == Decimal("100.00")

def test_packages_with_waste():
    required = with_waste("83", "5")
    assert required == Decimal("87.15")
    assert packages_required(required, "5.5") == 16

def test_steel_mass():
    per_m = steel_kg_per_m("12")
    assert per_m.quantize(Decimal("0.001")) == Decimal("0.889")
    total = steel_total_kg("12", "6", "10", "5")
    assert total > Decimal("55")

def test_room_geometry():
    g = room_geometry("4", "3.5", "2.7", "4.59")
    assert g.floor_area_m2 == Decimal("14.0")
    assert g.wall_gross_m2 == Decimal("40.50")
    assert g.wall_net_m2 == Decimal("35.91")

def test_roof_area():
    area = roof_sloped_area("100", "30")
    assert area.quantize(Decimal("0.01")) == Decimal("115.47")

def test_concrete_and_stirrups():
    assert concrete_volume("48", ".5", ".8") == Decimal("19.20")
    assert stirrup_count("6", "150") == 41

def test_supplier_complete_basket():
    baskets = [
        SupplierBasket("Dedeman", Decimal("1000"), Decimal("300")),
        SupplierBasket("MatHaus", Decimal("1050"), Decimal("100")),
        SupplierBasket("Hornbach", Decimal("900"), Decimal("500"), complete=False),
    ]
    winner = cheapest_complete_supplier(baskets)
    assert winner.supplier == "MatHaus"
    assert winner.landed_cost == Decimal("1150.00")

def test_mixed_landed_cost_charges_delivery_once():
    total = mixed_landed_cost(
        [("Dedeman", Decimal("100")), ("Dedeman", Decimal("200")), ("MatHaus", Decimal("50"))],
        {"Dedeman": Decimal("30"), "MatHaus": Decimal("20")}
    )
    assert total == Decimal("400.00")

def test_invalid_package():
    with pytest.raises(ValueError):
        packages_required("10", "0")
