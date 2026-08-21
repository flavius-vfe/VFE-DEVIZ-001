from .commercial_exports import _pdf,_xlsx

def delivery_pdf(d):
    return _pdf(["PROCES VERBAL DE RECEPTIE",f'Proiect: {d["project_name"]}',f'Furnizor: {d["supplier_name"]}',f'Comanda: {d["order_number"]}',f'Aviz: {d.get("delivery_note_number") or "-"}',f'Data: {d["delivery_date"]}']+[f'{x["description"]} | comandat {x["quantity_ordered"]} | primit {x["quantity_received"]} | acceptat {x["quantity_accepted"]} | deteriorat {x["quantity_damaged"]} | respins {x["quantity_rejected"]} | lipsa {x["quantity_missing"]}' for x in d["items"]]+[f'Probleme: {len(d["issues"])}',f'Observatii: {d.get("notes") or "-"}'])

def delivery_xlsx(d):
    return _xlsx({"Recepție":[["Proiect",d["project_name"]],["Furnizor",d["supplier_name"]],["Comandă",d["order_number"]],["Aviz",d.get("delivery_note_number")],["Data",d["delivery_date"]]],"Produse":[["Produs","Comandat","Așteptat","Primit","Acceptat","Deteriorat","Respins","Lipsă","Preț real","Sursa valorii"]]+[[x["description"],x["quantity_ordered"],x["quantity_expected"],x["quantity_received"],x["quantity_accepted"],x["quantity_damaged"],x["quantity_rejected"],x["quantity_missing"],x["effective_unit_price_gross"],x["value_source"]] for x in d["items"]],"Probleme":[["Tip","Cantitate","Descriere","Status"]]+[[x["issue_type"],x.get("quantity"),x["description"],x["status"]] for x in d["issues"]],"Rezumat":[["Transport estimat",d["transport_estimated"]],["Transport real",d.get("transport_cost_actual")],["Diferență transport",d.get("transport_variance")],["Valoare recepționată",d["received_value_gross"]]]})

def return_pdf(r):
    return _pdf(["DOCUMENT RETUR MATERIALE",f'Proiect: {r["project_name"]}',f'Furnizor: {r["supplier_name"]}',f'Numar: {r["return_number"]}',f'Motiv: {r["reason"]}']+[f'{x["description"]} | {x["quantity"]} {x["unit"]} | rambursare {x.get("actual_refund_gross") or x.get("expected_refund_gross") or 0}' for x in r["items"]]+[f'Rambursat: {r.get("refund_amount_gross") or 0} RON'])

def return_xlsx(r):
    return _xlsx({"Retur":[["Proiect",r["project_name"]],["Furnizor",r["supplier_name"]],["Număr",r["return_number"]],["Motiv",r["reason"]],["Status",r["status"]]],"Produse":[["Produs","SKU","Cantitate","UM","Rambursare estimată","Rambursare reală"]]+[[x["description"],x.get("sku"),x["quantity"],x["unit"],x.get("expected_refund_gross"),x.get("actual_refund_gross")] for x in r["items"]],"Rezumat":[["Rambursare totală",r.get("refund_amount_gross") or 0]]})
