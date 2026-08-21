import test from "node:test";import assert from "node:assert/strict";import fs from "node:fs";
const supplier=fs.readFileSync(new URL("../app/suppliers/supplier-client.tsx",import.meta.url),"utf8");
const products=fs.readFileSync(new URL("../app/catalog/materiale/[id]/produse/page.tsx",import.meta.url),"utf8");
test("import URL și stare adaptoare în română",()=>{assert.match(supplier,/Importă produs/);assert.match(supplier,/Actualizează prețurile/);assert.match(supplier,/Ultima verificare reușită/);assert.match(supplier,/Preț neconfirmat/)});
test("asociere manuală produse furnizor",()=>{assert.match(products,/Asociază/);assert.match(products,/Respinge/);assert.match(products,/Deschide produsul/);assert.match(products,/Încredere/)});
test("doar Dedeman și MatHaus",()=>{assert.match(supplier,/DEDEMAN/);assert.match(supplier,/MATHAUS/);assert.doesNotMatch(supplier,/Leroy|Hornbach/)});
