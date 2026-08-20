from __future__ import annotations
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

Unit = Literal["buc", "ml", "m2", "m3", "kg", "tona", "ora", "set", "sac", "palet"]
ResourceType = Literal["MATERIAL", "LABOR", "EQUIPMENT", "OTHER"]

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
    notes: str | None = Field(default=None, max_length=2000)
    unit: Unit
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

class MaterialIn(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=160)
    base_unit: Unit
    description: str | None = None
    attributes: dict = Field(default_factory=dict)
    active: bool = True

class MaterialOut(MaterialIn):
    id: int
    model_config = ConfigDict(from_attributes=True)

class PricedResourceIn(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=255)
    unit: Unit
    rate_net: Decimal = Field(ge=0)
    vat_rate: Decimal = Field(default=Decimal("21"), ge=0, le=100)
    active: bool = True

class PricedResourceOut(PricedResourceIn):
    id: int
    rate_gross: Decimal
    model_config = ConfigDict(from_attributes=True)

class WorkItemIn(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    unit: Unit
    active: bool = True

class WorkItemOut(WorkItemIn):
    id: int
    model_config = ConfigDict(from_attributes=True)

class RecipeIn(BaseModel):
    work_item_id: int
    scope: Literal["STANDARD", "COMPANY_OVERRIDE", "PROJECT_OVERRIDE"] = "STANDARD"
    project_id: int | None = None
    version: int = Field(default=1, ge=1)

class RecipeOut(RecipeIn):
    id: int
    model_config = ConfigDict(from_attributes=True)

class RecipeResourceIn(BaseModel):
    resource_type: ResourceType
    resource_id: int
    quantity_per_unit: Decimal = Field(gt=0)
    waste_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    unit: Unit
    notes: str | None = None

class RecipeResourceOut(RecipeResourceIn):
    id: int
    recipe_id: int
    description: str
    model_config = ConfigDict(from_attributes=True)

class ProjectPriceIn(BaseModel):
    resource_type: ResourceType
    resource_id: int
    unit_price_net: Decimal = Field(ge=0)
    vat_rate: Decimal = Field(default=Decimal("21"), ge=0, le=100)

class ProjectPriceOut(ProjectPriceIn):
    id: int
    project_id: int
    unit_price_gross: Decimal
    model_config = ConfigDict(from_attributes=True)

class ManualResourceLineIn(BaseModel):
    resource_type: ResourceType
    resource_id: int | None = None
    description: str = Field(min_length=1, max_length=255)
    unit: Unit
    quantity: Decimal = Field(gt=0)
    waste_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    unit_price_net: Decimal = Field(ge=0)
    vat_rate: Decimal = Field(default=Decimal("21"), ge=0, le=100)
    notes: str | None = None

GeometryType = Literal["ROOM", "WALL", "FOUNDATION_STRIP", "SLAB", "BEAM", "COLUMN", "ROOF_GABLE", "REBAR", "STIRRUPS", "WELDED_MESH"]

class GeometryCalculationIn(BaseModel):
    estimate_item_id: int | None = None
    parent_calculation_id: int | None = None
    geometry_type: GeometryType
    name: str = Field(min_length=1, max_length=255)
    input_data: dict
    selected_result: str = Field(min_length=1, max_length=80)
    waste_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    notes: str | None = None

class GeometryLinkIn(BaseModel):
    estimate_item_id: int
    result_key: str = Field(min_length=1, max_length=80)
    waste_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)

class GeometryCreateItemIn(BaseModel):
    section_id: int
    result_key: str
    code: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=255)
    work_item_id: int | None = None
    waste_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)

class MeshCatalogueIn(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=255)
    wire_diameter_mm: Decimal = Field(gt=0)
    spacing_x_mm: Decimal = Field(gt=0)
    spacing_y_mm: Decimal = Field(gt=0)
    sheet_length_m: Decimal = Field(gt=0)
    sheet_width_m: Decimal = Field(gt=0)
    weight_kg_per_sheet: Decimal = Field(gt=0)
    active: bool = True
