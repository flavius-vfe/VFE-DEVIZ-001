"use client";

import {FormEvent, useEffect, useState} from "react";
import {api} from "../lib/api";

type Mode = "loading" | "setup" | "login" | "dashboard";

export default function Home() {
  const [mode, setMode] = useState<Mode>("loading");
  const [error, setError] = useState("");
  const [projects, setProjects] = useState<any[]>([]);

  async function refresh() {
    setError("");
    try {
      const status = await api("/api/setup/status");
      if (!status.configured) return setMode("setup");
      try {
        await api("/api/auth/me");
        setProjects(await api("/api/projects"));
        setMode("dashboard");
      } catch {
        setMode("login");
      }
    } catch (e:any) {
      setError(e.message);
      setMode("login");
    }
  }

  useEffect(() => { refresh(); }, []);

  if (mode === "loading") return <main><div className="card">Se încarcă...</div></main>;

  return (
    <main>
      <header>
        <div>
          <h1>VFE Deviz</h1>
          <div className="muted">Devize construcții • Ceahlău, Neamț</div>
        </div>
        {mode === "dashboard" && (
          <button className="secondary" onClick={async () => { await api("/api/auth/logout", {method:"POST"}); setMode("login"); }}>
            Deconectare
          </button>
        )}
      </header>
      {error && <div className="card error">{error}</div>}
      {mode === "setup" && <Setup onDone={() => setMode("login")} onError={setError}/>}
      {mode === "login" && <Login onDone={refresh} onError={setError}/>}
      {mode === "dashboard" && <Dashboard projects={projects} onRefresh={refresh} onError={setError}/>}
    </main>
  );
}

function Setup({onDone, onError}:{onDone:()=>void,onError:(s:string)=>void}) {
  const [password, setPassword] = useState("");
  const [serverIp, setServerIp] = useState(
    typeof window !== "undefined" ? window.location.hostname : "192.168.0.50"
  );
  async function submit(e:FormEvent) {
    e.preventDefault();
    try {
      await api("/api/setup", {
        method:"POST",
        body:JSON.stringify({
          username:"administrator",
          password,
          server_ip:serverIp,
          locality:"Ceahlău",
          county:"Neamț",
          vat_rate:"21"
        })
      });
      onDone();
    } catch(e:any) { onError(e.message); }
  }
  return <div className="card">
    <h2>Configurare inițială</h2>
    <p>Introdu manual IP-ul serverului Unraid. TVA implicit: <strong>21%</strong>.</p>
    <form onSubmit={submit}>
      <label>IP server</label>
      <input value={serverIp} onChange={e=>setServerIp(e.target.value)} placeholder="192.168.0.50" required/>
      <label>Utilizator</label><input value="administrator" disabled/>
      <label>Parolă administrator</label>
      <input type="password" minLength={10} value={password} onChange={e=>setPassword(e.target.value)} required/>
      <button className="primary" style={{marginTop:16}}>Finalizează configurarea</button>
    </form>
  </div>;
}

function Login({onDone,onError}:{onDone:()=>void,onError:(s:string)=>void}) {
  const [password, setPassword] = useState("");
  async function submit(e:FormEvent) {
    e.preventDefault();
    try {
      await api("/api/auth/login", {
        method:"POST",
        body:JSON.stringify({username:"administrator", password})
      });
      onDone();
    } catch(e:any) { onError(e.message); }
  }
  return <div className="card">
    <h2>Autentificare</h2>
    <form onSubmit={submit}>
      <label>Utilizator</label><input value="administrator" disabled/>
      <label>Parolă</label><input type="password" value={password} onChange={e=>setPassword(e.target.value)} required/>
      <button className="primary" style={{marginTop:16}}>Autentificare</button>
    </form>
  </div>;
}

function Dashboard({projects,onRefresh,onError}:{projects:any[],onRefresh:()=>void,onError:(s:string)=>void}) {
  const [name, setName] = useState("");
  async function create(e:FormEvent) {
    e.preventDefault();
    try {
      await api("/api/projects", {
        method:"POST",
        body:JSON.stringify({
          name, locality:"Ceahlău", county:"Neamț", default_waste_percent:"5"
        })
      });
      setName("");
      onRefresh();
    } catch(e:any) { onError(e.message); }
  }
  return <>
    <div className="grid">
      <div className="card"><div className="muted">Proiecte</div><div className="value">{projects.length}</div></div>
      <div className="card"><div className="muted">Locație implicită</div><div className="value">Ceahlău</div></div>
      <div className="card"><div className="muted">TVA implicit</div><div className="value">21%</div></div>
    </div>
    <div className="card">
      <h2>Proiect nou</h2>
      <form onSubmit={create}>
        <label>Denumire proiect</label>
        <input value={name} onChange={e=>setName(e.target.value)} placeholder="ex. Casă Ceahlău" required/>
        <button className="primary" style={{marginTop:16}}>Creează proiect</button>
      </form>
    </div>
    <div className="card">
      <h2>Proiecte</h2>
      {projects.length === 0 ? <p className="muted">Nu există proiecte.</p> :
        projects.map(p => <div key={p.id} style={{padding:"10px 0",borderBottom:"1px solid #eee"}}>
          <strong>{p.name}</strong><div className="muted">{p.locality}, {p.county}</div>
        </div>)
      }
    </div>
  </>;
}
