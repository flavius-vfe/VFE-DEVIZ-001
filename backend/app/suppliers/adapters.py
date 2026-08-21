from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from html import unescape
from html.parser import HTMLParser
import json, re
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .security import validate_supplier_url, bounded_body

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): raise ValueError("Redirecționarea paginii furnizorului a fost blocată.")

def clean(value: object) -> str:
    return re.sub(r"\s+", " ", unescape(str(value or ""))).strip()[:2000]

def decimal_ro(value: object) -> Decimal:
    text = clean(value).replace("RON", "").replace("lei", "").replace(" ", "")
    if "," in text: text = text.replace(".", "").replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match: raise ValueError("Prețul nu a putut fi citit.")
    return Decimal(match.group())

def unit(value: str | None) -> str | None:
    text = clean(value).lower().replace("²", "2").replace("³", "3")
    aliases={"bucata":"buc","bucăți":"buc","bucati":"buc","metru liniar":"ml","litri":"litru","l":"litru","tone":"tona"}
    return aliases.get(text, text) if text in {"buc","sac","palet","kg","tona","ml","m2","m3","litru","set"} or text in aliases else None

def packaging(text: str) -> tuple[Decimal|None,str|None,dict]:
    """Extract a comparable package quantity while retaining the source phrase."""
    source=clean(text).replace("\u00b2","2").replace("\u00b3","3")
    patterns=(
        r"(\d+(?:[,.]\d+)?)\s*(m[23]|kg|litri?|buc)\s*/\s*(?:pachet|sac|palet|buc)",
        r"(\d+(?:[,.]\d+)?)\s*(m[23]|kg|litri?|buc)\b",
    )
    for pattern in patterns:
        match=re.search(pattern,source,re.I)
        if match:
            q,u=decimal_ro(match.group(1)),unit(match.group(2))
            return q,u,{"ambalaj_original":clean(match.group(0))}
    return None,None,{"ambalaj_original":source[:500]} if source else {}

def stock(value: str | None) -> str:
    text = clean(value).lower()
    if any(x in text for x in ("stoc epuizat", "indisponibil", "nu este în stoc")): return "OUT_OF_STOCK"
    if any(x in text for x in ("stoc limitat", "ultimele", "în limita stocului")): return "LIMITED"
    if any(x in text for x in ("în stoc", "in stoc", "disponibil")): return "IN_STOCK"
    return "UNKNOWN"

class Collector(HTMLParser):
    def __init__(self): super().__init__(); self.jsonld=[]; self.meta={}; self.text=[]; self._script=False; self._buf=[]
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag=="meta" and a.get("content"): self.meta[a.get("property") or a.get("name") or a.get("itemprop") or ""]=a["content"]
        if tag=="script" and a.get("type")=="application/ld+json": self._script=True; self._buf=[]
    def handle_endtag(self, tag):
        if tag=="script" and self._script:
            try: self.jsonld.append(json.loads("".join(self._buf)))
            except (ValueError, TypeError): pass
            self._script=False
    def handle_data(self, data):
        if self._script: self._buf.append(data)
        else: self.text.append(data)

@dataclass
class ParsedProduct:
    sku: str; name: str; url: str; gross: Decimal
    vat_rate: Decimal = Decimal("21"); brand: str|None=None; category: str|None=None; image_url: str|None=None
    package_quantity: Decimal|None=None; package_unit: str|None=None; normalized_quantity: Decimal|None=None; normalized_unit: str|None=None
    stock_status: str="UNKNOWN"; stock_text: str|None=None; attributes: dict = field(default_factory=dict)
    diagnostics: list[dict] = field(default_factory=list)

class SupplierAdapter(ABC):
    code=""; sitemap_url=""
    def discover_urls(self): return []
    def fetch_product(self, url: str) -> str:
        validate_supplier_url(url, self.code)
        req=Request(url, headers={"User-Agent":"VFE-Deviz/0.2.0 (+manual supplier price verification)","Accept":"text/html"})
        with build_opener(NoRedirect).open(req, timeout=15) as response: return bounded_body(response.read(2_000_001))
    @abstractmethod
    def parse_product(self, html: str, url: str=""): ...
    def normalize_product(self, parsed): return parsed
    def refresh_product(self, product): return self.normalize_product(self.parse_product(self.fetch_product(product.product_url), product.product_url))
    def health_check(self, representative_url: str|None=None):
        if not representative_url: return {"code":self.code,"status":"UNKNOWN","detail":"Nu este configurat un produs reprezentativ."}
        try:
            parsed=self.refresh_product(type("Product",(),{"product_url":representative_url})())
            return {"code":self.code,"status":"HEALTHY","sku":parsed.sku}
        except Exception as exc:
            return {"code":self.code,"status":"DEGRADED","detail":clean(exc)}
    def _product(self, html):
        c=Collector(); c.feed(html)
        nodes=[]
        def walk(x):
            if isinstance(x,dict):
                if x.get("@type") in ("Product",["Product"]): nodes.append(x)
                for v in x.values(): walk(v)
            elif isinstance(x,list):
                for v in x: walk(v)
        for x in c.jsonld: walk(x)
        return c, (nodes[0] if nodes else {})

