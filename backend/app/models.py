from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    String, Boolean, DateTime, ForeignKey, Numeric, Integer, Text, JSON,
    UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user: Mapped[User] = relationship()

class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client: Mapped[str | None] = mapped_column(String(255))
    delivery_address: Mapped[str | None] = mapped_column(Text)
    delivery_locality: Mapped[str] = mapped_column(String(120), default="Ceahlău", nullable=False)
    delivery_county: Mapped[str] = mapped_column(String(120), default="Neamț", nullable=False)
    delivery_country: Mapped[str] = mapped_column(String(80), default="România", nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    locality: Mapped[str] = mapped_column(String(120), default="Ceahlău", nullable=False)
    county: Mapped[str] = mapped_column(String(120), default="Neamț", nullable=False)
    postal_code: Mapped[str | None] = mapped_column(String(20))
    default_waste_percent: Mapped[Decimal] = mapped_column(Numeric(7, 3), default=Decimal("5.000"), nullable=False)
    preferred_supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    material_price_strategy: Mapped[str] = mapped_column(String(40), default="MANUAL", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Building(Base):
    __tablename__ = "project_buildings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

class Level(Base):
    __tablename__ = "project_levels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("project_buildings.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    elevation_m: Mapped[Decimal | None] = mapped_column(Numeric(9,3))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

class EstimateSection(Base):
    __tablename__ = "estimate_sections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level_id: Mapped[int] = mapped_column(ForeignKey("project_levels.id", ondelete="CASCADE"), nullable=False)
    parent_section_id: Mapped[int | None] = mapped_column(ForeignKey("estimate_sections.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

class Material(Base):
    __tablename__ = "materials"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(160), nullable=False)
    base_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class LaborResource(Base):
    __tablename__ = "labor_resources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    rate_net: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False, default=Decimal("21"))
    rate_gross: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class EquipmentResource(Base):
    __tablename__ = "equipment_resources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    rate_net: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False, default=Decimal("21"))
    rate_gross: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class OtherResource(Base):
    __tablename__ = "other_resources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    rate_net: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False, default=Decimal("21"))
    rate_gross: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class WorkCategory(Base):
    __tablename__ = "work_categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

class WorkItem(Base):
    __tablename__ = "work_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class WorkRecipe(Base):
    __tablename__ = "work_recipes"
    __table_args__ = (UniqueConstraint("work_item_id", "version", name="uq_recipe_version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_item_id: Mapped[int] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    scope: Mapped[str] = mapped_column(String(30), default="STANDARD", nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class RecipeResource(Base):
    __tablename__ = "recipe_resources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("work_recipes.id", ondelete="CASCADE"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False)
    resource_id: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity_per_unit: Mapped[Decimal] = mapped_column(Numeric(18,6), nullable=False)
    waste_percent: Mapped[Decimal] = mapped_column(Numeric(7,3), default=Decimal("0"))
    formula: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

class EstimateItem(Base):
    __tablename__ = "estimate_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("estimate_sections.id", ondelete="CASCADE"), nullable=False)
    work_item_id: Mapped[int | None] = mapped_column(ForeignKey("work_items.id"))
    pinned_recipe_id: Mapped[int | None] = mapped_column(ForeignKey("work_recipes.id", ondelete="SET NULL"))
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18,6), nullable=False)
    calculation_type: Mapped[str] = mapped_column(String(30), default="MANUAL", nullable=False)
    calculation_inputs: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    waste_percent: Mapped[Decimal] = mapped_column(Numeric(7,3), default=Decimal("0"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

class ProjectResourcePrice(Base):
    __tablename__ = "project_resource_prices"
    __table_args__ = (UniqueConstraint("project_id", "resource_type", "resource_id", name="uq_project_resource_price"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False)
    resource_id: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_net: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False)
    unit_price_gross: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

class EstimateResourceLine(Base):
    __tablename__ = "estimate_resource_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    estimate_item_id: Mapped[int] = mapped_column(ForeignKey("estimate_items.id", ondelete="CASCADE"), nullable=False)
    recipe_resource_id: Mapped[int | None] = mapped_column(ForeignKey("recipe_resources.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="MANUAL")
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False)
    resource_id: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    waste_percent: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False, default=Decimal("0"))
    unit_price_net: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False)
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    unit_price_gross: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    subtotal_net: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    subtotal_gross: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

class GeometryCalculation(Base):
    __tablename__ = "geometry_calculations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    estimate_item_id: Mapped[int | None] = mapped_column(ForeignKey("estimate_items.id", ondelete="SET NULL"))
    parent_calculation_id: Mapped[int | None] = mapped_column(ForeignKey("geometry_calculations.id", ondelete="SET NULL"))
    geometry_type: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    input_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    results: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    selected_result: Mapped[str] = mapped_column(String(80), nullable=False)
    calculated_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    calculated_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    waste_percent: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False, default=Decimal("0"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

class GeometryEstimateLink(Base):
    __tablename__ = "geometry_estimate_links"
    __table_args__ = (UniqueConstraint("geometry_calculation_id", "estimate_item_id", "result_key", name="uq_geometry_item_result"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    geometry_calculation_id: Mapped[int] = mapped_column(ForeignKey("geometry_calculations.id", ondelete="CASCADE"), nullable=False)
    estimate_item_id: Mapped[int] = mapped_column(ForeignKey("estimate_items.id", ondelete="CASCADE"), nullable=False)
    result_key: Mapped[str] = mapped_column(String(80), nullable=False)
    waste_percent: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False, default=Decimal("0"))

class MeshCatalogueItem(Base):
    __tablename__ = "mesh_catalogue_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    wire_diameter_mm: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    spacing_x_mm: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    spacing_y_mm: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    sheet_length_m: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    sheet_width_m: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    sheet_area_m2: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    weight_kg_per_sheet: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (Index("ix_suppliers_code_unique", "code", unique=True),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="RETAILER")
    website: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(60))
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)
    locality: Mapped[str | None] = mapped_column(String(160))
    county: Mapped[str | None] = mapped_column(String(160))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    requests_per_minute: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    request_timeout: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    backoff_seconds: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parse_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manual_imports: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

class SupplierLocation(Base):
    __tablename__ = "supplier_locations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    locality: Mapped[str | None] = mapped_column(String(160))
    county: Mapped[str | None] = mapped_column(String(160))
    address: Mapped[str | None] = mapped_column(Text)
    preferred: Mapped[bool] = mapped_column(Boolean, default=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

class SupplierProduct(Base):
    __tablename__ = "supplier_products"
    __table_args__ = (UniqueConstraint("supplier_id", "supplier_sku", name="uq_supplier_sku"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False)
    supplier_location_id: Mapped[int | None] = mapped_column(ForeignKey("supplier_locations.id"))
    supplier_sku: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(200))
    product_url: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text)
    package_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18,6))
    package_unit: Mapped[str | None] = mapped_column(String(20))
    normalized_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18,6))
    normalized_unit: Mapped[str | None] = mapped_column(String(20))
    minimum_order_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    minimum_package_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    whole_pallet_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class ProductMatch(Base):
    __tablename__ = "material_product_matches"
    __table_args__ = (UniqueConstraint("material_id", "supplier_product_id", name="uq_material_product_match"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), nullable=False)
    supplier_product_id: Mapped[int] = mapped_column(ForeignKey("supplier_products.id", ondelete="CASCADE"), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5,4), nullable=False)
    match_status: Mapped[str] = mapped_column(String(20), default="AUTO", nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

class PriceObservation(Base):
    __tablename__ = "price_observations"
    __table_args__ = (Index("ix_price_product_checked", "supplier_product_id", "checked_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_product_id: Mapped[int] = mapped_column(ForeignKey("supplier_products.id", ondelete="CASCADE"), nullable=False)
    supplier_location_id: Mapped[int | None] = mapped_column(ForeignKey("supplier_locations.id"))
    price_net: Mapped[Decimal | None] = mapped_column(Numeric(18,4))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(7,3), default=Decimal("21"))
    vat_amount: Mapped[Decimal | None] = mapped_column(Numeric(18,4))
    price_gross: Mapped[Decimal] = mapped_column(Numeric(18,4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="RON", nullable=False)
    stock_status: Mapped[str] = mapped_column(String(40), default="UNKNOWN", nullable=False)
    stock_text: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(40), default="WEB", nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str | None] = mapped_column(Text)

class SupplierRefreshJob(Base):
    __tablename__ = "supplier_refresh_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False)
    supplier_product_id: Mapped[int | None] = mapped_column(ForeignKey("supplier_products.id", ondelete="CASCADE"))
    job_type: Mapped[str] = mapped_column(String(40), nullable=False, default="PRODUCT")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

class DeliveryQuote(Base):
    __tablename__ = "delivery_quotes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False)
    supplier_location_id: Mapped[int | None] = mapped_column(ForeignKey("supplier_locations.id"))
    destination_address: Mapped[str | None] = mapped_column(Text)
    destination_locality: Mapped[str] = mapped_column(String(160), default="Ceahlău", nullable=False)
    destination_county: Mapped[str] = mapped_column(String(160), default="Neamț", nullable=False)
    basket_subtotal_gross: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    basket_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(18, 3))
    pallet_count: Mapped[Decimal | None] = mapped_column(Numeric(18, 3))
    delivery_cost_gross: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="RON", nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(20), default="MANUAL", nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

class SupplierDeliveryRule(Base):
    __tablename__ = "supplier_delivery_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, unique=True)
    minimum_order_gross: Mapped[Decimal | None] = mapped_column(Numeric(18,2))
    fixed_delivery_cost: Mapped[Decimal | None] = mapped_column(Numeric(18,2))
    free_delivery_threshold: Mapped[Decimal | None] = mapped_column(Numeric(18,2))
    cost_per_km: Mapped[Decimal | None] = mapped_column(Numeric(18,4))
    cost_per_pallet: Mapped[Decimal | None] = mapped_column(Numeric(18,4))
    cost_per_kg: Mapped[Decimal | None] = mapped_column(Numeric(18,4))
    minimum_delivery_cost: Mapped[Decimal | None] = mapped_column(Numeric(18,2))
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

class ProcurementPlan(Base):
    __tablename__ = "procurement_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    estimate_version_id: Mapped[int | None] = mapped_column(ForeignKey("estimate_versions.id"))
    strategy: Mapped[str] = mapped_column(String(40), nullable=False)
    preferred_supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)
    include_unknown_delivery: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

