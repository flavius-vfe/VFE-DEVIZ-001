import ipaddress, os, re, socket, time
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from sqlalchemy import create_engine, text
DATABASE_URL=os.environ["DATABASE_URL"]; POLL=int(os.getenv("WORKER_POLL_SECONDS","10")); HEALTH_FILE=os.getenv("HEALTH_FILE","/tmp/vfe-deviz-worker-health")
engine=create_engine(DATABASE_URL,pool_pre_ping=True); DOMAINS={"DEDEMAN":{"dedeman.ro","www.dedeman.ro"},"MATHAUS":{"mathaus.ro","www.mathaus.ro"},"LEROY_MERLIN":{"leroymerlin.ro","www.leroymerlin.ro"},"HORNBACH":{"hornbach.ro","www.hornbach.ro"}}
RATE_LIMITS={code:int(os.getenv(f"{('LEROY' if code=='LEROY_MERLIN' else code)}_REQUESTS_PER_MINUTE","6")) for code in DOMAINS}; LAST_REQUEST={}
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError("Redirecționare blocată")
def allowed(url,code):
    p=urlparse(url); host=(p.hostname or "").lower()
    if p.scheme!="https" or host not in DOMAINS.get(code,set()): raise ValueError("Domeniu furnizor nepermis")
    for x in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(x[4][0]).is_global: raise ValueError("Țintă SSRF blocată")
def fetch_price(url,code,timeout):
    interval=60/max(RATE_LIMITS[code],1);wait=interval-(time.monotonic()-LAST_REQUEST.get(code,0))
    if wait>0:time.sleep(wait)
    LAST_REQUEST[code]=time.monotonic()
    allowed(url,code); req=Request(url,headers={"User-Agent":"VFE-Deviz/0.2.0 supplier refresh","Accept":"text/html"})
    with build_opener(NoRedirect).open(req,timeout=timeout) as r: body=r.read(2_000_001)
    if len(body)>2_000_000: raise ValueError("Răspuns prea mare")
    html=body.decode("utf-8","replace"); patterns=[r'"price"\s*:\s*"?([0-9.,]+)',r'product:price:amount[^>]+content="([0-9.,]+)']
    value=next((m.group(1) for p in patterns if (m:=re.search(p,html,re.I))),None)
    if not value: raise ValueError("Prețul nu a putut fi extras")
    return Decimal(value.replace(".","").replace(",",".") if "," in value else value)
