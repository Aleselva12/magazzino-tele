"""SQL backup: actual historical dump parser, safe restore, export roundtrip."""
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
from sql_backup import read_backup
from excel_import import stock_rows

URL = "http://127.0.0.1:8082"
BOUNDARY = "SQL_BACKUP_TEST_BOUNDARY"

def upload_sql(raw, token=None):
    body = (f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="file"; filename="backup.sql"\r\n'
            "Content-Type: application/sql\r\n\r\n").encode() + raw + b"\r\n"
    if token is not None:
        body += (f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="preview_token"\r\n\r\n'
                 + token + "\r\n").encode()
    body += (f"--{BOUNDARY}--\r\n").encode()
    endpoint = "/api/workflow/sql-backup/import" if token else "/api/workflow/sql-backup/preview"
    req = Request(URL + endpoint, data=body, method="POST",
                  headers={"Content-Type": "multipart/form-data; boundary=" + BOUNDARY})
    with urlopen(req, timeout=180) as response:
        return json.load(response)

def get_json(path):
    with urlopen(URL + path, timeout=20) as response:
        return json.load(response)

def main():
    # Uses original SQL already present in the repository, not private new uploads.
    old = Path("backup/2025-08-17_18-16-33/database_backup_2025-08-17_18-16-33.sql").read_bytes()
    groups, ddl = read_backup(old)
    assert len(groups["customers"]["rows"]) > 10000
    assert len(groups["modelli"]["rows"]) >= 30
    assert ddl >= 7, ddl

    duplicates = [["1-1154",1,"SMECA",1154,"GIALLO"],
                  ["1-1195",1,"SMECA",1195,"GIALLO"]]
    matrix = ("matrix",["","SMECA"],[["GIALLO",""]],"magazzino.csv")
    assert stock_rows(matrix, duplicates, None, None) == []
    try:
        stock_rows(("matrix",["","SMECA"],[["GIALLO","12"]],"x.csv"),duplicates,None,None)
        raise AssertionError("Ambiguous stock accepted")
    except ValueError as err:
        assert "più codici" in str(err)

    # Previous E2E script resets the disposable DB.
    assert get_json("/api/workflow/catalog")["customers"] == []
    fixture = """-- MySQL-compatible SQL query file
    SET NAMES utf8mb4;
    INSERT INTO §customers§ (§ï»¿codiceunivoco§, §CoF§, §codice§, §descrizione§)
      VALUES ('C00002','C',2,'Rossi O''Connor');
    INSERT INTO §modelli§ (§ï»¿codice modello§, §MODELLO§) VALUES (1,'SMECA');
    INSERT INTO §schema colori semplice§ (§ï»¿Codice colore§, §Nome Colore§) VALUES (8,'BLU');
    INSERT INTO §prodotti_completi§
       (§Codice Prodotto§, §Codice Modello§, §Nome Modello§, §Codice Colore§, §Nome Colore§)
       VALUES ('1-8', 1,'SMECA',8,'BLU');
    """.replace("§",chr(96)).encode("utf-8")
    preview=upload_sql(fixture)
    assert preview["validated"] and not preview["imported"]
    assert preview["total"]==4,preview
    assert get_json("/api/workflow/catalog")["customers"]==[]
    applied=upload_sql(fixture,preview["preview_token"])
    assert applied["imported"] and applied["total"]==4
    assert len(get_json("/api/workflow/catalog")["products"])==1

    with urlopen(URL+"/api/workflow/sql-backup/export",timeout=40) as response:
        exported=response.read()
        assert "attachment" in response.headers.get("Content-Disposition","")
    contents,ddl=read_backup(exported)
    assert len(contents["customers"]["rows"])==1
    assert len(contents["prodotti_completi"]["rows"])==1
    assert ddl==7
    try:
        upload_sql(b"DELETE FROM customers;")
        raise AssertionError("Unsafe SQL accepted")
    except HTTPError as e:
        assert e.code==422
    print("SQL: historical dump parser, preview/import, export and safety: PASS")

if __name__=="__main__":
    main()
