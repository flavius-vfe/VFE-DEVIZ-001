"""Verificare live opțională, limitată la câte un URL public configurat."""
import argparse, os
from .suppliers import adapter_for

ALIASES={"dedeman":"DEDEMAN","mathaus":"MATHAUS","leroy":"LEROY_MERLIN","hornbach":"HORNBACH"}
def main(argv=None):
    parser=argparse.ArgumentParser(); group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--supplier",choices=ALIASES);group.add_argument("--all",action="store_true")
    args=parser.parse_args(argv); codes=list(ALIASES.values()) if args.all else [ALIASES[args.supplier]];configured=0
    for code in codes:
        url=os.getenv(f"SUPPLIER_SMOKE_{code}_URL")
        if not url: print(f"{code}: OMIS (URL neconfigurat)");continue
        configured+=1;a=adapter_for(code);p=a.parse_product(a.fetch_product(url),url);print(f"{code}: OK {p.sku} {p.gross} RON")
    return 0 if configured or args.all else 2
if __name__=="__main__":raise SystemExit(main())
