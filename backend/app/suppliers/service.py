from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
import re, unicodedata
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..calc import net_from_gross, money
from ..models import Supplier, SupplierProduct, PriceObservation

def package_purchase(required, package_quantity, package_price):
    required, size, price = map(lambda x: Decimal(str(x)), (required,package_quantity,package_price))
    if required < 0 or size <= 0 or price < 0: raise ValueError("Date de achiziție invalide.")
    packages=int((required/size).to_integral_value(rounding=ROUND_CEILING)); purchased=size*packages
    return {"packages_to_buy":packages,"purchase_quantity":purchased,"unused_quantity":purchased-required,"purchase_cost":money(price*packages)}

def retry_delay(backoff_seconds:int,attempt:int)->int:
    if backoff_seconds<0 or attempt<1:raise ValueError("Configurație retry invalidă.")
    return backoff_seconds*(2**(attempt-1))

def _words(value):
    ascii_text=unicodedata.normalize("NFKD",value.lower()).encode("ascii","ignore").decode()
    return set(re.findall(r"[a-z0-9]+",ascii_text))

def match_score(material, product) -> Decimal:
    a=_words(f"{material.name} {material.category}"); b=_words(f"{product.name} {product.category or ''}")
    text=Decimal(len(a & b))/Decimal(max(len(a | b),1)); score=text*Decimal("0.65")
    if material.category and material.category.lower() in (product.category or "").lower(): score+=Decimal("0.20")
    attrs=material.attributes or {}; pattrs=product.attributes or {}
    common=sum(1 for k,v in attrs.items() if str(v).lower() in str(pattrs.get(k,"")).lower())
    score+=min(Decimal(common)*Decimal("0.10"),Decimal("0.15"))
    return min(score,Decimal("1.0000")).quantize(Decimal("0.0001"))

def import_product(db: Session, supplier: Supplier, parsed, location_id=None, source="WEB"):
    now=datetime.now(timezone.utc)
    product=db.scalar(select(SupplierProduct).where(SupplierProduct.supplier_id==supplier.id,SupplierProduct.supplier_sku==parsed.sku))
    attributes=dict(parsed.attributes or {})
    if getattr(parsed,"diagnostics",None): attributes["diagnostic_parsare"]=parsed.diagnostics
    values=dict(supplier_location_id=location_id,name=parsed.name,brand=parsed.brand,category=parsed.category,product_url=parsed.url,image_url=parsed.image_url,package_quantity=parsed.package_quantity,package_unit=parsed.package_unit,normalized_quantity=parsed.normalized_quantity,normalized_unit=parsed.normalized_unit,attributes=attributes,active=True,last_seen_at=now)
    if product:
        for k,v in values.items(): setattr(product,k,v)
    else:
        product=SupplierProduct(supplier_id=supplier.id,supplier_sku=parsed.sku,first_seen_at=now,**values); db.add(product); db.flush()
    net=net_from_gross(parsed.gross,parsed.vat_rate); vat=money(parsed.gross-net)
    obs=PriceObservation(supplier_product_id=product.id,supplier_location_id=location_id,price_net=net,vat_rate=parsed.vat_rate,vat_amount=vat,price_gross=parsed.gross,currency="RON",stock_status=parsed.stock_status,stock_text=parsed.stock_text,source=source,checked_at=now,success=True)
    db.add(obs); supplier.requests+=1; supplier.successes+=1; supplier.last_success=now; supplier.last_error=None
    db.commit(); db.refresh(product); return product,obs
