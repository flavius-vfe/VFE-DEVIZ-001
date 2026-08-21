from io import BytesIO
from zipfile import ZipFile,ZIP_DEFLATED
from xml.sax.saxutils import escape
from .procurement_exports import _sheet

def _xlsx(sheets):
    names=list(sheets);out=BytesIO();count=len(names)
    with ZipFile(out,"w",ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,count+1))+'</Types>')
        z.writestr("_rels/.rels",'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml",'<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(f'<sheet name="{escape(n)}" sheetId="{i}" r:id="rId{i}"/>' for i,n in enumerate(names,1))+'</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,count+1))+'</Relationships>')
        for i,name in enumerate(names,1):z.writestr(f"xl/worksheets/sheet{i}.xml",_sheet(sheets[name]))
    return out.getvalue()

def _pdf(lines):
    safe=lambda v:str(v).replace("\\","\\\\").replace("(","\\(").replace(")","\\)")
    content="BT /F1 10 Tf 40 800 Td "+" ".join(f'({safe(x)}) Tj 0 -16 Td' for x in lines)+" ET";objs=["<< /Type /Catalog /Pages 2 0 R >>","<< /Type /Pages /Kids [3 0 R] /Count 1 >>","<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>","<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",f"<< /Length {len(content.encode())} >>\nstream\n{content}\nendstream"]
    data=b"%PDF-1.4\n";offsets=[0]
    for i,obj in enumerate(objs,1):offsets.append(len(data));data+=f"{i} 0 obj\n{obj}\nendobj\n".encode()
    x=len(data);return data+f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode()+b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets[1:])+f"trailer << /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF".encode()

def quote_pdf(q):return _pdf(["OFERTA FURNIZOR",f'Numar: {q.get("quote_number") or "-"}',f'Furnizor: {q["supplier_name"]}']+[f'{x["description"]} | {x["quantity"]} {x["unit"]} | {x["line_total_gross"]} RON' for x in q["items"]]+[f'TOTAL CU TVA: {q["total_gross"]} RON'])
def quote_xlsx(q):return _xlsx({"Ofertă":[["Număr",q.get("quote_number")],["Furnizor",q["supplier_name"]],["Total cu TVA",q["total_gross"]]],"Produse":[["Material","SKU","Cantitate","UM","Preț net","TVA","Total"]]+[[x["description"],x.get("supplier_sku"),x["quantity"],x["unit"],x["unit_price_net"],x["vat_rate"],x["line_total_gross"]] for x in q["items"]],"Rezumat":[["Subtotal",q["subtotal_net"]],["Discount",q["discount_total_net"]],["Transport",q["transport_net"]],["TVA",q["vat_total"]],["TOTAL",q["total_gross"]]]})
def order_pdf(o):return _pdf(["COMANDA MATERIALE",f'Proiect: {o["project_name"]}',f'Furnizor: {o["supplier_name"]}',f'Numar: {o["order_number"]}',f'Livrare: {o["delivery_address"]}']+[f'{x["description"]} | {x["quantity"]} {x["unit"]} | {x["line_total_gross"]} RON' for x in o["items"]]+[f'TOTAL CU TVA: {o["total_gross"]} RON'])
def order_xlsx(o):return _xlsx({"Comandă":[["Nr. comandă",o["order_number"]],["Furnizor",o["supplier_name"]],["Livrare",o["delivery_address"]]],"Produse":[["Produs","SKU","Cantitate","UM","Preț","Discount","Total"]]+[[x["description"],x.get("sku"),x["quantity"],x["unit"],x["unit_price_net"],x["discount_net"],x["line_total_gross"]] for x in o["items"]],"Rezumat":[["Subtotal fără TVA",o["subtotal_net"]],["Discount",o["discount_total"]],["Transport",o["transport_cost"]],["TVA",o["vat_total"]],["TOTAL CU TVA",o["total_gross"]]]})
