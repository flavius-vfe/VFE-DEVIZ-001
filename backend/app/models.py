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
    locality: Mapped[str] = mapped_column(String(120), default="Ceahlău", nullable=False)
    county: Mapped[str] = mapped_column(String(120), default="Neamț", nullable=False)
    postal_code: Mapped[str | None] = mapped_column(String(20))
    default_waste_percent: Mapped[Decimal] = mapped_column(Numeric(7, 3), default=Decimal("5.000"), nullable=False)
    preferred_supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
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
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(160), nullable=False)
    base_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

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

class EstimateItem(Base):
    __tablename__ = "estimate_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("estimate_sections.id", ondelete="CASCADE"), nullable=False)
    work_item_id: Mapped[int | None] = mapped_column(ForeignKey("work_items.id"))
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18,6), nullable=False)
    calculation_type: Mapped[str] = mapped_column(String(30), default="MANUAL", nullable=False)
    calculation_inputs: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    waste_percent: Mapped[Decimal] = mapped_column(Numeric(7,3), default=Decimal("0"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="RETAILER")
    website: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)

class SupplierLocation(Base):
    __tablename__ = "supplier_locations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    locality: Mapped[str | None] = mapped_column(String(160))
    county: Mapped[str | None] = mapped_column(String(160))
    address: Mapped[str | None] = mapped_column(Text)
    preferred: Mapped[bool] = mapped_column(Boolean, default=False)

class SupplierProduct(Base):
    __tablename__ = "supplier_products"
    __table_args__ = (UniqueConstraint("supplier_id", "supplier_sku", name="uq_supplier_sku"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False)
    supplier_sku: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(200))
    product_url: Mapped[str] = mapped_column(Text, nullable=False)
    package_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18,6))
    package_unit: Mapped[str | None] = mapped_column(String(20))
    normalized_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18,6))
    normalized_unit: Mapped[str | None] = mapped_column(String(20))
    attributes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class ProductMatch(Base):
    __tablename__ = "product_matches"
    __table_args__ = (UniqueConstraint("material_id", "supplier_product_id", name="uq_material_product_match"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), nullable=False)
    supplier_product_id: Mapped[int] = mapped_column(ForeignKey("supplier_products.id", ondelete="CASCADE"), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5,4), nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    matching_notes: Mapped[str | None] = mapped_column(Text)

class PriceObservation(Base):
    __tablename__ = "price_observations"
    __table_args__ = (Index("ix_price_product_checked", "supplier_product_id", "checked_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_product_id: Mapped[int] = mapped_column(ForeignKey("supplier_products.id", ondelete="CASCADE"), nullable=False)
    supplier_location_id: Mapped[int | None] = mapped_column(ForeignKey("supplier_locations.id"))
    price_net: Mapped[Decimal | None] = mapped_column(Numeric(18,4))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(7,3), default=Decimal("21"))
    price_gross: Mapped[Decimal] = mapped_column(Numeric(18,4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="RON", nullable=False)
    stock_status: Mapped[str] = mapped_column(String(40), default="UNKNOWN", nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="WEB", nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str | None] = mapped_column(Text)

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
