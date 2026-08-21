from __future__ import annotations
import ipaddress
import socket
from urllib.parse import urlparse

ALLOWED_DOMAINS = {
    "DEDEMAN": {"dedeman.ro", "www.dedeman.ro"},
    "MATHAUS": {"mathaus.ro", "www.mathaus.ro"},
    "LEROY_MERLIN": {"leroymerlin.ro", "www.leroymerlin.ro"},
    "HORNBACH": {"hornbach.ro", "www.hornbach.ro"},
}
MAX_RESPONSE_BYTES = 2_000_000

def validate_supplier_url(url: str, supplier_code: str, resolve: bool = True) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("URL-ul trebuie să folosească HTTPS fără credențiale sau port personalizat.")
    host = (parsed.hostname or "").lower().rstrip(".")
    if host not in ALLOWED_DOMAINS.get(supplier_code.upper(), set()):
        raise ValueError("Domeniul nu este permis pentru furnizorul selectat.")
    if resolve:
        for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM):
            ip = ipaddress.ip_address(info[4][0])
            if not ip.is_global:
                raise ValueError("Adresele locale sau private nu sunt permise.")
    return url

def bounded_body(body: bytes) -> str:
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("Pagina furnizorului depășește limita permisă.")
    return body.decode("utf-8", errors="replace")
