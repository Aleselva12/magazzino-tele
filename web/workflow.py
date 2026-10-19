"""Legacy Magazzino Tele operational flows: orders, customers, colors, inventory."""
from datetime import date
from flask import Blueprint, abort, jsonify, request

bp = Blueprint("workflow", __name__, url_prefix="/api/workflow")

def connection():
    from app import db
    return db()

@bp.get("/catalog")
def catalog():
    db = connection()
    try:
        c = db.cursor()
        c.execute("SELECT `ï»¿codiceunivoco`,CoF,codice,descrizione FROM customers ORDER BY descrizione")
        customers = [dict(code=r[0],kind=r[1],number=r[2],name=r[3]) for r in c.fetchall()]
        c.execute("SELECT `ï»¿Codice colore`,`Nome Colore` FROM `schema colori semplice` ORDER BY `Nome Colore`")
        colors = [dict(code=r[0],name=r[1]) for r in c.fetchall()]
        c.execute("SELECT `ï»¿codice modello`,MODELLO FROM modelli ORDER BY MODELLO")
        models = [dict(code=r[0],name=r[1]) for r in c.fetchall()]
        c.execute("SELECT `Codice Prodotto`,`Codice Modello`,`Nome Modello`,`Codice Colore`,`Nome Colore` FROM prodotti_completi ORDER BY `Nome Modello`,`Nome Colore`")
        products = [dict(code=r[0],model_code=r[1],model=r[2],color_code=r[3],color=r[4]) for r in c.fetchall()]
        return jsonify(customers=customers,colors=colors,models=models,products=products)
    finally:
        db.close()

@bp.get("/orders")
def orders():
    term=request.args.get("q","").strip()[:100]
    color=request.args.get("color","").strip()[:80]
    try: page=min(max(int(request.args.get("page",0)),0),10000)
    except ValueError: abort(400,"Pagina non valida")
    conditions=[];params=[]
    if term:
        conditions.append("(CAST(o.`codice ordine` AS CHAR) LIKE %s OR c.descrizione LIKE %s OR o.`codice cliente` LIKE %s)")
        params.extend(["%"+term+"%"]*3)
    if color:
        conditions.append("EXISTS (SELECT 1 FROM ordiniprodotti fi JOIN prodotti_completi fp ON fp.`Codice Prodotto`=fi.`codice prodotto` WHERE fi.`codice ordine`=o.`codice ordine` AND fp.`Nome Colore`=%s)")
        params.append(color)
    where=" WHERE "+" AND ".join(conditions) if conditions else ""
    db=connection()
    try:
        c=db.cursor(dictionary=True)
        c.execute("SELECT COUNT(*) AS n, COALESCE(SUM(o.evaso=1),0) AS done FROM ordini o LEFT JOIN customers c ON c.`ï»¿codiceunivoco`=o.`codice cliente`"+where,params)
        totals=c.fetchone()
        c.execute("""SELECT o.`codice ordine` AS id,o.`data` AS data,o.`codice cliente` AS codice_cliente,
                    c.descrizione AS cliente,COALESCE(o.evaso,0) AS evaso,
                    GROUP_CONCAT(DISTINCT pc.`Nome Modello` ORDER BY pc.`Nome Modello` SEPARATOR ', ') AS modello,
                    GROUP_CONCAT(DISTINCT pc.`Nome Colore` ORDER BY pc.`Nome Colore` SEPARATOR ', ') AS colore,
                    COALESCE(SUM(op.quantita),0) AS quantita
                    FROM ordini o LEFT JOIN customers c ON c.`ï»¿codiceunivoco`=o.`codice cliente`
                    LEFT JOIN ordiniprodotti op ON op.`codice ordine`=o.`codice ordine`
                    LEFT JOIN prodotti_completi pc ON pc.`Codice Prodotto`=op.`codice prodotto`"""
                  +where+""" GROUP BY o.`codice ordine`,o.`data`,o.`codice cliente`,c.descrizione,o.evaso
                    ORDER BY o.`codice ordine` DESC LIMIT 100 OFFSET %s""",params+[page*100])
        rows=c.fetchall()
        return jsonify(rows=rows,total=int(totals["n"]),evasi=int(totals["done"]),page=page)
    finally:db.close()

@bp.get("/orders/<int:identifier>")
def order_detail(identifier):
    db=connection()
    try:
        c=db.cursor(dictionary=True)
        c.execute("SELECT `codice ordine` AS id,`codice cliente` AS customer,`data` AS date,evaso FROM ordini WHERE `codice ordine`=%s",(identifier,))
        row=c.fetchone()
        if not row:abort(404,"Ordine non trovato")
        c.execute("""SELECT op.`codice prodotto` AS code,op.quantita AS quantity,op.scritta,op.cuscino,op.pronto,
                 pc.`Nome Modello` AS model,pc.`Nome Colore` AS color
                 FROM ordiniprodotti op JOIN prodotti_completi pc ON pc.`Codice Prodotto`=op.`codice prodotto`
                 WHERE op.`codice ordine`=%s ORDER BY op.codiceordiniprodotti""",(identifier,))
        row["lines"]=c.fetchall()
        return jsonify(row)
    finally:db.close()

