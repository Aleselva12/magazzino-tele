"""End to end: create new customer, color, model, product, order from XLS templates."""
import io
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import xlwt

BASE="http://127.0.0.1:8082"
BOUNDARY="LEGACYORDERTEST123"

def workbook(*records):
    wb=xlwt.Workbook()
    ws=wb.add_sheet("COLORE")
    headings=["Cod.Cli.","NOME","IMP.","Q.TA","DESCRITTIVA",
              "SCRITTA PARASOLE","SCRITTA TELE","DATA EVAS.","EVASO"]
    for i,h in enumerate(headings):ws.write(0,i,h)
    for n,rec in enumerate(records,1):
        for col,val in enumerate(rec):
            if val is not None:ws.write(n,col,val)
    buf=io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

def upload(filename,raw,day="2026-10-20",token=None,partial=False):
    def part(key,value,filename=None):
        head=f"--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"{key}\""
        if filename:head+=f"; filename=\"{filename}\""
        return (head+"\r\n\r\n").encode()+value+b"\r\n"
    body=part("date",day.encode())+part("allow_partial",b"true" if partial else b"false")+part("files",raw,filename)
    if token:body+=part("preview_token",token.encode())
    body+=(f"--{BOUNDARY}--\r\n").encode()
    path="/api/workflow/color-orders/"+("apply" if token else "preview")
    req=Request(BASE+path,method="POST",data=body,headers={"Content-Type":"multipart/form-data; boundary="+BOUNDARY})
    try:
        with urlopen(req,timeout=60) as res:return json.load(res)
    except HTTPError as e:
        print('Color workbook endpoint rejected request:',e.code,e.read().decode('utf-8','replace')[:700])
        raise

def fetch(path):
    with urlopen(BASE+path,timeout=30) as r:return json.load(r)

def main():
    old=fetch("/api/workflow/catalog")
    assert len(old["customers"])==1 and old["customers"][0]["code"]=="C00002"
    # Same client reused from the earlier SQL restore test. Another customer
    # must be allocated progressively (with all mandatory columns nonempty).
    data=workbook(
        ["C00002","Rossi O'Connor","M72",3,"TELE MODELLO PROVA","BLU TEST",None,45748,"EVASO"],
        [None,"Cliente Nuovo Test","M99",5,"TELE MODELLO PROVA",None,None,45797,None],
        ["C00002","Rossi O'Connor","MOV",-4,"TELE MODELLO PROVA",None,None,None,None],
    )
    report=upload("BLU NOTTE.xls",data)
    assert report["validated"] and not report["blocked"],report
    assert report["totals"]=={"customers":1,"colors":1,"models":1,"products":1,"orders":2,"lines":2},report
    assert len(fetch("/api/workflow/orders")["rows"])==0
    result=upload("BLU NOTTE.xls",data,token=report["preview_token"])
    assert result["imported"] and result["totals"]["orders"]==2
    cat=fetch("/api/workflow/catalog")
    assert len(cat["customers"])==2
    assert len(cat["colors"])==2
    assert len(cat["models"])==2
    assert len(cat["products"])==2
    new_customer=next(x for x in cat["customers"] if "NUOVO" in x["name"])
    assert new_customer["code"].startswith("C") and int(new_customer["number"])>2
    assert new_customer["code"] and new_customer["number"] and new_customer["name"]
    new_product=next(x for x in cat["products"] if x["color"]=="BLU NOTTE")
    assert new_product["code"] and new_product["model_code"] and new_product["color_code"]
    assert fetch("/api/workflow/orders")["total"]==2
    assert fetch("/api/workflow/orders")["evasi"]==1
    assert all(x["data"]=="2026-10-20" for x in fetch("/api/workflow/orders")["rows"])

    # Same source/row cannot create duplicates on another upload.
    again=upload("BLU NOTTE.xls",data)
    assert again["already_imported"]==2
    assert again["totals"]["orders"]==0

    # Missing model on a positive line must block the whole batch.
    bad=workbook(["C00002","Rossi O'Connor","M101",9,None,None,None,None,None])
    try:
        preview=upload("COLORE SENZA DESCRIZIONE.xls",bad)
        assert not preview["validated"] and preview["blocked"],preview
    except HTTPError as e:
        assert e.code==422
    assert fetch("/api/workflow/orders")["total"]==2
    # Optional partial batch imports only complete lines; no dummy records.
    mixed=workbook(
       [None,"CLIENTE PROVA PARZIALE", "M002", 7,"TELE MODELLO PARZIALE",None,None,None,None],
       [None,"CLIENTE NON IMPORTABILE", "M003", 9,None,None,None,None,None],
    )
    review=upload("VERDE MARINO.xls",mixed,partial=True)
    assert review["validated"] and review["blocked"],review
    assert review["totals"]["orders"]==1,review
    final=upload("VERDE MARINO.xls",mixed,token=review["preview_token"],partial=True)
    assert final["imported"] and final["totals"]["orders"]==1
    after=fetch("/api/workflow/catalog")
    assert not any("NON IMPORTABILE" in c["name"] for c in after["customers"])
    assert fetch("/api/workflow/orders")["total"]==3
    print("Legacy XLS -> customer, color, model, product, order, mandatory IDs, idempotence and validation: PASS")

if __name__=="__main__":
    main()
