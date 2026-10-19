"""Turn legacy per-color Excel order sheets into relational MySQL orders.

Only explicit order rows are accepted. No AI, no heuristically inferred quantity
from calculated stock cells. Preview is read-only; apply is one transaction.
"""
import hashlib
import io
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import PurePath

from flask import Blueprint, abort, jsonify, request
from mysql.connector import Error
from openpyxl import load_workbook
import xlrd
from excel_import import upload_parts, norm, preview_signature, validate_receipt

bp = Blueprint("color_workbooks", __name__, url_prefix="/api/workflow/color-orders")
MAX_ORDERS = 5000

def clean(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()

def key(value):
    return re.sub(r"[^a-z0-9]+", "", clean(value).casefold())

def name_key(value):
    return " ".join(clean(value).upper().split())

def qty(value):
    if isinstance(value, bool):
        return None
    try:
        f = float(value)
        return int(f) if f.is_integer() and abs(f) <= 1000000 else None
    except (ValueError, TypeError, OverflowError):
        return None

def color_from_filename(filename):
    stem = PurePath(filename).stem.strip()
    match = re.match(r"^(?:(?:MEL|CORTI|FABBRI|RAMBERTI)\s+)?(?:0*(\d{2,6}))[\s._-]+(.+)$", stem, re.I)
    if match:
        return int(match.group(1)), name_key(match.group(2))
    return None, name_key(stem)

def sheets(filename, raw):
    if filename.lower().endswith(".xls"):
        book = xlrd.open_workbook(file_contents=raw, on_demand=True)
        try:
            for ws in book.sheets():
                if ws.nrows > 25001 or ws.ncols > 100:
                    raise ValueError("Foglio Excel troppo grande: " + filename)
                lines = []
                for r in range(ws.nrows):
                    row=[]
                    for cell in ws.row(r):
                        if cell.ctype == xlrd.XL_CELL_ERROR:
                            row.append(None)
                        elif cell.ctype == xlrd.XL_CELL_DATE:
                            row.append(xlrd.xldate_as_datetime(cell.value,book.datemode).date().isoformat())
                        else:
                            row.append(cell.value)
                    lines.append(row)
                yield ws.name, lines
        finally:
            book.release_resources()
    elif filename.lower().endswith(".xlsx"):
        book = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        try:
            for ws in book.worksheets:
                if ws.max_row > 25001 or ws.max_column > 100:
                    raise ValueError("Foglio Excel troppo grande: " + filename)
                yield ws.title, list(ws.iter_rows(values_only=True))
        finally:
            book.close()
    else:
        raise ValueError("È necessario un file Excel .xls o .xlsx")

def parse_orders(parts):
    candidates, issues, summaries = [], [], []
    names_seen=set()
    for filename,raw in parts:
        if not filename.lower().endswith((".xls", ".xlsx")):
            summaries.append({"file": filename,"result":"ignorato: non è una scheda ordini Excel"})
            continue
        if filename.casefold() in names_seen:
            issues.append(filename+": due file con lo stesso nome; caricali separatamente")
            continue
        names_seen.add(filename.casefold())
        color_code,color_label=color_from_filename(filename)
        file_found=0
        if not color_label:
            issues.append(filename+": nome colore mancante")
            continue
        for sheet,rows in sheets(filename,raw):
            if not rows:
                continue
            header_idx=None
            cols={}
            for i,row in enumerate(rows[:8]):
                mapping={key(v):j for j,v in enumerate(row) if clean(v)}
                if {"codcli","nome","qta"}.issubset(mapping):
                    header_idx=i;cols=mapping;typ="standard";break
                if {"modello","clienti","qta"}.issubset(mapping):
                    header_idx=i;cols=mapping;typ="special";break
            if header_idx is None:
                continue
            for n in range(header_idx+1,len(rows)):
                row=rows[n]
                def get(name):
                    j=cols.get(name)
                    return row[j] if j is not None and j<len(row) else None
                amount=qty(get("qta"))
                if amount is None or amount == 0:
                    continue
                if amount < 0:
                    # Negative deliveries are incoming/stock movements, NOT new orders.
                    continue
                if typ=="standard":
                    customer=clean(get("nome"))
                    client_code=clean(get("codcli"))
                    model=clean(get("descrittiva"))
                    reference=clean(get("imp"))
                    message=clean(get("scrittaparasole")) or clean(get("scrittatele"))
                    state=clean(get("evaso"))
                else:
                    customer=clean(get("clienti"))
                    client_code=""
                    model=clean(get("modello"))
                    reference=clean(get("impegno"))
                    message=""
                    state=clean(get("evaso"))
                if not customer or not model:
                    issues.append(f"{filename} / {sheet} / riga {n+1}: cliente o descrizione modello mancanti, quantità {amount}")
                    continue
                if len(model)>200 or len(customer)>240:
                    issues.append(f"{filename} / {sheet} / riga {n+1}: testo troppo lungo")
                    continue
                marker=hashlib.sha256((filename.casefold()+"|"+sheet.casefold()+"|"+str(n+1)).encode()).hexdigest()[:32]
                tag="XL:"+marker+"-"+re.sub(r"[^A-Za-z0-9]", "",reference)[:8]
                if len(tag)>45:
                    raise ValueError("Riferimento importazione troppo lungo")
                candidates.append(dict(source=filename,sheet=sheet,row=n+1,
                    customer=customer,customer_code=client_code,model=name_key(model),
                    color_code=color_code,color=color_label,quantity=amount,
                    evaso=state.upper() in ("EVASO","EVASA","SPEDITO","SPEDITA"),
                    scritta=message[:45],reference=reference,tag=tag))
                file_found+=1
                if len(candidates)>MAX_ORDERS:
                    raise ValueError("Troppi ordini in una sola importazione (massimo 5000)")
        summaries.append(dict(file=filename, orders_detected=file_found,
                              color=color_label, color_code=color_code))
    return candidates,issues,summaries

def read_catalog(conn):
    c=conn.cursor()
    def select(sql):
        c.execute(sql)
        return c.fetchall()
    customers=select("SELECT `ï»¿codiceunivoco`,CoF,codice,descrizione FROM customers")
    colors=select("SELECT `ï»¿Codice colore`,`Nome Colore` FROM `schema colori semplice`")
    models=select("SELECT `ï»¿codice modello`,MODELLO FROM modelli")
    products=select("SELECT `Codice Prodotto`,`Codice Modello`,`Codice Colore` FROM prodotti_completi")
    orders=select("SELECT `codice ordine`,`codice ordine prodotto` FROM ordini")
    c.execute("SELECT COALESCE(MAX(codiceordiniprodotti),0) FROM ordiniprodotti")
    line_id=int(c.fetchone()[0])
    return dict(customers=customers,colors=colors,models=models,products=products,orders=orders,line_id=line_id)

def plan_import(candidates,issues,summaries,existing,registration_date):
    # All generated keys are unique, non-null, and remain compatible with legacy schema.
    customers={clean(r[0]):(clean(r[1]),r[2],clean(r[3])) for r in existing["customers"]}
    by_name=defaultdict(set)
    for code,(_kind,_num,label) in customers.items():
        by_name[name_key(label)].add(code)
    colors={int(code):name_key(label) for code,label in existing["colors"]}
    colors_by_name=defaultdict(set)
    for code,label in colors.items():colors_by_name[label].add(code)
    models={int(code):name_key(label) for code,label in existing["models"]}
    models_by_name=defaultdict(set)
    for code,label in models.items():models_by_name[label].add(code)
    products={clean(code):(int(m),int(c)) for code,m,c in existing["products"]}
    products_by_pair=defaultdict(set)
    for code,pair in products.items():products_by_pair[pair].add(code)
    tags={clean(tag) for _id,tag in existing["orders"] if tag}
    next_client=max([int(r[2] or 0) for r in existing["customers"]]+
                    [int(re.sub(r"^\D+","",code) or 0) for code in customers] + [0])
    next_color=max(colors.keys(),default=0)
    next_model=max(models.keys(),default=0)
    next_order=max([int(i) for i,_tag in existing["orders"]]+[0])
    next_line=existing["line_id"]
    next_product=0
    inserted={"customers":[],"colors":[],"models":[],"products":[],"orders":[],"lines":[]}
    duplicate=0
    for rec in candidates:
        if rec["tag"] in tags:
            duplicate+=1
            continue
        cname=name_key(rec["customer"])
        supplied=clean(rec["customer_code"]).upper()
        if supplied:
            if len(supplied)>10 or not re.fullmatch(r"[CF]\d+",supplied):
                issues.append(f'{rec["source"]} riga {rec["row"]}: codice cliente non valido ({supplied})')
                continue
            if supplied in customers:
                if name_key(customers[supplied][2])!=cname:
                    issues.append(f'{rec["source"]} riga {rec["row"]}: codice {supplied} associato a un altro cliente')
                    continue
                custcode=supplied
            elif by_name.get(cname):
                if len(by_name[cname]) != 1 or next(iter(by_name[cname])) != supplied:
                    issues.append(f'{rec["source"]} riga {rec["row"]}: cliente già esistente con codice diverso')
                    continue
                custcode=supplied
            else:
                custcode=supplied
                digit=int(supplied[1:])
                next_client=max(next_client,digit)
                customers[custcode]=("C",digit,cname)
                by_name[cname].add(custcode)
                inserted["customers"].append((custcode,"C",digit,cname))
        else:
            options=by_name.get(cname,set())
            if len(options)>1:
                issues.append(f'{rec["source"]} riga {rec["row"]}: più clienti con nome {cname}')
                continue
            if options:
                custcode=next(iter(options))
            else:
                next_client+=1
                custcode="C"+str(next_client).zfill(5)
                if len(custcode)>10:
                    issues.append("Progressivo clienti oltre dieci caratteri")
                    continue
                customers[custcode]=("C",next_client,cname)
                by_name[cname].add(custcode)
                inserted["customers"].append((custcode,"C",next_client,cname))
        color_id=rec["color_code"]
        if color_id is not None:
            if color_id in colors:
                color_label=colors[color_id]
                if color_label != rec["color"] and rec["color"] not in color_label:
                    # Filename abbreviations differ from canonical master labels.
                    pass
            else:
                color_label=rec["color"]
                colors[color_id]=color_label
                colors_by_name[color_label].add(color_id)
                inserted["colors"].append((color_id,color_label))
                next_color=max(next_color,color_id)
        else:
            choices=colors_by_name.get(rec["color"],set())
            if len(choices)>1:
                issues.append(f'{rec["source"]}: nome colore duplicato, serve codice numerico')
                continue
            if choices:
                color_id=next(iter(choices))
            else:
                next_color+=1
                color_id=next_color
                color_label=rec["color"]
                colors[color_id]=color_label
                colors_by_name[color_label].add(color_id)
                inserted["colors"].append((color_id,color_label))
        model_label=rec["model"]
        options=models_by_name.get(model_label,set())
        if len(options)>1:
            issues.append(f'{rec["source"]} riga {rec["row"]}: modello omonimo in anagrafica')
            continue
        if options:
            model_id=next(iter(options))
        else:
            next_model+=1
            model_id=next_model
            models[model_id]=model_label
            models_by_name[model_label].add(model_id)
            inserted["models"].append((model_id,model_label))
        pair=(model_id,color_id)
        options=products_by_pair.get(pair,set())
        if len(options)>1:
            issues.append(f'{rec["source"]} riga {rec["row"]}: due prodotti con gli stessi codici modello/colore')
            continue
        if options:
            product_code=next(iter(options))
        else:
            suggestion=f"{model_id}-{color_id}"
            if len(suggestion)>10 or suggestion in products:
                while True:
                    next_product+=1
                    suggestion="P"+str(next_product).zfill(9)
                    if suggestion not in products:break
            product_code=suggestion
            products[product_code]=pair
            products_by_pair[pair].add(product_code)
            inserted["products"].append((product_code,model_id,model_label,color_id,colors[color_id]))
        next_order+=1
        next_line+=1
        if not custcode or not product_code or not registration_date:
            raise ValueError("Chiave obbligatoria non valorizzata")
        kind=1 if customers[custcode][0].upper()=="F" else 0
        inserted["orders"].append((next_order,registration_date,custcode,int(rec["evaso"]),rec["tag"],kind))
        inserted["lines"].append((next_line,product_code,next_order,rec["quantity"],rec["scritta"],"",0))
        tags.add(rec["tag"])
    # Do not leave orphan anagraphic records behind when a source row
    # cannot become a valid order (particularly with partial import).
    used_customers={row[2] for row in inserted["orders"]}
    used_products={row[1] for row in inserted["lines"]}
    inserted["customers"]=[r for r in inserted["customers"] if r[0] in used_customers]
    inserted["products"]=[r for r in inserted["products"] if r[0] in used_products]
    used_models={r[1] for r in inserted["products"]}
    used_colors={r[3] for r in inserted["products"]}
    inserted["models"]=[r for r in inserted["models"] if r[0] in used_models]
    inserted["colors"]=[r for r in inserted["colors"] if r[0] in used_colors]
    preview={
      "totals":{k:len(v) for k,v in inserted.items()},
      "already_imported":duplicate,
      "source_files":summaries[:160],
      "warnings":issues[:120],
      "warnings_count":len(issues),
      "examples":[{"source":x["source"],"sheet":x["sheet"],"row":x["row"],
                   "customer":x["customer"],"model":x["model"],"color":x["color"],
                   "quantity":x["quantity"],"impegno":x["reference"]}
                  for x in candidates[:35]],
      "registration_date":registration_date
    }
    return inserted,preview

def digest_plan(raw_digest,day,preview,operations):
    shape=json.dumps({"digest":raw_digest,"day":day,"counts":preview["totals"],
                      "skipped":preview["already_imported"],"warn":preview["warnings"],
                      "operations":operations},
                     sort_keys=True,ensure_ascii=False)
    return hashlib.sha256(shape.encode()).hexdigest()

@bp.post("/preview")
@bp.post("/apply")
def import_workbooks():
    do_apply=request.path.endswith("/apply")
    try:
        registration_date=date.fromisoformat(request.form.get("date","")).isoformat()
    except ValueError:
        abort(400,"Indicare una data di registrazione valida")
    if request.content_length and request.content_length>80*1024*1024:
        abort(413,"Massimo 80 MB per invio")
    allow_partial=request.form.get("allow_partial")=="true"
    if not request.files.getlist("files"):abort(400,"Seleziona i file Excel")
    parts,digest=upload_parts(request.files.getlist("files"))
    try:
        candidates,issues,summaries=parse_orders(parts)
    except (ValueError, xlrd.XLRDError, OSError, KeyError) as error:
        abort(422,"Excel non leggibile: "+str(error)[:200])
    if not candidates:
        return jsonify(validated=False,blocked=True,message="Non sono state trovate righe d'ordine con quantità positiva",source_files=summaries,warnings=issues),422
    from app import db
    conn=db()
    cur=conn.cursor()
    locked=False
    try:
        if do_apply:
            cur.execute("SELECT GET_LOCK('tele_order_identifier',10)")
            locked=cur.fetchone()[0]==1
            if not locked:abort(409,"Ordini in fase di aggiornamento, riprova")
        catalog=read_catalog(conn)
        operations,preview=plan_import(candidates,issues,summaries,catalog,registration_date)
        checksum=digest_plan(digest,registration_date,preview,operations)
        checksum=hashlib.sha256((checksum+"|partial="+str(allow_partial)).encode()).hexdigest()
        preview["validated"]=(not issues or allow_partial) and preview["totals"]["orders"]>0
        preview["partial_mode"]=allow_partial
        preview["blocked"]=bool(issues)
        if do_apply:
            if issues:
                abort(409,"Importazione bloccata: correggi le righe segnalate nell'anteprima")
            if not validate_receipt(request.form.get("preview_token"),checksum):
                abort(409,"Anteprima scaduta o database modificato: esegui di nuovo Controlla file")
            if not operations["orders"]:
                abort(409,"Non ci sono nuovi ordini da importare")
            statements=[
              ("customers","INSERT INTO customers (`ï»¿codiceunivoco`,CoF,codice,descrizione) VALUES (%s,%s,%s,%s)"),
              ("colors","INSERT INTO `schema colori semplice` (`ï»¿Codice colore`,`Nome Colore`) VALUES (%s,%s)"),
              ("models","INSERT INTO modelli (`ï»¿codice modello`,MODELLO) VALUES (%s,%s)"),
              ("products","INSERT INTO prodotti_completi (`Codice Prodotto`,`Codice Modello`,`Nome Modello`,`Codice Colore`,`Nome Colore`) VALUES (%s,%s,%s,%s,%s)"),
              ("orders","INSERT INTO ordini (`codice ordine`,`data`,`codice cliente`,evaso,`codice ordine prodotto`,FornitoreOCliente) VALUES (%s,%s,%s,%s,%s,%s)"),
              ("lines","INSERT INTO ordiniprodotti (codiceordiniprodotti,`codice prodotto`,`codice ordine`,quantita,scritta,cuscino,pronto) VALUES (%s,%s,%s,%s,%s,%s,%s)")
            ]
            for item,sql in statements:
                if operations[item]:
                    cur.executemany(sql,operations[item])
            conn.commit()
            return jsonify(imported=True,**preview)
        conn.rollback()
        preview["preview_token"]=preview_signature(checksum,int(__import__("time").time())+3600) if preview["validated"] else None
        return jsonify(imported=False,**preview)
    except Error as e:
        conn.rollback()
        abort(409,"Il database ha rifiutato una chiave o un riferimento: "+str(e.msg)[:150])
    except Exception:
        conn.rollback()
        raise
    finally:
        if locked:
            try:
                cur.execute("SELECT RELEASE_LOCK('tele_order_identifier')")
                cur.fetchone()
            except Exception:
                pass
        cur.close()
        conn.close()
