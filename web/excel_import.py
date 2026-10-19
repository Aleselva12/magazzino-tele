"""Validated imports of historical CSV, XLS, XLSX and ZIP bundles.

The database layout is *legacy* (seven real tables), not the illustrative ERD.
Only known relational sources are written. Color-specific legacy .xls workbooks
are inspected but never misinterpreted as flat database tables.
"""
import csv
import hashlib
import hmac
import io
import os
from pathlib import PurePosixPath
import re
import time
import zipfile

from flask import Blueprint, abort, jsonify, request
from mysql.connector import Error
from openpyxl import load_workbook
import xlrd

bp = Blueprint("excel_import", __name__, url_prefix="/api/workflow")
ORDER = ("customers", "modelli", "schema colori semplice", "prodotti_completi",
         "ordini", "magazzino", "ordiniprodotti")
ALIASES = {
    "customers": "customers", "clienti": "customers",
    "modelli": "modelli", "models": "modelli",
    "schema colori semplice": "schema colori semplice", "colori": "schema colori semplice",
    "schema colori": "schema colori semplice",
    "prodotti completi": "prodotti_completi", "prodotti_completi": "prodotti_completi",
    "ordini": "ordini", "orders": "ordini",
    "magazzino": "magazzino", "inventario": "magazzino",
    "ordiniprodotti": "ordiniprodotti", "prodottiordini": "ordiniprodotti", "righe": "ordiniprodotti",
}
MAX_BYTES = 80 * 1024 * 1024
MAX_EXPANDED = 100 * 1024 * 1024
MAX_FILES = 300
MAX_ROWS = 25000

def norm(value):
    return re.sub(r"[\s_-]+", "", str(value or "").replace("ï»¿", "").lstrip("\ufeff").strip().lower())

def q(value):
    return chr(96) + value.replace(chr(96), chr(96) * 2) + chr(96)

def sheet_values(name, raw):
    """Read first worksheet with actual data rows, treating XLS and XLSX separately."""
    name = name.lower()
    if name.endswith(".xlsx"):
        with io.BytesIO(raw) as stream:
            wb = load_workbook(stream, read_only=True, data_only=True)
            try:
                ws = wb.active
                if ws.max_row > MAX_ROWS + 1 or ws.max_column > 100:
                    raise ValueError("Foglio troppo grande")
                return [list(r) for r in ws.iter_rows(values_only=True)]
            finally: wb.close()
    if name.endswith(".xls"):
        book = xlrd.open_workbook(file_contents=raw, on_demand=True)
        try:
            ws = book.sheet_by_index(0)
            if ws.nrows > MAX_ROWS + 1 or ws.ncols > 100:
                raise ValueError("Foglio troppo grande")
            return [ws.row_values(i) for i in range(ws.nrows)]
        finally: book.release_resources()
    # CSV: Excel Italy usually writes semicolon, UTF-8 BOM; tolerate cp1252.
    try: text = raw.decode("utf-8-sig")
    except UnicodeDecodeError: text = raw.decode("cp1252")
    try: dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t")
    except csv.Error: dialect = csv.excel
    return list(csv.reader(io.StringIO(text), dialect=dialect))

def upload_parts(files):
    """Never unpack paths on disk: enumerate safe ZIP members entirely in memory."""
    collected = []
    sizes = 0
    fingerprint = hashlib.sha256()
    def add(name, data):
        nonlocal sizes
        sizes += len(data)
        if sizes > MAX_EXPANDED or len(collected) >= MAX_FILES:
            abort(413, "Archivio troppo grande (limite 100 MB/300 file)")
        fingerprint.update(name.encode("utf-8", "replace") + b"\0")
        fingerprint.update(hashlib.sha256(data).digest())
        collected.append((name, data))
    for file in files:
        name = PurePosixPath(file.filename or "").name
        if not name or name.startswith("."): abort(400, "File non valido")
        raw = file.read()
        if len(raw) > MAX_BYTES: abort(413, "File troppo grande")
        if name.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    members = [m for m in archive.infolist() if not m.is_dir()
                               and not PurePosixPath(m.filename).name.startswith(".")]
                    if len(members) + len(collected) > MAX_FILES: abort(413, "Troppi file nell'archivio")
                    for member in members:
                        # No symlinks and no encrypted ZIP. No path traversal/extraction.
                        if member.flag_bits & 1 or (member.external_attr >> 16) & 0o170000 == 0o120000:
                            abort(400, "Archivio con file non consentiti")
                        if member.file_size > MAX_BYTES or sizes + member.file_size > MAX_EXPANDED:
                            abort(413, "Archivio espanso troppo grande")
                        inner = PurePosixPath(member.filename).name
                        if inner and inner.lower().endswith((".csv",".xls",".xlsx")):
                            add(inner, archive.read(member))
            except (zipfile.BadZipFile, RuntimeError):
                abort(400, "Archivio ZIP non leggibile")
        elif name.lower().endswith((".csv",".xls",".xlsx")):
            add(name, raw)
        else: abort(400, "Formati ammessi: .csv, .xls, .xlsx, .zip")
    return collected, fingerprint.hexdigest()