class ProcurementPlanItem(Base):
    __tablename__ = "procurement_plan_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    procurement_plan_id: Mapped[int] = mapped_column(ForeignKey("procurement_plans.id", ondelete="CASCADE"), nullable=False)
    estimate_resource_id: Mapped[int] = mapped_column(ForeignKey("estimate_resource_lines.id"), nullable=False)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    supplier_product_id: Mapped[int | None] = mapped_column(ForeignKey("supplier_products.id"))
    quote_item_id: Mapped[int | None] = mapped_column(ForeignKey("supplier_quote_items.id"))
    required_quantity: Mapped[Decimal] = mapped_column(Numeric(18,6), nullable=False)
    required_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    package_quantity: Mapped[Decimal] = mapped_column(Numeric(18,6), nullable=False)
    package_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    packages_to_buy: Mapped[int] = mapped_column(Integer, nullable=False)
    purchased_quantity: Mapped[Decimal] = mapped_column(Numeric(18,6), nullable=False)
    unused_quantity: Mapped[Decimal] = mapped_column(Numeric(18,6), nullable=False)
    unit_package_price_gross: Mapped[Decimal] = mapped_column(Numeric(18,4), nullable=False)
    product_subtotal_gross: Mapped[Decimal] = mapped_column(Numeric(18,2), nullable=False)
    price_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stock_status: Mapped[str] = mapped_column(String(40), nullable=False)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supplier_name: Mapped[str] = mapped_column(String(160), nullable=False)
    supplier_sku: Mapped[str] = mapped_column(String(120), nullable=False)
    product_name: Mapped[str] = mapped_column(String(500), nullable=False)
    product_url: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    procurement_status: Mapped[str] = mapped_column(String(30), default="NOT_ORDERED", nullable=False)

