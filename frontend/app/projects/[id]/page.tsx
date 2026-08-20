"use client";

import {FormEvent, ReactNode, useCallback, useEffect, useMemo, useState} from "react";
import {useParams} from "next/navigation";
import {api} from "../../../lib/api";

const UNITS = ["buc", "ml", "m2", "m3", "kg", "tona", "ora", "set"] as const;
type Unit = typeof UNITS[number];
type Project = {id:number; name:string; locality:string; county:string};
type Item = {id:number; section_id:number; code:string; description:string; unit:Unit; quantity:string; waste_percent:string; notes:string|null; sort_order:number};
type Section = {id:number; level_id:number; code:string; name:string; parent_section_id:number|null; sort_order:number; items:Item[]};
type Level = {id:number; building_id:number; name:string; elevation_m:string|null; sort_order:number; sections:Section[]};
type Building = {id:number; project_id:number; name:string; sort_order:number; levels:Level[]};

function message(error:unknown) {
  return error instanceof Error ? error.message : "A apărut o eroare neașteptată.";
}

function itemTotals(items:Item[]) {
  return items.reduce<Record<string, number>>((totals, item) => {
    const adjusted = Number(item.quantity) * (1 + Number(item.waste_percent) / 100);
    totals[item.unit] = (totals[item.unit] || 0) + adjusted;
    return totals;
  }, {});
}

function Subtotal({items, label}:{items:Item[]; label:string}) {
  const totals = itemTotals(items);
  const entries = Object.entries(totals);
  return <div className="subtotal"><strong>{label}:</strong>{entries.length === 0 ? " fără cantități" : " " + entries.map(([unit, value]) => `${value.toLocaleString("ro-RO", {maximumFractionDigits:3})} ${unit}`).join(" • ")}</div>;
}

export default function ProjectPage() {
  const params = useParams<{id:string}>();
  const projectId = Number(params.id);
  const [project, setProject] = useState<Project|null>(null);
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [addingBuilding, setAddingBuilding] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const loadedProject = await api(`/api/projects/${projectId}`);
      const rawBuildings = await api(`/api/projects/${projectId}/buildings`);
      const fullBuildings:Building[] = await Promise.all(rawBuildings.map(async (building:Building) => {
        const rawLevels = await api(`/api/buildings/${building.id}/levels`);
        const levels:Level[] = await Promise.all(rawLevels.map(async (level:Level) => {
          const rawSections = await api(`/api/levels/${level.id}/sections`);
          const sections:Section[] = await Promise.all(rawSections.map(async (section:Section) => ({
            ...section,
            items: await api(`/api/sections/${section.id}/items`)
          })));
          return {...level, sections};
        }));
        return {...building, levels};
      }));
      setProject(loadedProject);
      setBuildings(fullBuildings);
    } catch (caught) {
      setError(message(caught));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { if (Number.isInteger(projectId) && projectId > 0) load(); else { setError("Identificatorul proiectului nu este valid."); setLoading(false); } }, [load, projectId]);

  async function mutate(action:()=>Promise<unknown>) {
    setBusy(true); setError("");
    try { await action(); await load(); return true; }
    catch (caught) { setError(message(caught)); return false; }
    finally { setBusy(false); }
  }

  const projectItems = useMemo(() => buildings.flatMap(b => b.levels.flatMap(l => l.sections.flatMap(s => s.items))), [buildings]);
  if (loading) return <main><div className="card">Se încarcă proiectul și structura devizului...</div></main>;

  return <main>
    <div className="breadcrumbs"><a href="/">Proiecte</a><span>/</span><strong>{project?.name || "Proiect"}</strong></div>
    <header><div><h1>{project?.name || "Proiect indisponibil"}</h1>{project && <div className="muted">{project.locality}, {project.county}</div>}</div><div className="toolbar"><a href={`/projects/${projectId}/estimate`}>Deviz valoric</a><a href="/">Înapoi la proiecte</a></div></header>
    {error && <div className="card error" role="alert">{error} <button className="secondary" onClick={load}>Reîncearcă</button></div>}
    {project && <>
      <Subtotal items={projectItems} label="Total proiect, cu pierderi" />
      <div className="toolbar push"><h2>Structură deviz</h2><button className="primary" disabled={busy} onClick={() => setAddingBuilding(true)}>Adaugă corp</button></div>
      {addingBuilding && <BuildingForm disabled={busy} onCancel={() => setAddingBuilding(false)} onSave={async payload => { if (await mutate(() => api(`/api/projects/${projectId}/buildings`, {method:"POST", body:JSON.stringify(payload)}))) setAddingBuilding(false); }} />}
      {buildings.length === 0 && !addingBuilding ? <div className="empty">Proiectul nu are corpuri. Adaugă primul corp pentru a începe structura devizului.</div> : buildings.map(building => <BuildingCard key={building.id} building={building} projectName={project.name} busy={busy} mutate={mutate} />)}
    </>}
  </main>;
}

