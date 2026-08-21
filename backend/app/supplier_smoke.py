"""Verificare live opțională: SUPPLIER_SMOKE_DEDEMAN_URL / SUPPLIER_SMOKE_MATHAUS_URL."""
import os
from .suppliers import adapter_for
def main():
    configured=0
    for code in ("DEDEMAN","MATHAUS"):
        url=os.getenv(f"SUPPLIER_SMOKE_{code}_URL")
        if not url:continue
        configured+=1;a=adapter_for(code);p=a.parse_product(a.fetch_product(url),url);print(f"{code}: OK {p.sku} {p.gross} RON")
    if not configured:print("Nu sunt configurate URL-uri live; verificarea a fost omisă.")
if __name__=="__main__":main()