def preview_signature(digest, expiry):
    secret = os.environ["TELE_DB_PASSWORD"].encode()
    msg = (str(expiry) + ":" + digest).encode()
    return str(expiry) + ":" + hmac.new(secret, msg, hashlib.sha256).hexdigest()

def validate_receipt(token, digest):
    try:
        expiry, signature = token.split(":", 1)
        exp = int(expiry)
        expected = preview_signature(digest, exp).split(":", 1)[1]
        return int(time.time()) <= exp <= int(time.time()) + 3600 and hmac.compare_digest(expected,signature)
    except (ValueError, AttributeError):return False

def normalize_rows(name, rows):
    # A per-color stock workbook has no table layout: never guess from formulas.
    if not rows: return [], []
    headers = [norm(x) for x in rows[0]]
    rest = []
    for row in rows[1:]:
        if any(v is not None and str(v).strip() for v in row):
            rest.append(row)
    if len(rest) > MAX_ROWS:raise ValueError("Troppi record")
    return headers, rest

def mapped_rows(table, headers, rows, columns):
    cols = [norm(c) for c in columns]
    # Empty order extracts: keep empty and do not infer historical structure.
    if not rows:
        return []
    mapping = {}
    for col in cols:
        matching = [i for i,v in enumerate(headers) if v == col]
        if len(matching) != 1: raise ValueError("Intestazione obbligatoria o duplicata: " + col)
        mapping[col] = matching[0]
    out=[]
    for row in rows:
        cells=[]
        for col in cols:
            v = row[mapping[col]] if mapping[col] < len(row) else None
            if isinstance(v,str):
                v=v.strip()
                if not v:v=None
            cells.append(v)
        out.append(cells)
    return out

def parse_sources(parts, metadata):
    sources={}
    notices=[]
    extra=[]
    for name,raw in parts:
        stem = name.rsplit(".",1)[0].lower().strip()
        table = ALIASES.get(stem)
        # Inspect the format of unstructured legacy workbooks as well: a corrupt
        # .xls should be reported as unreadable, not silently accepted.
        if table is None:
            if name.lower().endswith(".xls"):
                try:
                    wb = xlrd.open_workbook(file_contents=raw, on_demand=True)
                    ws = wb.sheet_by_index(0)
                    if ws.nrows > MAX_ROWS + 1 or ws.ncols > 100:
                        raise ValueError("Foglio troppo grande")
                    shape = f" ({ws.nrows} righe, {ws.ncols} colonne)"
                    wb.release_resources()
                except (xlrd.XLRDError, ValueError, IndexError) as e:
                    raise ValueError("Il file XLS non è leggibile: " + name + " — " + str(e)[:90])
                extra.append((name,"Scheda colore XLS leggibile"+shape+"; non è una tabella MySQL e non viene convertita arbitrariamente in giacenze."))
                continue
            if stem == "0001 magazzino tele schema colori":
                extra.append((name,"Mappa colori estesa: 143 voci con codici duplicati/non numerici. Richiede normalizzazione prima di unirla all'anagrafica relazionale."))
            elif stem in ("prodotti","00123.xls"):
                extra.append((name,"Foglio ausiliario, non è la tabella prodotti_completi canonica."))
            else:
                extra.append((name,"Scheda Excel per colore: formato non relazionale; conservata come sorgente, non trasformata in giacenze."))
            continue
        try:
            headers, rows = normalize_rows(name, sheet_values(name, raw))
        except (ValueError, TypeError, xlrd.XLRDError, zipfile.BadZipFile) as e:
            raise ValueError("Impossibile leggere " + name + ": " + str(e)[:120])
        if table == "schema colori semplice" and stem == "schema colori":
            # Extended 131-row CSV includes metadata not in legacy SQL table.
            notices.append("schema colori.csv: importati codice e nome; attributi aggiuntivi non ancora salvati.")
        if table == "magazzino" and headers and headers[0] == "":
            # Process only nonempty numeric stock cells: empty *does not* mean 0.
            if "magazzino" in sources: raise ValueError("Più di una sorgente magazzino")
            sources["magazzino"]=("matrix",headers,rows,name)
            continue
        cols=metadata[table]
        if table=="schema colori semplice":
            code=next((i for i,h in enumerate(headers) if h=="codicecolore"),None)
            color=next((i for i,h in enumerate(headers) if h=="nomecolore"),None)
            if code is None or color is None: raise ValueError("Colori senza codice/nome")
            entries=[[row[code],row[color]] for row in rows]
            if table in sources:
                prev=sources[table][1]
                same = {(str(a).strip(),str(b).strip()) for a,b in entries} == {(str(a).strip(),str(b).strip()) for a,b in prev}
                if not same:
                    notices.append("ATTENZIONE: i due elenchi colori hanno codici discordanti. Uso 'schema colori semplice.csv', coerente con prodotti_completi.csv.")
                else:
                    notices.append("Due elenchi colori equivalenti: il secondo viene ignorato.")
                if stem == "schema colori semplice":
                    sources[table]=("rows",entries,name)
                continue
            sources[table]=("rows",entries,name)
            continue
        if table == "customers" and stem=="00123.xls":
            extra.append((name,"Elenco anagrafica alternativo: usare customers.csv per conservare gli identificativi degli ordini."))
            continue
        if table in sources: raise ValueError("Più file per la stessa tabella: "+table)
        if table == "magazzino" and not headers:
            sources[table]=("rows",[],name);continue
        if table in ("ordini","ordiniprodotti") and not rows:
            sources[table]=("rows",[],name);continue
        # A normal relational export must match all DB column headings (but
        # can omit nullable fields -- use the active DB schema for those).
        sources[table]=("rows",mapped_rows(table,headers,rows,cols),name)
    return sources,extra,notices