function Panel({children}:{children:ReactNode}) { return <div className="card">{children}</div>; }

function BuildingForm({initial,disabled,onSave,onCancel}:{initial?:Building;disabled:boolean;onSave:(p:{name:string;sort_order:number})=>Promise<void>;onCancel:()=>void}) {
  const [name,setName]=useState(initial?.name||"");
  return <Panel><h3>{initial ? "Editează corpul" : "Corp nou"}</h3><form onSubmit={async e=>{e.preventDefault(); if(name.trim()) await onSave({name:name.trim(),sort_order:initial?.sort_order||0});}}><label>Denumire corp</label><input required maxLength={160} value={name} onChange={e=>setName(e.target.value)} placeholder="ex. Corp principal"/><div className="toolbar" style={{marginTop:12}}><button className="primary" disabled={disabled}>Salvează</button><button type="button" className="secondary" onClick={onCancel}>Renunță</button></div></form></Panel>;
}

function BuildingCard({building,projectName,busy,mutate}:{building:Building;projectName:string;busy:boolean;mutate:(a:()=>Promise<unknown>)=>Promise<boolean>}) {
  const [editing,setEditing]=useState(false), [adding,setAdding]=useState(false);
  const items=building.levels.flatMap(l=>l.sections.flatMap(s=>s.items));
  if(editing) return <BuildingForm initial={building} disabled={busy} onCancel={()=>setEditing(false)} onSave={async p=>{if(await mutate(()=>api(`/api/buildings/${building.id}`,{method:"PUT",body:JSON.stringify(p)})))setEditing(false);}}/>;
  return <div className="hierarchy"><Panel><div className="toolbar push"><div><div className="muted">{projectName} / Corp</div><h2>{building.name}</h2></div><div className="toolbar"><button className="secondary" onClick={()=>setEditing(true)}>Editează</button><button className="danger" disabled={busy} onClick={()=>{if(confirm(`Ștergi corpul „${building.name}” și tot conținutul său?`))mutate(()=>api(`/api/buildings/${building.id}`,{method:"DELETE"}));}}>Șterge</button></div></div><Subtotal items={items} label="Subtotal corp"/><button className="primary" onClick={()=>setAdding(true)}>Adaugă nivel</button></Panel>{adding&&<LevelForm disabled={busy} onCancel={()=>setAdding(false)} onSave={async p=>{if(await mutate(()=>api(`/api/buildings/${building.id}/levels`,{method:"POST",body:JSON.stringify(p)})))setAdding(false);}}/>}{building.levels.length===0&&!adding?<div className="empty">Acest corp nu are niveluri.</div>:building.levels.map(level=><LevelCard key={level.id} level={level} trail={`${projectName} / ${building.name}`} busy={busy} mutate={mutate}/>)}</div>;
}

function LevelForm({initial,disabled,onSave,onCancel}:{initial?:Level;disabled:boolean;onSave:(p:{name:string;elevation_m:string|null;sort_order:number})=>Promise<void>;onCancel:()=>void}) {
  const [name,setName]=useState(initial?.name||""),[elevation,setElevation]=useState(initial?.elevation_m||"");
  return <Panel><h3>{initial?"Editează nivelul":"Nivel nou"}</h3><form className="form-grid" onSubmit={async e=>{e.preventDefault();await onSave({name:name.trim(),elevation_m:elevation===""?null:elevation,sort_order:initial?.sort_order||0});}}><div><label>Denumire nivel</label><input required maxLength={160} value={name} onChange={e=>setName(e.target.value)} placeholder="ex. Parter"/></div><div><label>Cotă (m)</label><input type="number" step="0.001" value={elevation} onChange={e=>setElevation(e.target.value)}/></div><div className="wide toolbar" style={{marginTop:12}}><button className="primary" disabled={disabled}>Salvează</button><button type="button" className="secondary" onClick={onCancel}>Renunță</button></div></form></Panel>;
}