class DedemanAdapter(SupplierAdapter):
    code="DEDEMAN"; sitemap_url="https://www.dedeman.ro/media/sitemap/sitemap.xml"
    def discover_urls(self):
        # Descoperire conservatoare: numai URL-uri publice din sitemap și categorii de construcții.
        validate_supplier_url(self.sitemap_url,self.code)
        req=Request(self.sitemap_url,headers={"User-Agent":"VFE-Deviz/0.2.0 sitemap discovery"})
        with build_opener(NoRedirect).open(req,timeout=15) as response: xml=bounded_body(response.read(2_000_001))
        terms=("bca","ciment","adeziv","caramida","beton","izol","gips","mortar","otel","plasa")
        return [clean(x) for x in re.findall(r"<loc>(.*?)</loc>",xml,re.I) if any(t in x.lower() for t in terms)][:500]
    def parse_product(self, html: str, url: str="") -> ParsedProduct:
        c,p=self._product(html); offer=p.get("offers") or {}; offer=offer[0] if isinstance(offer,list) else offer
        sku=clean(p.get("sku") or c.meta.get("product:retailer_item_id")); name=clean(p.get("name") or c.meta.get("og:title")); price=decimal_ro(offer.get("price") or c.meta.get("product:price:amount"))
        if not sku or not name: raise ValueError("Pagina Dedeman nu conține SKU și denumire publice.")
        desc=clean(p.get("description")); m=re.search(r"(\d+(?:[,.]\d+)?)\s*(kg|m[23]|litri?|buc)\b", desc, re.I)
        q=decimal_ro(m.group(1)) if m else None; u=unit(m.group(2)) if m else None
        brand=p.get("brand"); brand=brand.get("name") if isinstance(brand,dict) else brand
        return ParsedProduct(sku,name,url or clean(p.get("url")),price,brand=clean(brand) or None,category=clean(p.get("category")) or None,image_url=clean(p.get("image")) or None,package_quantity=q,package_unit=u,normalized_quantity=q,normalized_unit=u,stock_status="UNKNOWN",attributes={"descriere_tehnică":desc})

class MathausAdapter(SupplierAdapter):
    code="MATHAUS"
    def parse_product(self, html: str, url: str="") -> ParsedProduct:
        c,p=self._product(html); alltext=clean(" ".join(c.text)); offer=p.get("offers") or {}; offer=offer[0] if isinstance(offer,list) else offer
        sku=clean(p.get("sku") or p.get("productID") or c.meta.get("product:retailer_item_id")); name=clean(p.get("name") or c.meta.get("og:title")); price=decimal_ro(offer.get("price") or c.meta.get("product:price:amount"))
        vatm=re.search(r"TVA\s*(\d+(?:[,.]\d+)?)\s*%", alltext, re.I); vat=decimal_ro(vatm.group(1)) if vatm else Decimal("21")
        pack=re.search(r"(\d+(?:[,.]\d+)?)\s*(kg|m[23]|litri?|buc)\s*/\s*(sac|palet|buc)", alltext,re.I)
        q=decimal_ro(pack.group(1)) if pack else None; u=unit(pack.group(2)) if pack else None
        brand=p.get("brand"); brand=brand.get("name") if isinstance(brand,dict) else brand
        stocktext=clean(offer.get("availability") or next((x for x in c.text if "stoc" in x.lower() or "disponibil" in x.lower()),""))
        attrs={"specificații":clean(p.get("description"))}; pallet=re.search(r"(\d+(?:[,.]\d+)?)\s*(buc|m3)\s*/\s*palet",alltext,re.I)
        if pallet: attrs["palet"]={"cantitate":str(decimal_ro(pallet.group(1))),"unitate":unit(pallet.group(2))}
        return ParsedProduct(sku,name,url or clean(p.get("url")),price,vat_rate=vat,brand=clean(brand) or None,category=clean(p.get("category")) or None,image_url=clean(p.get("image")) or None,package_quantity=q,package_unit=u,normalized_quantity=q,normalized_unit=u,stock_status=stock(f"{stocktext} {alltext}"),stock_text=stocktext or None,attributes=attrs)