class ProcurementPlanSupplierTotal(Base):
    __tablename__ = "procurement_plan_supplier_totals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    procurement_plan_id: Mapped[int] = mapped_column(ForeignKey("procurement_plans.id", ondelete="CASCADE"), nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    product_count: Mapped[int] = mapped_column(Integer, nullable=False)
    subtotal_gross: Mapped[Decimal] = mapped_column(Numeric(18,2), nullable=False)
    delivery_cost_gross: Mapped[Decimal | None] = mapped_column(Numeric(18,2))
    delivery_source: Mapped[str] = mapped_column(String(20), nullable=False, default="UNKNOWN")
    landed_total_gross: Mapped[Decimal | None] = mapped_column(Numeric(18,2))

class EstimateVersion(Base):
    __tablename__ = "estimate_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(7,3), default=Decimal("21"), nullable=False)
    total_net: Mapped[Decimal] = mapped_column(Numeric(18,2), default=Decimal("0"))
    vat_total: Mapped[Decimal] = mapped_column(Numeric(18,2), default=Decimal("0"))
    total_gross: Mapped[Decimal] = mapped_column(Numeric(18,2), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class EstimateSnapshotLine(Base):
    __tablename__ = "estimate_snapshot_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    estimate_version_id: Mapped[int] = mapped_column(ForeignKey("estimate_versions.id", ondelete="CASCADE"), nullable=False)
    source_item_id: Mapped[int | None] = mapped_column(Integer)
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18,6), nullable=False)
    unit_price_net: Mapped[Decimal] = mapped_column(Numeric(18,4), default=Decimal("0"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(7,3), default=Decimal("21"))
    unit_price_gross: Mapped[Decimal] = mapped_column(Numeric(18,4), default=Decimal("0"))
    total_gross: Mapped[Decimal] = mapped_column(Numeric(18,2), default=Decimal("0"))
    supplier_name: Mapped[str | None] = mapped_column(String(160))
    supplier_sku: Mapped[str | None] = mapped_column(String(120))
    product_url: Mapped[str | None] = mapped_column(Text)
    price_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supplier_product_id: Mapped[int | None] = mapped_column(Integer)
    product_name: Mapped[str | None] = mapped_column(String(500))
    package_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    package_unit: Mapped[str | None] = mapped_column(String(20))
    purchase_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    packages_to_buy: Mapped[int | None] = mapped_column(Integer)

class SupplierQuote(Base):
    __tablename__="supplier_quotes"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    supplier_id:Mapped[int]=mapped_column(ForeignKey("suppliers.id"),nullable=False)
    project_id:Mapped[int]=mapped_column(ForeignKey("projects.id",ondelete="CASCADE"),nullable=False)
    quote_number:Mapped[str|None]=mapped_column(String(120)); quote_date:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    valid_until:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); currency:Mapped[str]=mapped_column(String(3),default="RON",nullable=False)
    status:Mapped[str]=mapped_column(String(30),default="DRAFT",nullable=False)
    subtotal_net:Mapped[Decimal]=mapped_column(Numeric(18,2),default=Decimal("0"),nullable=False)
    discount_total_net:Mapped[Decimal]=mapped_column(Numeric(18,2),default=Decimal("0"),nullable=False)
    transport_net:Mapped[Decimal]=mapped_column(Numeric(18,2),default=Decimal("0"),nullable=False)
    pump_fixed_cost:Mapped[Decimal]=mapped_column(Numeric(18,2),default=Decimal("0"),nullable=False)
    pump_hourly_cost:Mapped[Decimal]=mapped_column(Numeric(18,2),default=Decimal("0"),nullable=False)
    pump_hours:Mapped[Decimal]=mapped_column(Numeric(10,2),default=Decimal("0"),nullable=False)
    waiting_cost:Mapped[Decimal]=mapped_column(Numeric(18,2),default=Decimal("0"),nullable=False)
    other_cost:Mapped[Decimal]=mapped_column(Numeric(18,2),default=Decimal("0"),nullable=False)
    vat_total:Mapped[Decimal]=mapped_column(Numeric(18,2),default=Decimal("0"),nullable=False); total_gross:Mapped[Decimal]=mapped_column(Numeric(18,2),default=Decimal("0"),nullable=False)
    notes:Mapped[str|None]=mapped_column(Text); conditions:Mapped[dict]=mapped_column(JSON,default=dict,nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,nullable=False); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow,nullable=False)

