"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, apiBase } from "../../../../lib/api";
const money = (x: any) =>
  Number(x || 0).toLocaleString("ro-RO", { minimumFractionDigits: 2 });
export default function Page() {
  const { id } = useParams<{ id: string }>();
  const [orders, setOrders] = useState<any[]>([]);
  const [project, setProject] = useState<any>();
  const [selected, setSelected] = useState<any>();
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      setProject(await api(`/api/projects/${id}`));
      setOrders(await api(`/api/projects/${id}/orders`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Eroare.");
    }
  }, [id]);
  useEffect(() => {
    load();
  }, [load]);
  async function status(o: any, s: string) {
    await api(`/api/projects/${id}/orders/${o.id}/status`, {
      method: "POST",
      body: JSON.stringify({ status: s }),
    });
    await load();
  }
  return (
    <main>
      <div className="breadcrumbs">
        <a href="/">Proiecte</a>
        <span>/</span>
        <a href={`/projects/${id}`}>{project?.name}</a>
        <span>/</span>
        <strong>Comenzi materiale</strong>
      </div>
      <h1>Comenzi materiale</h1>
      {error && <div className="error card">{error}</div>}
      {orders.length === 0 ? (
        <div className="empty">Nu există comenzi.</div>
      ) : (
        <div className="card table-wrap">
          <table>
            <thead>
              <tr>
                <th>Nr. comandă</th>
                <th>Furnizor</th>
                <th>Status</th>
                <th>Total cu TVA</th>
                <th>Progres</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => {
                const ordered = o.reconciliation.reduce(
                    (s: number, x: any) => s + Number(x.ordered),
                    0,
                  ),
                  received = o.reconciliation.reduce(
                    (s: number, x: any) => s + Number(x.received_total),
                    0,
                  );
                return (
                  <tr key={o.id}>
                    <td>{o.order_number}</td>
                    <td>{o.supplier_name}</td>
                    <td>{o.status}</td>
                    <td>{money(o.total_gross)}</td>
                    <td>
                      {received} / {ordered} (
                      {ordered ? Math.round((received * 100) / ordered) : 0}%)
                    </td>
                    <td className="toolbar">
                      <button onClick={() => setSelected(o)}>Deschide</button>
                      {o.status === "DRAFT" && (
                        <button onClick={() => status(o, "READY_TO_ORDER")}>
                          Marchează gata de comandă
                        </button>
                      )}
                      {o.status === "READY_TO_ORDER" && (
                        <button onClick={() => status(o, "ORDERED")}>
                          Marchează comandată
                        </button>
                      )}
                      {["DRAFT", "READY_TO_ORDER"].includes(o.status) && (
                        <button className="danger" onClick={() => status(o, "CANCELLED")}>
                          Anulează
                        </button>
                      )}
                      {["ORDERED", "PARTIALLY_DELIVERED"].includes(
                        o.status,
                      ) && (
                        <a href={`/projects/${id}/deliveries`}>
                          Înregistrează livrare
                        </a>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {selected && (
        <section className="card">
          <div className="toolbar push">
            <h2>{selected.order_number}</h2>
            <div>
              <a
                href={`${apiBase()}/api/projects/${id}/orders/${selected.id}/export.pdf`}
              >
                PDF
              </a>{" "}
              <a
                href={`${apiBase()}/api/projects/${id}/orders/${selected.id}/export.xlsx`}
              >
                XLSX
              </a>
            </div>
          </div>
          <p>
            <strong>Furnizor:</strong> {selected.supplier_name}
          </p>
          <table>
            <thead>
              <tr>
                <th>Produs</th>
                <th>Comandat</th>
                <th>Recepționat</th>
                <th>Acceptat</th>
                <th>Deteriorat</th>
                <th>Respins</th>
                <th>Retur</th>
                <th>Rămas de livrat</th>
              </tr>
            </thead>
            <tbody>
              {selected.reconciliation.map((x: any) => (
                <tr key={x.purchase_order_item_id}>
                  <td>{x.description}</td>
                  <td>
                    {x.ordered} {x.unit}
                  </td>
                  <td>{x.received_total}</td>
                  <td>{x.accepted_total}</td>
                  <td>{x.damaged_total}</td>
                  <td>{x.rejected_total}</td>
                  <td>{x.returned_total}</td>
                  <td>
                    {x.remaining_to_receive}
                    <div>{Number(x.progress_percent).toFixed(0)}%</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="results-grid">
            <div>
              Subtotal fără TVA<strong>{money(selected.subtotal_net)}</strong>
            </div>
            <div>
              Transport estimat<strong>{money(selected.transport_cost)}</strong>
            </div>
            <div>
              TVA<strong>{money(selected.vat_total)}</strong>
            </div>
            <div>
              TOTAL CU TVA<strong>{money(selected.total_gross)}</strong>
            </div>
          </div>
          {selected.status === "ORDERED" && (
            <button
              onClick={() =>
                api(`/api/projects/${id}/orders/${selected.id}/revision`, {
                  method: "POST",
                }).then(load)
              }
            >
              Creează revizie
            </button>
          )}
        </section>
      )}
    </main>
  );
}