def tick():
    now=datetime.now(timezone.utc)
    with engine.begin() as c:
        c.execute(text("""INSERT INTO supplier_refresh_jobs (supplier_id,supplier_product_id,job_type,status,attempts,scheduled_at)
          SELECT DISTINCT sp.supplier_id,sp.id,'ACTIVE_PROJECTS','PENDING',0,:now
          FROM supplier_products sp JOIN material_product_matches mm ON mm.supplier_product_id=sp.id AND mm.approved=true
          JOIN estimate_resource_lines erl ON erl.resource_type='MATERIAL' AND erl.resource_id=mm.material_id
          JOIN estimate_items ei ON ei.id=erl.estimate_item_id JOIN estimate_sections es ON es.id=ei.section_id
          JOIN project_levels pl ON pl.id=es.level_id JOIN project_buildings pb ON pb.id=pl.building_id JOIN projects p ON p.id=pb.project_id AND p.active=true
          WHERE sp.active=true AND NOT EXISTS (SELECT 1 FROM supplier_refresh_jobs j WHERE j.supplier_product_id=sp.id AND j.status IN ('PENDING','RUNNING'))
          AND COALESCE((SELECT max(po.checked_at) FROM price_observations po WHERE po.supplier_product_id=sp.id AND po.success=true),TIMESTAMP '1970-01-01') < :now - INTERVAL '24 hours'"""),{"now":now})
        job=c.execute(text("""SELECT j.id,j.supplier_id,j.supplier_product_id,j.attempts,s.code,s.retry_count,s.backoff_seconds,s.request_timeout,p.product_url
          FROM supplier_refresh_jobs j JOIN suppliers s ON s.id=j.supplier_id LEFT JOIN supplier_products p ON p.id=j.supplier_product_id
          WHERE j.status='PENDING' AND j.scheduled_at<=:now
          ORDER BY CASE WHEN EXISTS (SELECT 1 FROM procurement_plan_items ppi JOIN procurement_plans pp ON pp.id=ppi.procurement_plan_id WHERE ppi.supplier_product_id=j.supplier_product_id AND pp.status IN ('CALCULATED','LOCKED')) THEN 0 ELSE 1 END,j.scheduled_at,j.id
          FOR UPDATE SKIP LOCKED LIMIT 1"""),{"now":now}).mappings().first()
        if not job:return
        c.execute(text("UPDATE supplier_refresh_jobs SET status='RUNNING',started_at=:now,attempts=attempts+1 WHERE id=:id"),{"now":now,"id":job["id"]})
    try:
        if not job["supplier_product_id"]:raise ValueError("Actualizarea furnizorului necesită produse individuale")
        gross=fetch_price(job["product_url"],job["code"],job["request_timeout"]);net=(gross/Decimal("1.21")).quantize(Decimal("0.0001"));vat=gross-net
        with engine.begin() as c:
            c.execute(text("INSERT INTO price_observations (supplier_product_id,price_net,vat_rate,vat_amount,price_gross,currency,stock_status,source,checked_at,success) VALUES (:p,:n,21,:v,:g,'RON','UNKNOWN','WEB',:now,true)"),{"p":job["supplier_product_id"],"n":net,"v":vat,"g":gross,"now":now})
            c.execute(text("UPDATE supplier_refresh_jobs SET status='COMPLETED',completed_at=:now,error_message=NULL WHERE id=:id"),{"now":now,"id":job["id"]});c.execute(text("UPDATE suppliers SET requests=requests+1,successes=successes+1,last_success=:now,last_error=NULL WHERE id=:id"),{"now":now,"id":job["supplier_id"]})
    except Exception as exc:
        attempts=job["attempts"]+1;retry=attempts<=job["retry_count"];scheduled=now+timedelta(seconds=job["backoff_seconds"]*(2**max(attempts-1,0)))
        with engine.begin() as c:
            if job["supplier_product_id"]:
                c.execute(text("""INSERT INTO price_observations (supplier_product_id,supplier_location_id,price_net,vat_rate,vat_amount,price_gross,currency,stock_status,stock_text,source,checked_at,success,error_message)
                  SELECT po.supplier_product_id,po.supplier_location_id,po.price_net,po.vat_rate,po.vat_amount,po.price_gross,po.currency,po.stock_status,po.stock_text,'WEB',:now,false,:error
                  FROM price_observations po WHERE po.supplier_product_id=:product AND po.success=true ORDER BY po.checked_at DESC,po.id DESC LIMIT 1"""),{"now":now,"error":str(exc)[:2000],"product":job["supplier_product_id"]})
            c.execute(text("UPDATE supplier_refresh_jobs SET status=:status,scheduled_at=:scheduled,completed_at=:done,error_message=:error WHERE id=:id"),{"status":"PENDING" if retry else "FAILED","scheduled":scheduled,"done":None if retry else now,"error":str(exc)[:2000],"id":job["id"]});c.execute(text("UPDATE suppliers SET requests=requests+1,failures=failures+1,last_error=:error WHERE id=:id"),{"error":str(exc)[:2000],"id":job["supplier_id"]})
if __name__=="__main__":
    while True:
        try:tick();open(HEALTH_FILE,"w",encoding="utf-8").write(str(time.time()))
        except Exception as exc:print(f"worker error: {exc}",flush=True)
        time.sleep(POLL)