class SupplierQuoteItem(Base):
    __tablename__="supplier_quote_items"
    id:Mapped[int]=mapped_column(Integer,primary_key=True); quote_id:Mapped[int]=mapped_column(ForeignKey("supplier_quotes.id",ondelete="CASCADE"),nullable=False)
    material_id:Mapped[int|None]=mapped_column(ForeignKey("materials.id")); supplier_product_id:Mapped[int|None]=mapped_column(ForeignKey("supplier_products.id"))
    description:Mapped[str]=mapped_column(String(500),nullable=False); supplier_sku:Mapped[str|None]=mapped_column(String(120)); unit:Mapped[str]=mapped_column(String(20),nullable=False)
    quantity:Mapped[Decimal]=mapped_column(Numeric(18,6),nullable=False); unit_price_net:Mapped[Decimal]=mapped_column(Numeric(18,4),nullable=False); vat_rate:Mapped[Decimal]=mapped_column(Numeric(7,3),nullable=False)
    unit_price_gross:Mapped[Decimal]=mapped_column(Numeric(18,4),nullable=False); line_discount_type:Mapped[str|None]=mapped_column(String(30)); line_discount_value:Mapped[Decimal|None]=mapped_column(Numeric(18,4))
    line_total_net:Mapped[Decimal]=mapped_column(Numeric(18,2),nullable=False); line_vat:Mapped[Decimal]=mapped_column(Numeric(18,2),nullable=False); line_total_gross:Mapped[Decimal]=mapped_column(Numeric(18,2),nullable=False)
    attributes:Mapped[dict]=mapped_column(JSON,default=dict,nullable=False); notes:Mapped[str|None]=mapped_column(Text)

