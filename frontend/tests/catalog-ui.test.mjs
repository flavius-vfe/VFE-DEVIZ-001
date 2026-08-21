import test from "node:test";import assert from "node:assert/strict";import{readFileSync}from"node:fs";
const works=readFileSync(new URL("../app/catalog/lucrari/page.tsx",import.meta.url),"utf8"),project=readFileSync(new URL("../app/projects/[id]/page.tsx",import.meta.url),"utf8"),settings=readFileSync(new URL("../app/settings/catalog/page.tsx",import.meta.url),"utf8");
test("navigare și căutare catalog",()=>{assert.match(works,/CatalogNav/);assert.match(works,/Caută lucrare/);assert.match(works,/Categorii/)});
test("adăugare lucrare în proiect",()=>{assert.match(project,/Adaugă lucrare din catalog/);assert.match(project,/items\/from-catalog/);assert.match(project,/quantity/)});
test("editor rețetă și versiuni",()=>{assert.match(works,/RecipeEditor/);assert.match(works,/Creează versiune nouă/);assert.match(works,/Pierderi %/);assert.match(works,/Elimină/)});
test("override-uri și administrare",()=>{assert.match(works,/scope/);assert.match(settings,/Reîncarcă date standard/);assert.match(settings,/Exportă catalog/);assert.match(settings,/Importă catalog/)});
test("validare formulare",()=>{assert.match(works,/required/);assert.match(works,/min=\"0\.000001\"/);assert.match(project,/min=\"0\.000001\"/)});
