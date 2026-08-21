import test from "node:test";import assert from "node:assert/strict";import fs from "node:fs";
const delivery=fs.readFileSync(new URL("../app/projects/[id]/deliveries/page.tsx",import.meta.url),"utf8"),returns=fs.readFileSync(new URL("../app/projects/[id]/returns/page.tsx",import.meta.url),"utf8"),orders=fs.readFileSync(new URL("../app/projects/[id]/orders/page.tsx",import.meta.url),"utf8");
test("recepții și validări românești",()=>{for(const text of ["Recepții materiale","Recepție nouă","Deteriorat","Respins","Lipsă","Acceptat","Probleme recepție"])assert.match(delivery,new RegExp(text))});
test("diferențe transport și preț",()=>{assert.match(delivery,/Transport estimat/);assert.match(delivery,/Transport real/);assert.match(delivery,/unit_price_variance/)});
test("flux retur românesc",()=>{for(const text of ["Retururi","Retur nou","Marchează solicitat","Acceptat de furnizor","Expediat","Rambursat","Închide"])assert.match(returns,new RegExp(text))});
test("reconciliere comandă",()=>{for(const text of ["Comandat","Recepționat","Acceptat","Deteriorat","Respins","Retur","Rămas de livrat","Înregistrează livrare"])assert.match(orders,new RegExp(text))});