class Discount(Base):
    __tablename__="discounts"
    id:Mapped[int]=mapped_column(Integer,primary_key=True); scope_type:Mapped[str]=mapped_column(String(30),nullable=False); scope_id:Mapped[int]=mapped_column(Integer,nullable=False)
    discount_type:Mapped[str]=mapped_column(String(40),nullable=False); value:Mapped[Decimal]=mapped_column(Numeric(18,4),nullable=False); description:Mapped[str|None]=mapped_column(Text)
    valid_from:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); valid_until:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); conditions:Mapped[dict|None]=mapped_column(JSON); active:Mapped[bool]=mapped_column(Boolean,default=True,nullable=False)

class Attachment(Base):
    __tablename__="attachments"
    id:Mapped[int]=mapped_column(Integer,primary_key=True); project_id:Mapped[int]=mapped_column(ForeignKey("projects.id",ondelete="CASCADE"),nullable=False)
    entity_type:Mapped[str]=mapped_column(String(50),nullable=False); entity_id:Mapped[int]=mapped_column(Integer,nullable=False); original_filename:Mapped[str]=mapped_column(String(255),nullable=False); stored_filename:Mapped[str]=mapped_column(String(255),nullable=False)
    mime_type:Mapped[str]=mapped_column(String(120),nullable=False); file_size:Mapped[int]=mapped_column(Integer,nullable=False); relative_path:Mapped[str]=mapped_column(Text,nullable=False); uploaded_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,nullable=False); description:Mapped[str|None]=mapped_column(Text)

class PurchaseOrder(Base):
    __tablename__="purchase_orders"; __table_args__=(UniqueConstraint("order_number",name="uq_purchase_order_number"),)
    id:Mapped[int]=mapped_column(Integer,primary_key=True); project_id:Mapped[int]=mapped_column(ForeignKey("projects.id",ondelete="CASCADE"),nullable=False); supplier_id:Mapped[int]=mapped_column(ForeignKey("suppliers.id"),nullable=False)
    supplier_quote_id:Mapped[int|None]=mapped_column(ForeignKey("supplier_quotes.id")); procurement_plan_id:Mapped[int|None]=mapped_column(ForeignKey("procurement_plans.id")); order_number:Mapped[str]=mapped_column(String(50),nullable=False)
    status:Mapped[str]=mapped_column(String(30),default="DRAFT",nullable=False); delivery_address:Mapped[str]=mapped_column(Text,nullable=False); requested_delivery_date:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    subtotal_net:Mapped[Decimal]=mapped_column(Numeric(18,2),nullable=False); discount_total:Mapped[Decimal]=mapped_column(Numeric(18,2),nullable=False); transport_cost:Mapped[Decimal]=mapped_column(Numeric(18,2),nullable=False); vat_total:Mapped[Decimal]=mapped_column(Numeric(18,2),nullable=False); total_gross:Mapped[Decimal]=mapped_column(Numeric(18,2),nullable=False)
    notes:Mapped[str|None]=mapped_column(Text); revision_of_id:Mapped[int|None]=mapped_column(ForeignKey("purchase_orders.id")); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,nullable=False); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow,nullable=False)

