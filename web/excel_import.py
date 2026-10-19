"""Explicit Excel import with transactional preview and no overwrite of existing records."""
import io
import re
from flask import Blueprint, abort, jsonify, request
from openpyxl import load_workbook
from mysql.connector import Error

bp = Blueprint("excel_import", __name__, url_prefix="/api/workflow")
ORDER = ("customers","modelli","schema colori semplice","prodotti_completi","ordini","magazzino","ordiniprodotti")
ALIASES = {
    "clienti":"customers", "customers":"customers",
    "modelli":"modelli", "colori":"schema colori semplice",
    "schema colori semplice":"schema colori semplice",
    "prodotti":"prodotti_completi", "prodotti completi":"prodotti_completi",
    "prodotti_completi":"prodotti_completi",
    "ordini":"ordini","magazzino":"magazzino",
    "righe":"ordiniprodotti","ordiniprodotti":"ordiniprodotti"
}

def normalized(value):
    return re.sub(r"[\s_-]+","",str(value).replace("ï»¿","").lstrip("\ufeff").strip().lower())

def quote(value):
    return chr(96) + value.replace(chr(96),chr(96)*2) + chr(96)

def excel_records(file, expected):
    source=io.BytesIO(file.read())
    wb=load_workbook(source,read_only=True,data_only=True)
    try:
        ws=wb.active
        if ws.max_row>20000:abort(413,"File troppo grande (massimo 20.000 righe)")
        raw=ws.iter_rows(values_only=True)
        headers=next(raw,None)
        if not headers:abort(400,"Excel vuoto")
        original=[normalized(v) for v in headers]
        if not len(original)==len(set(original)):abort(400,"Intestazioni duplicate in Excel")
        indices=[]
        for col in expected:
            key=normalized(col)
            if key not in original:
                abort(400,"Colonna Excel mancante: "+col)
            indices.append(original.index(key))
        records=[]
        for row in raw:
            if not any(cell is not None and str(cell).strip() for cell in row):
                continue
            records.append([row[i] if i<len(row) else None for i in indices])
        return records
    finally:
        wb.close()

@bp.post("/import")
def excel_import():
    apply=request.args.get("apply")=="1"
    if not request.files.getlist("files"):abort(400,"Seleziona uno o più Excel .xlsx")
    if request.content_length and request.content_length>25*1024*1024:
        abort(413,"Caricamento troppo grande")
    from app import db
    conn=db()
    try:
        cursor=conn.cursor()
        sets={}
        for file in request.files.getlist("files"):
            if not file.filename or not file.filename.lower().endswith(".xlsx"):
                abort(400,"Sono accettati soltanto file .xlsx")
            stem=file.filename.rsplit(".",1)[0].lower().strip()
            table=ALIASES.get(stem)
            if table is None:abort(400,"Nome Excel non riconosciuto: "+stem)
            if table in sets:abort(400,"File duplicato per tabella: "+table)
            cursor.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",(table,))
            cols=[r[0] for r in cursor.fetchall()]
            if not cols:abort(409,"Schema non completo: "+table)
            sets[table]=(cols,excel_records(file,cols))
        report=[]
        # Read-only preflight for duplicate keys; do not silently replace or erase records.
        for table in ORDER:
            if table not in sets:continue
            cols,rows=sets[table]
            cursor.execute("SELECT COUNT(*) FROM "+quote(table))
            existing=cursor.fetchone()[0]
            if existing:
                abort(409,"La tabella "+table+" contiene già "+str(existing)+" record: import bloccato per evitare duplicati")
            report.append(dict(table=table,rows=len(rows)))
        # Validate schema constraints in a transaction, then rollback on preview.
        for table in ORDER:
            if table not in sets:continue
            cols,rows=sets[table]
            if not rows:continue
            statement="INSERT INTO "+quote(table)+" ("+",".join(map(quote,cols))+") VALUES ("+",".join(["%s"]*len(cols))+")"
            cursor.executemany(statement,rows)
        if apply:
            conn.commit()
        else:
            conn.rollback()
        return jsonify(validated=True,imported=apply,tables=report,
                       total=sum(x["rows"] for x in report))
    except Error as error:
        conn.rollback()
        abort(409,"I dati Excel non rispettano i vincoli del database (duplicati, collegamenti o formato). "+str(error.msg)[:160])
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