class PublicRetailProductAdapter(SupplierAdapter):
    """Conservative public-page parser: JSON-LD, semantic metadata, then text."""
    force_unknown_stock=False
    def parse_product(self, html: str, url: str="") -> ParsedProduct:
        c,p=self._product(html); alltext=clean(" ".join(c.text)); offer=p.get("offers") or {}
        offer=offer[0] if isinstance(offer,list) else offer
        fields={
            "sku":(p.get("sku") or p.get("productID") or c.meta.get("product:retailer_item_id"),"JSON-LD/metadata"),
            "name":(p.get("name") or c.meta.get("og:title"),"JSON-LD/og:title"),
            "price":(offer.get("price") or c.meta.get("product:price:amount"),"JSON-LD/metadata"),
        }
        diagnostics=[{"field":key,"source":source,"success":bool(clean(value))} for key,(value,source) in fields.items()]
        sku,name=clean(fields["sku"][0]),clean(fields["name"][0])
        if not sku or not name or not clean(fields["price"][0]):
            raise ValueError(f"Pagina {self.code} a pierdut câmpuri critice (SKU, denumire sau preț).")
        price=decimal_ro(fields["price"][0]); description=clean(p.get("description")); q,u,attrs=packaging(f"{description} {alltext}")
        brand=p.get("brand"); brand=brand.get("name") if isinstance(brand,dict) else brand
        vat_match=re.search(r"(?:TVA|inclusiv TVA)\s*(\d+(?:[,.]\d+)?)\s*%",alltext,re.I)
        dims=re.findall(r"\d+(?:[,.]\d+)?\s*(?:mm|cm|m)\b",f"{description} {alltext}",re.I)[:6]
        if dims: attrs["dimensiuni"]=[clean(x) for x in dims]
        weight=re.search(r"(?:greutate)?\s*(\d+(?:[,.]\d+)?)\s*kg\b",f"{description} {alltext}",re.I)
        if weight: attrs["greutate_kg"]=str(decimal_ro(weight.group(1)))
        stocktext=clean(offer.get("availability") or next((x for x in c.text if any(t in x.lower() for t in ("stoc","livrare","disponibil"))),""))
        return ParsedProduct(sku,name,url or clean(p.get("url")),price,vat_rate=decimal_ro(vat_match.group(1)) if vat_match else Decimal("21"),brand=clean(brand) or None,category=clean(p.get("category")) or None,image_url=clean(p.get("image") if not isinstance(p.get("image"),list) else p.get("image")[0]) or c.meta.get("og:image") or None,package_quantity=q,package_unit=u,normalized_quantity=q,normalized_unit=u,stock_status="UNKNOWN" if self.force_unknown_stock else stock(f"{stocktext} {alltext}"),stock_text=stocktext or None,attributes={**attrs,"caracteristici_tehnice":description},diagnostics=diagnostics)

class LeroyMerlinAdapter(PublicRetailProductAdapter):
    code="LEROY_MERLIN"; force_unknown_stock=True
    sitemap_url="https://www.leroymerlin.ro/sitemap.xml"
    def discover_urls(self):
        validate_supplier_url(self.sitemap_url,self.code)
        req=Request(self.sitemap_url,headers={"User-Agent":"VFE-Deviz/0.2.0 category-limited discovery"})
        with build_opener(NoRedirect).open(req,timeout=15) as response: xml=bounded_body(response.read(2_000_001))
        terms=("bca","ciment","adeziv","polistiren","xps","vata","gips-carton","otel","plasa","tencuiala","glet","vopsea","membrana","acoperis")
        return [clean(x) for x in re.findall(r"<loc>(.*?)</loc>",xml,re.I) if any(t in x.lower() for t in terms)][:500]

class HornbachAdapter(PublicRetailProductAdapter):
    code="HORNBACH"
    def discover_urls(self): return []

def adapter_for(code: str) -> SupplierAdapter:
    adapters={"DEDEMAN":DedemanAdapter,"MATHAUS":MathausAdapter,"LEROY_MERLIN":LeroyMerlinAdapter,"HORNBACH":HornbachAdapter}
    try: return adapters[code.upper()]()
    except KeyError: raise ValueError("Furnizor fără adaptor configurat.")
