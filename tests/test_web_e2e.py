"""End-to-end smoke: XLSX, historical CSV archive, orders and stock, on disposable DB."""
import io
import json
import zipfile
from urllib.request import Request, urlopen
from openpyxl import Workbook

URL="http://127.0.0.1:8082"
BOUNDARY="TELE_TEST_BOUNDARY"

def call(path, method="GET", body=None):
    raw=json.dumps(body,ensure_ascii=False).encode() if body is not None else None
    req=Request(URL+path,data=raw,method=method,headers={"Content-Type":"application/json"})
    with urlopen(req,timeout=60) as response:return json.load(response)

def upload(filename,contents,token=None):
    parts=[]
    def field(name,value,filename=None):
        part=f"--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"{name}\""
        if filename:part+=f"; filename=\"{filename}\""
        part+="\r\n\r\n"
        return part.encode()+value+b"\r\n"
    parts.append(field("files",contents,filename))
    if token:parts.append(field("preview_token",token.encode()))
    payload=b"".join(parts)+f"--{BOUNDARY}--\r\n".encode()
    req=Request(URL+"/api/workflow/import"+("?apply=1" if token else ""),
                data=payload,method="POST",headers={"Content-Type":"multipart/form-data; boundary="+BOUNDARY})
    with urlopen(req,timeout=90) as response:return json.load(response)

def import_checked(name,content):
    preview=upload(name,content)
    assert preview["validated"] and not preview["imported"],preview
    result=upload(name,content,preview["preview_token"])
    assert result["validated"] and result["imported"],result
    return result

def main():
    assert call("/health")["status"]=="ok"
    cat=call("/api/workflow/catalog")
    assert all(not cat[k] for k in ("customers","models","colors","products"))
    # Spreadsheet import must recognize the accidental historical BOM in SQL column names.
    wb=Workbook();ws=wb.active
    ws.append(["codiceunivoco","CoF","codice","descrizione"])
    ws.append(["C00001","C",1,"Cliente test"])
    xlsx=io.BytesIO();wb.save(xlsx)
    assert import_checked("customers.xlsx",xlsx.getvalue())["total"]==1
    assert len(call("/api/workflow/catalog")["customers"])==1

    # A historical bundle includes a redundant conflicting color CSV, a stock matrix
    # with blank cells, and an unfinished products.csv export.
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,"w") as z:
        z.writestr("123/modelli.csv","codice modello;MODELLO\n1;SMECA TEST\n")
        z.writestr("123/schema colori semplice.csv","Codice colore;Nome Colore\n8;BLU TEST\n")
        z.writestr("123/schema colori.csv",
                   "Codice colore;Nome Colore;Caratteristica;traforato;Azienda;Smeca;Sp;Anf;Regista&Sdraio\n9;BLU TEST;Standard;0;;1;1;1;1\n")
        z.writestr("123/prodotti_completi.csv",
                   "Codice Prodotto;Codice Modello;Nome Modello;Codice Colore;Nome Colore\n1-8;1;SMECA TEST;8;BLU TEST\n")
        z.writestr("123/magazzino.csv",";SMECA TEST\nBLU TEST;\n")
        z.writestr("123/prodotti.csv","codiceProdotto;codice colore;Modello\n;8;S\n")
        z.writestr("123/ordini.csv","codice ordine;codiceunivoco;data oridne\n")
        z.writestr("123/Prodottiordini.csv","codice ordine;codiceunivoco;data oridne\n")
    result=import_checked("123.zip",archive.getvalue())
    assert any("discordanti" in n for n in result["notes"]),result
    assert len(call("/api/workflow/catalog")["products"])==1
    assert len(call("/api/workflow/catalog")["colors"])==1

    order=call("/api/workflow/orders","POST",{"customer":"C00001","date":"2026-10-19",
         "lines":[{"code":"1-8","quantity":5}]})
    identifier=order["id"]
    assert call("/api/workflow/orders")["total"]==1
    assert call("/api/workflow/orders?color=BLU%20TEST")["total"]==1
    assert call("/api/workflow/orders/"+str(identifier))["lines"][0]["quantity"]==5
    call("/api/workflow/orders/"+str(identifier)+"/status","PATCH",{"evaso":True})
    assert call("/api/workflow/orders")["evasi"]==1
    call("/api/workflow/inventory/1-8","PATCH",{"quantity":12})
    assert any(row["quantity"]==12 for row in call("/api/workflow/inventory")["rows"])
    # Reset is disabled by default and must never be exposed on production.
    assert call("/api/workflow/dev-reset/status")["enabled"] is False
    print("E2E Excel XLSX + ZIP CSV + BOM + divergent colors + empty stock + orders: PASS")

if __name__=="__main__":main()
