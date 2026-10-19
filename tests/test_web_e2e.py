"""Integration smoke test for the disposable GitHub Actions MySQL container."""
import io
import json
from urllib.request import Request, urlopen
from openpyxl import Workbook

URL="http://127.0.0.1:8082"

def call(path, method="GET", body=None, content_type="application/json"):
    raw=json.dumps(body,ensure_ascii=False).encode("utf-8") if body is not None else None
    req=Request(URL+path,data=raw,method=method,
                headers={"Content-Type":content_type})
    with urlopen(req,timeout=20) as response:
        return json.load(response)

def main():
    assert call("/health")["status"]=="ok"
    options=call("/api/workflow/catalog")
    assert all(not options[k] for k in ("customers","models","colors","products")), options
    wb=Workbook()
    sh=wb.active
    sh.append(["ï»¿codiceunivoco","CoF","codice","descrizione"])
    sh.append(["C00001","C",1,"Cliente di collaudo"])
    stream=io.BytesIO()
    wb.save(stream)
    boundary="TESTBOUNDARY12345"
    body=(f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"customers.xlsx\"\r\n"
          "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n").encode()+stream.getvalue()+f"\r\n--{boundary}--\r\n".encode()
    for apply in (False,True):
        req=Request(URL+"/api/workflow/import"+("?apply=1" if apply else ""),
                data=body,method="POST",headers={"Content-Type":"multipart/form-data; boundary="+boundary})
        with urlopen(req,timeout=30) as res:result=json.load(res)
        assert result["validated"] and result["imported"] is apply
    assert len(call("/api/workflow/catalog")["customers"])==1
    call("/api/modelli","POST",{"ï»¿codice modello":1,"MODELLO":"SMECA TEST"})
    call("/api/colori","POST",{"ï»¿Codice colore":8,"Nome Colore":"BLU TEST"})
    call("/api/prodotti","POST",{"Codice Prodotto":"1-8","Codice Modello":1,
        "Nome Modello":"SMECA TEST","Codice Colore":8,"Nome Colore":"BLU TEST"})
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
    print("E2E web + MySQL + Excel preview/import + order + inventory: PASS")

if __name__=="__main__":main()