class PurchaseOrderItem(Base):
    __tablename__="purchase_order_items"
    id:Mapped[int]=mapped_column(Integer,primary_key=True); purchase_order_id:Mapped[int]=mapped_column(ForeignKey("purchase_orders.id",ondelete="CASCADE"),nullable=False); estimate_resource_id:Mapped[int|None]=mapped_column(ForeignKey("estimate_resource_lines.id")); material_id:Mapped[int|None]=mapped_column(ForeignKey("materials.id")); supplier_product_id:Mapped[int|None]=mapped_column(ForeignKey("supplier_products.id")); quote_item_id:Mapped[int|None]=mapped_column(ForeignKey("supplier_quote_items.id"))
    description:Mapped[str]=mapped_column(String(500),nullable=False); sku:Mapped[str|None]=mapped_column(String(120)); unit:Mapped[str]=mapped_column(String(20),nullable=False); quantity:Mapped[Decimal]=mapped_column(Numeric(18,6),nullable=False); package_quantity:Mapped[Decimal|None]=mapped_column(Numeric(18,6)); package_count:Mapped[int|None]=mapped_column(Integer)
    unit_price_net:Mapped[Decimal]=mapped_column(Numeric(18,4),nullable=False); vat_rate:Mapped[Decimal]=mapped_column(Numeric(7,3),nullable=False); unit_price_gross:Mapped[Decimal]=mapped_column(Numeric(18,4),nullable=False); discount_net:Mapped[Decimal]=mapped_column(Numeric(18,2),nullable=False); line_total_net:Mapped[Decimal]=mapped_column(Numeric(18,2),nullable=False); line_vat:Mapped[Decimal]=mapped_column(Numeric(18,2),nullable=False); line_total_gross:Mapped[Decimal]=mapped_column(Numeric(18,2),nullable=False); notes:Mapped[str|None]=mapped_column(Text)

class PurchaseOrderSequence(Base):
    __tablename__="purchase_order_sequences"; year:Mapped[int]=mapped_column(Integer,primary_key=True); value:Mapped[int]=mapped_column(Integer,nullable=False,default=0)

class AuditEvent(Base):
    __tablename__="audit_events"; id:Mapped[int]=mapped_column(Integer,primary_key=True); entity_type:Mapped[str]=mapped_column(String(50),nullable=False); entity_id:Mapped[int]=mapped_column(Integer,nullable=False); action:Mapped[str]=mapped_column(String(80),nullable=False); details:Mapped[dict]=mapped_column(JSON,default=dict,nullable=False); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)

class PurchaseDelivery(Base):
    __tablename__="purchase_deliveries"
    id:Mapped[int]=mapped_column(Integer,primary_key=True); project_id:Mapped[int]=mapped_column(ForeignKey("projects.id",ondelete="CASCADE"),nullable=False); purchase_order_id:Mapped[int]=mapped_column(ForeignKey("purchase_orders.id"),nullable=False); supplier_id:Mapped[int]=mapped_column(ForeignKey("suppliers.id"),nullable=False)
    delivery_number:Mapped[str|None]=mapped_column(String(80)); delivery_note_number:Mapped[str|None]=mapped_column(String(120)); delivery_date:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False); status:Mapped[str]=mapped_column(String(30),default="EXPECTED",nullable=False); transport_cost_actual:Mapped[Decimal|None]=mapped_column(Numeric(18,2)); notes:Mapped[str|None]=mapped_column(Text); correction_of_id:Mapped[int|None]=mapped_column(ForeignKey("purchase_deliveries.id")); discrepancy_accepted:Mapped[bool]=mapped_column(Boolean,default=False,nullable=False); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,nullable=False); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow,nullable=False)

