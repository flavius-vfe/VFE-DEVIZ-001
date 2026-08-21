from __future__ import annotations
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from .calc import money
D=Decimal

DISCOUNT_TYPES={"PERCENT","FIXED_AMOUNT","PAYMENT_CONDITION","VOLUME_DISCOUNT"}
def dec(value,default="0"):return D(str(default if value in (None,"") else value))

def line_calculation(quantity,unit_price_net,vat_rate,discount_type=None,discount_value=None):
    quantity,price,vat=dec(quantity),dec(unit_price_net),dec(vat_rate)
    if quantity<=0 or price<0 or vat<0:raise ValueError("Cantitatea și prețurile trebuie să fie valide.")
    base=quantity*price;value=dec(discount_value)
    discount=base*value/D("100") if discount_type=="PERCENT" else value if discount_type=="FIXED_AMOUNT" else D("0")
    discount=min(max(discount,D("0")),base);net=money(base-discount);tax=money(net*vat/D("100"));gross=money(net+tax)
    return {"unit_price_gross":money(price*(D("1")+vat/D("100"))),"discount_net":money(discount),"line_total_net":net,"line_vat":tax,"line_total_gross":gross}

def quote_calculation(lines,discounts=(),transport_net=0,pump_fixed_cost=0,pump_hourly_cost=0,pump_hours=0,waiting_cost=0,other_cost=0,extra_vat_rate=21):
    """Deterministic order: line discount -> quote % -> quote fixed -> extras -> VAT."""
    line_discounts=sum((dec(x.get("discount_net")) for x in lines),D("0"));remaining=money(sum((dec(x["line_total_net"]) for x in lines),D("0")));subtotal=money(remaining+line_discounts);discount_total=line_discounts
    after_line=remaining;active=[x for x in discounts if x.get("active",True)]
    for row in [x for x in active if x["discount_type"] in {"PERCENT","VOLUME_DISCOUNT","PAYMENT_CONDITION"}]:
        amount=money(remaining*dec(row["value"])/D("100"));remaining=max(D("0"),remaining-amount);discount_total+=amount
    for row in [x for x in active if x["discount_type"]=="FIXED_AMOUNT"]:
        amount=min(remaining,dec(row["value"]));remaining-=amount;discount_total+=amount
    extras=dec(transport_net)+dec(pump_fixed_cost)+dec(pump_hourly_cost)*dec(pump_hours)+dec(waiting_cost)+dec(other_cost)
    line_vat=sum((dec(x["line_vat"]) for x in lines),D("0"));quote_reduction=after_line-remaining
    weighted_vat=max(D("0"),line_vat-money(quote_reduction*dec(extra_vat_rate)/D("100")));vat=money(weighted_vat+extras*dec(extra_vat_rate)/D("100"))
    return {"subtotal_net":subtotal,"discount_total_net":money(discount_total),"extras_net":money(extras),"vat_total":vat,"total_gross":money(remaining+extras+vat)}

def validity(valid_until,now=None,warning_days=3):
    if not valid_until:return "VALID"
    now=now or datetime.now(timezone.utc);until=valid_until if valid_until.tzinfo else valid_until.replace(tzinfo=timezone.utc)
    if until<now:return "EXPIRED"
    return "EXPIRING_SOON" if until<=now+timedelta(days=warning_days) else "VALID"

ALLOWED_ATTACHMENTS={".pdf":"application/pdf",".jpg":"image/jpeg",".jpeg":"image/jpeg",".png":"image/png",".xlsx":"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
def validate_attachment(filename,mime,size,max_size=10*1024*1024):
    from pathlib import Path
    ext=Path(filename).suffix.lower()
    if ext not in ALLOWED_ATTACHMENTS or mime!=ALLOWED_ATTACHMENTS[ext]:raise ValueError("Tipul fișierului nu este permis.")
    if size<=0 or size>max_size:raise ValueError("Fișierul depășește limita de 10 MB.")
    return ext
def validate_signature(ext,content):
    signatures={".pdf":b"%PDF-",".jpg":b"\xff\xd8\xff",".jpeg":b"\xff\xd8\xff",".png":b"\x89PNG\r\n\x1a\n",".xlsx":b"PK\x03\x04"}
    if not content.startswith(signatures[ext]):raise ValueError("Conținutul fișierului nu corespunde extensiei declarate.")