function LevelCard({level,trail,busy,mutate}:{level:Level;trail:string;busy:boolean;mutate:(a:()=>Promise<unknown>)=>Promise<boolean>}) {
  const [editing,setEditing]=useState(false),[adding,setAdding]=useState(false); const items=level.sections.flatMap(s=>s.items);
  if(editing)return <LevelForm initial={level} disabled={busy} onCancel={()=>setEditing(false)} onSave={async p=>{if(await mutate(()=>api(`/api/levels/${level.id}`,{method:"PUT",body:JSON.stringify(p)})))setEditing(false);}}/>;
  return <div className="hierarchy level"><Panel><div className="toolbar push"><div><div className="muted">{trail} / Nivel</div><h3>{level.name}{level.elevation_m!==null?` • cota ${Number(level.elevation_m).toLocaleString("ro-RO")} m`:""}</h3></div><div className="toolbar"><button className="secondary" onClick={()=>setEditing(true)}>Editează</button><button className="danger" disabled={busy} onClick={()=>{if(confirm(`Ștergi nivelul „${level.name}” și tot conținutul său?`))mutate(()=>api(`/api/levels/${level.id}`,{method:"DELETE"}));}}>Șterge</button></div></div><Subtotal items={items} label="Subtotal nivel"/><button className="primary" onClick={()=>setAdding(true)}>Adaugă capitol</button></Panel>{adding&&<SectionForm disabled={busy} onCancel={()=>setAdding(false)} onSave={async p=>{if(await mutate(()=>api(`/api/levels/${level.id}/sections`,{method:"POST",body:JSON.stringify(p)})))setAdding(false);}}/>}{level.sections.length===0&&!adding?<div className="empty">Acest nivel nu are capitole.</div>:level.sections.map(section=><SectionCard key={section.id} section={section} trail={`${trail} / ${level.name}`} busy={busy} mutate={mutate}/>)}</div>;
}

function SectionForm({initial,disabled,onSave,onCancel}:{initial?:Section;disabled:boolean;onSave:(p:{code:string;name:string;parent_section_id:number|null;sort_order:number})=>Promise<void>;onCancel:()=>void}) {
  const [code,setCode]=useState(initial?.code||""),[name,setName]=useState(initial?.name||"");
  return <Panel><h3>{initial?"Editează capitolul":"Capitol nou"}</h3><form className="form-grid" onSubmit={async e=>{e.preventDefault();await onSave({code:code.trim(),name:name.trim(),parent_section_id:initial?.parent_section_id||null,sort_order:initial?.sort_order||0});}}><div><label>Cod</label><input required maxLength={50} value={code} onChange={e=>setCode(e.target.value)} placeholder="ex. 01"/></div><div><label>Denumire capitol</label><input required maxLength={255} value={name} onChange={e=>setName(e.target.value)} placeholder="ex. Fundații"/></div><div className="wide toolbar" style={{marginTop:12}}><button className="primary" disabled={disabled}>Salvează</button><button type="button" className="secondary" onClick={onCancel}>Renunță</button></div></form></Panel>;
}