class DeliveryItem(Base):
    __tablename__="delivery_items"
    id:Mapped[int]=mapped_column(Integer,primary_key=True); delivery_id:Mapped[int]=mapped_column(ForeignKey("purchase_deliveries.id",ondelete="CASCADE"),nullable=False); purchase_order_item_id:Mapped[int]=mapped_column(ForeignKey("purchase_order_items.id"),nullable=False); material_id:Mapped[int|None]=mapped_column(ForeignKey("materials.id")); supplier_product_id:Mapped[int|None]=mapped_column(ForeignKey("supplier_products.id")); description:Mapped[str]=mapped_column(String(500),nullable=False); sku:Mapped[str|None]=mapped_column(String(120)); unit:Mapped[str]=mapped_column(String(20),nullable=False)
    quantity_ordered:Mapped[Decimal]=mapped_column(Numeric(18,6),nullable=False); quantity_expected:Mapped[Decimal]=mapped_column(Numeric(18,6),nullable=False); quantity_received:Mapped[Decimal]=mapped_column(Numeric(18,6),default=Decimal("0"),nullable=False); quantity_damaged:Mapped[Decimal]=mapped_column(Numeric(18,6),default=Decimal("0"),nullable=False); quantity_rejected:Mapped[Decimal]=mapped_column(Numeric(18,6),default=Decimal("0"),nullable=False); quantity_missing:Mapped[Decimal]=mapped_column(Numeric(18,6),default=Decimal("0"),nullable=False); quantity_accepted:Mapped[Decimal]=mapped_column(Numeric(18,6),default=Decimal("0"),nullable=False); actual_unit_price_gross:Mapped[Decimal|None]=mapped_column(Numeric(18,4)); notes:Mapped[str|None]=mapped_column(Text); over_delivery_confirmed:Mapped[bool]=mapped_column(Boolean,default=False,nullable=False)

class DeliveryIssue(Base):
    __tablename__="delivery_issues"
    id:Mapped[int]=mapped_column(Integer,primary_key=True); delivery_id:Mapped[int]=mapped_column(ForeignKey("purchase_deliveries.id",ondelete="CASCADE"),nullable=False); delivery_item_id:Mapped[int|None]=mapped_column(ForeignKey("delivery_items.id",ondelete="CASCADE")); issue_type:Mapped[str]=mapped_column(String(40),nullable=False); quantity:Mapped[Decimal|None]=mapped_column(Numeric(18,6)); description:Mapped[str]=mapped_column(Text,nullable=False); status:Mapped[str]=mapped_column(String(20),default="OPEN",nullable=False); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,nullable=False); resolved_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); resolution_notes:Mapped[str|None]=mapped_column(Text)

class MaterialReturn(Base):
    __tablename__="material_returns"; __table_args__=(UniqueConstraint("return_number",name="uq_material_return_number"),)
    id:Mapped[int]=mapped_column(Integer,primary_key=True); project_id:Mapped[int]=mapped_column(ForeignKey("projects.id",ondelete="CASCADE"),nullable=False); supplier_id:Mapped[int]=mapped_column(ForeignKey("suppliers.id"),nullable=False); delivery_id:Mapped[int|None]=mapped_column(ForeignKey("purchase_deliveries.id")); purchase_order_id:Mapped[int|None]=mapped_column(ForeignKey("purchase_orders.id")); return_number:Mapped[str]=mapped_column(String(80),nullable=False); return_date:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False); reason:Mapped[str]=mapped_column(String(30),nullable=False); status:Mapped[str]=mapped_column(String(30),default="DRAFT",nullable=False); refund_amount_gross:Mapped[Decimal|None]=mapped_column(Numeric(18,2)); notes:Mapped[str|None]=mapped_column(Text); correction_of_id:Mapped[int|None]=mapped_column(ForeignKey("material_returns.id")); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)

class MaterialReturnItem(Base):
    __tablename__="material_return_items"
    id:Mapped[int]=mapped_column(Integer,primary_key=True); material_return_id:Mapped[int]=mapped_column(ForeignKey("material_returns.id",ondelete="CASCADE"),nullable=False); delivery_item_id:Mapped[int]=mapped_column(ForeignKey("delivery_items.id"),nullable=False); material_id:Mapped[int|None]=mapped_column(ForeignKey("materials.id")); description:Mapped[str]=mapped_column(String(500),nullable=False); sku:Mapped[str|None]=mapped_column(String(120)); quantity:Mapped[Decimal]=mapped_column(Numeric(18,6),nullable=False); unit:Mapped[str]=mapped_column(String(20),nullable=False); expected_refund_gross:Mapped[Decimal|None]=mapped_column(Numeric(18,2)); actual_refund_gross:Mapped[Decimal|None]=mapped_column(Numeric(18,2)); notes:Mapped[str|None]=mapped_column(Text)
