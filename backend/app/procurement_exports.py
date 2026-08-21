from __future__ import annotations
from io import BytesIO
from zipfile import ZipFile,ZIP_DEFLATED
from xml.sax.saxutils import escape

def _sheet(rows):
    body=[]
    for ri,row in enumerate(rows,1):
        cells=[]
        for ci,value in enumerate(row,1):
            n=ci;letters=""
            while n:n,rem=divmod(n-1,26);letters=chr(65+rem)+letters
            cells.append(f'<c r="{letters}{ri}" t="inlineStr"><is><t>{escape(str(value if value is not None else ""))}</t></is></c>')
        body.append(f'<row r="{ri}">{"".join(cells)}</row>')
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join(body)+'</sheetData></worksheet>'

def shopping_xlsx(plan):
    names=["Rezumat","Dedeman","MatHaus","Materiale","Comparație"];by={n:[] for n in names};by["Rezumat"]=[["Furnizor","Produse","Transport","Total livrat"]]+[[x["supplier_code"],x["subtotal_gross"],x["delivery_cost_gross"] if x["delivery_cost_gross"] is not None else "Necunoscut",x["landed_total_gross"] if x["landed_total_gross"] is not None else "Necunoscut"] for x in plan["supplier_totals"]]
    header=["Produs","SKU","Necesar","Ambalaj","Nr. pachete","Cantitate cumpărată","Preț","Subtotal","Stoc","Ultima verificare","Link produs"]
    for supplier in ("Dedeman","MatHaus"):by[supplier]=[header]+[[x["product_name"],x["supplier_sku"],x["required_quantity"],f'{x["package_quantity"]} {x["package_unit"]}',x["packages_to_buy"],x["purchased_quantity"],x["unit_package_price_gross"],x["product_subtotal_gross"],x["stock_status"],x["price_checked_at"],x["product_url"]] for x in plan["items"] if (x.get("supplier_code") or x.get("supplier_name","")).lower()==supplier.lower()]
    by["Materiale"]=[["Material","Necesar","Unitate","Furnizor","Produs"]]+[[x["material_id"],x["required_quantity"],x["required_unit"],x.get("supplier_code") or x.get("supplier_name"),x["product_name"]] for x in plan["items"]]
    by["Comparație"]=[["Strategie","Total livrat"],[plan["strategy"],plan["landed_total_gross"]]]
    out=BytesIO()
    with ZipFile(out,"w",ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,6))+'</Types>')
        z.writestr("_rels/.rels",'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml",'<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(f'<sheet name="{escape(n)}" sheetId="{i}" r:id="rId{i}"/>' for i,n in enumerate(names,1))+'</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,6))+'</Relationships>')
        for i,n in enumerate(names,1):z.writestr(f"xl/worksheets/sheet{i}.xml",_sheet(by[n]))
    return out.getvalue()

def shopping_pdf(plan):
    lines=["LISTA DE CUMPARATURI",f'Strategie: {plan["strategy"]}']
    for total in plan["supplier_totals"]:
        lines += [f'FURNIZOR: {total["supplier_code"]}']+[f'{x["product_name"]} | {x["supplier_sku"]} | {x["packages_to_buy"]} pachete | {x["product_subtotal_gross"]} RON' for x in plan["items"] if x["supplier_id"]==total["supplier_id"]]+[f'Produse: {total["subtotal_gross"]} RON',f'Transport: {total["delivery_cost_gross"] if total["delivery_cost_gross"] is not None else "Necunoscut"}',f'TOTAL LIVRAT: {total["landed_total_gross"] if total["landed_total_gross"] is not None else "Necunoscut"}']
    def pdf_text(value):return value.replace("\\","\\\\").replace("(","\\(").replace(")","\\)")
    content="BT /F1 10 Tf 40 800 Td "+" ".join(f'({pdf_text(s)}) Tj 0 -16 Td' for s in lines)+" ET"
    objs=["<< /Type /Catalog /Pages 2 0 R >>","<< /Type /Pages /Kids [3 0 R] /Count 1 >>","<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>","<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",f"<< /Length {len(content.encode())} >>\nstream\n{content}\nendstream"]
    data=b"%PDF-1.4\n";offsets=[0]
    for i,obj in enumerate(objs,1):offsets.append(len(data));data+=f"{i} 0 obj\n{obj}\nendobj\n".encode()
    x=len(data);data+=f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode()+b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets[1:])+f"trailer << /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF".encode();return data