function SectionCard({section,trail,busy,mutate}:{section:Section;trail:string;busy:boolean;mutate:(a:()=>Promise<unknown>)=>Promise<boolean>}) {
  const [editing,setEditing]=useState(false),[adding,setAdding]=useState(false),[editingItem,setEditingItem]=useState<number|null>(null);
  if(editing)return <SectionForm initial={section} disabled={busy} onCancel={()=>setEditing(false)} onSave={async p=>{if(await mutate(()=>api(`/api/sections/${section.id}`,{method:"PUT",body:JSON.stringify(p)})))setEditing(false);}}/>;
  return <div className="hierarchy section"><Panel><div className="toolbar push"><div><div className="muted">{trail} / Capitol</div><h3>{section.code} — {section.name}</h3></div><div className="toolbar"><button className="secondary" onClick={()=>setEditing(true)}>Editează</button><button className="danger" disabled={busy} onClick={()=>{if(confirm(`Ștergi capitolul „${section.name}” și toate articolele?`))mutate(()=>api(`/api/sections/${section.id}`,{method:"DELETE"}));}}>Șterge</button></div></div><Subtotal items={section.items} label="Subtotal capitol"/><button className="primary" onClick={()=>setAdding(true)}>Adaugă articol</button>{adding&&<ItemForm disabled={busy} onCancel={()=>setAdding(false)} onSave={async p=>{if(await mutate(()=>api(`/api/sections/${section.id}/items`,{method:"POST",body:JSON.stringify(p)})))setAdding(false);}}/>}{section.items.length===0&&!adding?<div className="empty" style={{marginTop:12}}>Capitolul nu are articole de deviz.</div>:section.items.map(item=>editingItem===item.id?<ItemForm key={item.id} initial={item} disabled={busy} onCancel={()=>setEditingItem(null)} onSave={async p=>{if(await mutate(()=>api(`/api/estimate-items/${item.id}`,{method:"PUT",body:JSON.stringify(p)})))setEditingItem(null);}}/>:<div className="item-row" key={item.id}><strong>{item.code}</strong><div>{item.description}{item.notes&&<div className="muted">{item.notes}</div>}</div><span>{Number(item.quantity).toLocaleString("ro-RO")} {item.unit}</span><span>Pierderi {Number(item.waste_percent).toLocaleString("ro-RO")}%</span><strong>{(Number(item.quantity)*(1+Number(item.waste_percent)/100)).toLocaleString("ro-RO",{maximumFractionDigits:3})} {item.unit}</strong><div className="toolbar"><button className="secondary" onClick={()=>setEditingItem(item.id)}>Editează</button><button className="danger" disabled={busy} onClick={()=>{if(confirm(`Ștergi articolul „${item.description}”?`))mutate(()=>api(`/api/estimate-items/${item.id}`,{method:"DELETE"}));}}>Șterge</button></div></div>)}</Panel></div>;
}

function ItemForm({initial,disabled,onSave,onCancel}:{initial?:Item;disabled:boolean;onSave:(p:Record<string,unknown>)=>Promise<void>;onCancel:()=>void}) {
  const [code,setCode]=useState(initial?.code||""),[description,setDescription]=useState(initial?.description||""),[unit,setUnit]=useState<Unit>(initial?.unit||"buc"),[quantity,setQuantity]=useState(initial?.quantity||"1"),[waste,setWaste]=useState(initial?.waste_percent||"0"),[notes,setNotes]=useState(initial?.notes||"");
  return <div className="card" style={{marginTop:12}}><h3>{initial?"Editează articolul":"Articol nou"}</h3><form className="form-grid" onSubmit={async(e:FormEvent)=>{e.preventDefault();if(Number(quantity)<=0)return;await onSave({code:code.trim(),description:description.trim(),unit,quantity,waste_percent:waste,notes:notes.trim()||null,work_item_id:null,calculation_type:"MANUAL",calculation_inputs:{},sort_order:initial?.sort_order||0});}}><div><label>Cod</label><input required maxLength={80} value={code} onChange={e=>setCode(e.target.value)}/></div><div><label>Descriere</label><input required maxLength={255} value={description} onChange={e=>setDescription(e.target.value)}/></div><div><label>Unitate</label><select value={unit} onChange={e=>setUnit(e.target.value as Unit)}>{UNITS.map(value=><option key={value}>{value}</option>)}</select></div><div><label>Cantitate</label><input required type="number" min="0.000001" step="0.000001" value={quantity} onChange={e=>setQuantity(e.target.value)}/></div><div><label>Pierderi (%)</label><input required type="number" min="0" max="100" step="0.001" value={waste} onChange={e=>setWaste(e.target.value)}/></div><div className="wide"><label>Note</label><textarea maxLength={2000} value={notes} onChange={e=>setNotes(e.target.value)} placeholder="Observații opționale"/></div><div className="wide toolbar"><button className="primary" disabled={disabled}>Salvează</button><button type="button" className="secondary" onClick={onCancel}>Renunță</button></div></form></div>;
}