def stock_rows(matrix, products, model_labels, color_labels):
    _kind,headers,rows,_name=matrix
    by_pair={}
    for code,model_code,model,color_code,color in products:
        key=(norm(model),norm(color))
        if key in by_pair:raise ValueError("Prodotti con modello/colore duplicati")
        by_pair[key]=str(code).strip()
    output=[]
    for row in rows:
        color_name=norm(row[0] if row else "")
        for i,heading in enumerate(headers[1:],1):
            raw=row[i] if i<len(row) else None
            if raw is None or str(raw).strip()=="":continue
            key=(norm(heading),color_name)
            if key not in by_pair:
                raise ValueError("Giacenza senza prodotto corrispondente: " + str(heading)[:45])
            try:
                # Ignore formula literals; only confirmed numeric quantities.
                value=float(raw)
                if not value.is_integer():raise ValueError()
                qty=int(value)
                if abs(qty)>1000000:raise ValueError()
            except (TypeError,ValueError):
                raise ValueError("Giacenza non numerica in "+str(heading)[:40])
            output.append([by_pair[key],qty])
    return output

@bp.post("/import")
def excel_import():
    if request.content_length and request.content_length > MAX_BYTES:abort(413,"Caricamento troppo grande (80 MB)")
    files=request.files.getlist("files")
    if not files:abort(400,"Seleziona file CSV, Excel o ZIP")
    apply=request.args.get("apply")=="1"
    parts,digest=upload_parts(files)
    if not parts:abort(400,"Nessun file tabellare trovato")
    if apply and not validate_receipt(request.form.get("preview_token"),digest):
        abort(409,"Prima controlla gli stessi file con Anteprima, poi conferma entro un'ora.")
    from app import db
    conn=db()
    try:
        cursor=conn.cursor()
        metadata={}
        for table in ORDER:
            cursor.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",(table,))
            metadata[table]=[r[0] for r in cursor.fetchall()]
            if not metadata[table]:abort(503,"Schema MySQL incompleto: "+table)
        sources,extras,notices=parse_sources(parts,metadata)
        if not sources:
            return jsonify(validated=False,imported=False,files_reviewed=len(parts),warnings=extras,
                           message="Nessuna tabella relazionale riconosciuta. Le schede per singolo colore richiedono una mappatura specifica.")
        if "magazzino" in sources and sources["magazzino"][0]=="matrix":
            if "prodotti_completi" not in sources:
                raise ValueError("Per la matrice magazzino serve anche prodotti_completi.csv nello stesso caricamento")
            sources["magazzino"]=("rows",stock_rows(sources["magazzino"],sources["prodotti_completi"][1],None,None),"magazzino.csv")
        report=[]
        for table in ORDER:
            if table not in sources:continue
            cursor.execute("SELECT COUNT(*) FROM "+q(table))
            existing=int(cursor.fetchone()[0])
            if existing:
                abort(409,table+" contiene già "+str(existing)+" record. Importazione sospesa, nessuna sovrascrittura.")
            records=sources[table][1]
            # If products are supplied but colors or models already exist on server,
            # MySQL FK validation ensures references remain coherent.
            report.append({"table":table,"rows":len(records),"source":sources[table][2]})
        for table in ORDER:
            if table not in sources:continue
            records=sources[table][1]
            if not records:continue
            cols=metadata[table]
            # colors reduced 9-col CSV -> 2 SQL cols; matrix inventory -> two SQL cols.
            query="INSERT INTO "+q(table)+" ("+",".join(map(q,cols))+") VALUES ("+",".join(["%s"]*len(cols))+")"
            cursor.executemany(query, records)
        if apply:conn.commit()
        else:conn.rollback()
        return jsonify(validated=True,imported=apply,files_reviewed=len(parts),tables=report,
                       total=sum(x["rows"] for x in report),warnings=extras[:200],notes=notices,
                       preview_token=None if apply else preview_signature(digest,int(time.time())+3600))
    except Error as error:
        conn.rollback()
        abort(409,"Dati non compatibili con il database: "+str(error.msg)[:170])
    except ValueError as error:
        conn.rollback()
        abort(409,str(error))
    except Exception:
        conn.rollback()
        raise
    finally:conn.close()