def validate_order(data):
    if not isinstance(data,dict):abort(400,"Ordine non valido")
    customer=str(data.get("customer","")).strip()
    if not customer or len(customer)>10:abort(400,"Seleziona un cliente")
    try:day=date.fromisoformat(str(data.get("date",""))).isoformat()
    except ValueError:abort(400,"Data non valida")
    lines=data.get("lines")
    if not isinstance(lines,list) or not 0<len(lines)<=200:abort(400,"Inserisci almeno una riga prodotto")
    parsed=[]
    for line in lines:
        if not isinstance(line,dict):abort(400,"Riga non valida")
        code=str(line.get("code","")).strip()
        try:qty=int(line.get("quantity"))
        except (TypeError,ValueError):abort(400,"Quantità non valida")
        if not code or len(code)>10 or not 0<qty<=1000000:abort(400,"Codice o quantità non validi")
        parsed.append((code,qty,str(line.get("scritta",""))[:45],str(line.get("cuscino",""))[:45],0))
    return customer,day,parsed

@bp.post("/orders")
def create_order():
    customer,day,lines=validate_order(request.get_json(silent=True))
    db=connection()
    c=db.cursor()
    locked=False
    try:
        c.execute("SELECT GET_LOCK('tele_order_identifier',10)")
        locked=c.fetchone()[0]==1
        if not locked:abort(409,"Creazione ordine occupata, riprova")
        c.execute("SELECT CoF FROM customers WHERE `ï»¿codiceunivoco`=%s",(customer,))
        source=c.fetchone()
        if not source:abort(400,"Cliente non trovato in anagrafica")
        for code,*_ in lines:
            c.execute("SELECT 1 FROM prodotti_completi WHERE `Codice Prodotto`=%s",(code,))
            if not c.fetchone():abort(400,"Prodotto non presente: "+code)
        c.execute("SELECT COALESCE(MAX(`codice ordine`),0)+1 FROM ordini")
        order_id=int(c.fetchone()[0])
        c.execute("SELECT COALESCE(MAX(codiceordiniprodotti),0)+1 FROM ordiniprodotti")
        line_id=int(c.fetchone()[0])
        c.execute("INSERT INTO ordini (`codice ordine`,`data`,`codice cliente`,evaso,FornitoreOCliente) VALUES (%s,%s,%s,0,%s)",
                 (order_id,day,customer,1 if str(source[0]).upper()=="F" else 0))
        for code,qty,scritta,cuscino,ready in lines:
            c.execute("INSERT INTO ordiniprodotti (codiceordiniprodotti,`codice ordine`,`codice prodotto`,quantita,scritta,cuscino,pronto) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                      (line_id,order_id,code,qty,scritta,cuscino,ready))
            line_id+=1
        db.commit()
        return jsonify(id=order_id,created=True),201
    except Exception:
        db.rollback()
        raise
    finally:
        if locked:
            try:
                c.execute("SELECT RELEASE_LOCK('tele_order_identifier')")
                c.fetchone()
            except Exception:pass
        c.close()
        db.close()

@bp.patch("/orders/<int:identifier>/status")
def order_status(identifier):
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or type(body.get("evaso")) is not bool:abort(400,"Stato non valido")
    db=connection()
    try:
        c=db.cursor()
        c.execute("UPDATE ordini SET evaso=%s WHERE `codice ordine`=%s",(int(body["evaso"]),identifier))
        if c.rowcount!=1:abort(404,"Ordine non trovato")
        db.commit()
        return jsonify(updated=True)
    except Exception:
        db.rollback();raise
    finally:db.close()

@bp.get("/inventory")
def inventory():
    db=connection()
    try:
        c=db.cursor()
        c.execute("""SELECT pc.`Codice Prodotto`,pc.`Codice Modello`,pc.`Nome Modello`,
                 pc.`Codice Colore`,pc.`Nome Colore`,COALESCE(m.quantita,0)
                 FROM prodotti_completi pc LEFT JOIN magazzino m ON m.codiceprodotto=pc.`Codice Prodotto`
                 ORDER BY pc.`Nome Colore`,pc.`Nome Modello`""")
        return jsonify(rows=[dict(code=r[0],model_code=r[1],model=r[2],color_code=r[3],color=r[4],
                                 quantity=r[5]) for r in c.fetchall()])
    finally:db.close()

@bp.patch("/inventory/<code>")
def inventory_write(code):
    if len(code)>10:abort(400,"Codice prodotto troppo lungo")
    body=request.get_json(silent=True)
    if not isinstance(body,dict):abort(400,"Dati non validi")
    try:qty=int(body.get("quantity"))
    except (TypeError,ValueError):abort(400,"Quantità non valida")
    if not -1000000<=qty<=1000000:abort(400,"Quantità fuori limite")
    db=connection()
    try:
        c=db.cursor()
        c.execute("SELECT 1 FROM prodotti_completi WHERE `Codice Prodotto`=%s",(code,))
        if not c.fetchone():abort(404,"Prodotto non presente")
        c.execute("INSERT INTO magazzino (codiceprodotto,quantita) VALUES (%s,%s) ON DUPLICATE KEY UPDATE quantita=VALUES(quantita)",(code,qty))
        db.commit()
        return jsonify(updated=True)
    except Exception:
        db.rollback();raise
    finally:db.close()
