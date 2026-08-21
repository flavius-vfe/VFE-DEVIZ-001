import test from "node:test";import assert from "node:assert/strict";import fs from "node:fs";
const ui=fs.readFileSync(new URL("../app/projects/[id]/procurement/procurement-client.tsx",import.meta.url),"utf8");const settings=fs.readFileSync(new URL("../app/projects/[id]/settings/page.tsx",import.meta.url),"utf8");
const page=fs.readFileSync(new URL("../app/projects/[id]/procurement/page.tsx",import.meta.url),"utf8");
test("navigare aprovizionare în română",()=>{for(const text of ["Comparație","Plan achiziție","Transport","Listă cumpărături","MIX OPTIM"])assert.match(ui,new RegExp(text))});
test("cost livrat separat și transport necunoscut",()=>{assert.match(ui,/Produse:/);assert.match(ui,/Transport/);assert.match(ui,/TOTAL LIVRAT/);assert.match(ui,/Necunoscut/)});
test("listă, stoc, link și exporturi",()=>{for(const text of ["Nr. pachete","Stoc necunoscut","Deschide produsul","export.pdf","export.xlsx","Blochează planul"])assert.match(ui,new RegExp(text.replace(".","\\.")))});
test("adresă de livrare proiect",()=>{assert.match(settings,/Adresă livrare/);assert.match(settings,/Localitate/);assert.match(settings,/Județ/);assert.match(settings,/România/)});
test("nu automatizează cumpărarea",()=>{assert.doesNotMatch(ui,/checkout|cumpără acum|plasează comanda/i)});
test("marchează vizibil prospețimea prețului",()=>{assert.match(page,/Preț actualizat/);assert.match(page,/Preț vechi/);assert.match(page,/Preț indisponibil/)});
