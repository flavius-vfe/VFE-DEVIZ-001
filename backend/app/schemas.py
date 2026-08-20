from __future__ import annotations
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict

class SetupStatusOut(BaseModel):
    configured: bool

class SetupIn(BaseModel):
    username: str = Field(default="administrator", min_length=3, max_length=100)
    password: str = Field(min_length=10, max_length=200)
    server_ip: str
    locality: str = "Ceahlău"
    county: str = "Neamț"
    currency: str = Field(default="RON", pattern="^RON$")
    vat_rate: Decimal = Field(default=Decimal("21"), ge=0, le=100)

class LoginIn(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    id: int
    username: str
    model_config = ConfigDict(from_attributes=True)

class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    client: str | None = None
    delivery_address: str | None = None
    locality: str = "Ceahlău"
    county: str = "Neamț"
    postal_code: str | None = None
    default_waste_percent: Decimal = Field(default=Decimal("5"), ge=0, le=100)

class ProjectOut(ProjectIn):
    id: int
    active: bool
    model_config = ConfigDict(from_attributes=True)

class BuildingIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    sort_order: int = 0

class BuildingOut(BuildingIn):
    id: int
    project_id: int
    model_config = ConfigDict(from_attributes=True)

class LevelIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    elevation_m: Decimal | None = None
    sort_order: int = 0

class LevelOut(LevelIn):
    id: int
    building_id: int
    model_config = ConfigDict(from_attributes=True)

class SectionIn(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    parent_section_id: int | None = None
    sort_order: int = 0

class SectionOut(SectionIn):
    id: int
    level_id: int
    model_config = ConfigDict(from_attributes=True)

class EstimateItemIn(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=255)
    unit: str = Field(min_length=1, max_length=20)
    quantity: Decimal = Field(gt=0)
    work_item_id: int | None = None
    calculation_type: str = Field(default="MANUAL", max_length=30)
    calculation_inputs: dict = Field(default_factory=dict)
    waste_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    sort_order: int = 0

class EstimateItemOut(EstimateItemIn):
    id: int
    section_id: int
    model_config = ConfigDict(from_attributes=True)

class VatCalcIn(BaseModel):
    amount: Decimal = Field(ge=0)
    vat_rate: Decimal = Field(default=Decimal("21"), ge=0, le=100)
    amount_includes_vat: bool = False

class PackageCalcIn(BaseModel):
    required_quantity: Decimal = Field(ge=0)
    waste_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    package_quantity: Decimal = Field(gt=0)
    package_price_gross: Decimal = Field(ge=0)

class RoomCalcIn(BaseModel):
    length_m: Decimal = Field(gt=0)
    width_m: Decimal = Field(gt=0)
    height_m: Decimal = Field(gt=0)
    openings_m2: Decimal = Field(default=Decimal("0"), ge=0)

class SteelCalcIn(BaseModel):
    diameter_mm: Decimal = Field(gt=0)
    bar_length_m: Decimal = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    waste_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
