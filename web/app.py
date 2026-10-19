"""Independent Magazzino Tele web UI. No Cora integration."""
import os
from datetime import date, datetime
from decimal import Decimal
from flask import Flask, jsonify, request, render_template_string, abort
from werkzeug.exceptions import HTTPException
import mysql.connector

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
TABLES = {
    "clienti": "customers", "colori": "schema colori semplice",
    "modelli": "modelli", "prodotti": "prodotti_completi",
    "magazzino": "magazzino", "ordini": "ordini",
    "righe": "ordiniprodotti",
}

def db():
    return mysql.connector.connect(
        host=os.environ.get("TELE_DB_HOST", "db"),
        database=os.environ.get("TELE_DB_NAME", "magazzino_tele"),
        user=os.environ["TELE_DB_USER"], password=os.environ["TELE_DB_PASSWORD"],
        charset="utf8mb4", connection_timeout=5,
    )

def quoted(name):
    return "`" + name.replace("`", "``") + "`"

def table_for(alias):
    if alias not in TABLES:
        abort(404)
    return TABLES[alias]

def metadata(cursor, table):
    cursor.execute(
        "SELECT COLUMN_NAME,COLUMN_KEY,EXTRA FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",
        (table,),
    )
    items = cursor.fetchall()
    if not items:
        abort(503, "Schema del gestionale non inizializzato")
    return [x[0] for x in items], [x[0] for x in items if x[1]=="PRI"], [x[0] for x in items if "auto_increment" in x[2]]

def connection_scope(work):
    conn=db()
    try:
        return work(conn)
    finally:
        conn.close()

@app.errorhandler(Exception)
def fail(e):
    if isinstance(e, HTTPException):
        return jsonify(error=e.description), e.code
    app.logger.exception("Database request failed")
    return jsonify(error="Errore nel database o nella configurazione"), 500

@app.get("/health")
def health():
    def run(conn):
        c=conn.cursor()
        c.execute("SELECT 1")
        c.fetchone()
        return jsonify(status="ok")
    return connection_scope(run)

@app.get("/api/<alias>")
def rows(alias):
    table=table_for(alias)
    try: page=max(0,min(10000,int(request.args.get("page","0"))))
    except ValueError: abort(400,"Pagina non valida")
    search=request.args.get("search","")[:100]
    def run(conn):
        c=conn.cursor(dictionary=True)
        columns,pk,auto=metadata(c,table)
        conditions=" OR ".join(f"CAST({quoted(col)} AS CHAR) LIKE %s" for col in columns)
        where=" WHERE ("+conditions+")" if search else ""
        params=["%"+search+"%"]*len(columns) if search else []
        order=" ORDER BY "+",".join(quoted(x) for x in pk) if pk else ""
        c.execute("SELECT * FROM "+quoted(table)+where+order+" LIMIT 50 OFFSET %s",params+[page*50])
        data=c.fetchall()
        def val(x):
            if isinstance(x,(date,datetime)):return x.isoformat()
            if isinstance(x,Decimal):return str(x)
            return x
        return jsonify(columns=columns,primary_key=pk,auto_increment=auto,
                       rows=[{k:val(v) for k,v in row.items()} for row in data],page=page)
    return connection_scope(run)

@app.post("/api/<alias>")
def insert(alias):
    table=table_for(alias)
    body=request.get_json(silent=True)
    if not isinstance(body,dict): abort(400,"Dati non validi")
    def run(conn):
        c=conn.cursor()
        cols,pk,auto=metadata(c,table)
        fields={k:v for k,v in body.items() if k in cols and k not in auto}
        if not fields or len(fields)!=len(body): abort(400,"Campi non validi")
        c.execute("INSERT INTO "+quoted(table)+" ("+",".join(quoted(k) for k in fields)+") VALUES ("+",".join(["%s"]*len(fields))+")",list(fields.values()))
        conn.commit()
        return jsonify(ok=True),201
    return connection_scope(run)

@app.patch("/api/<alias>")
def modify(alias):
    table=table_for(alias)
    body=request.get_json(silent=True)
    if not isinstance(body,dict): abort(400,"Dati non validi")
    key=body.get("key")
    changes=body.get("changes")
    def run(conn):
        c=conn.cursor()
        cols,pk,auto=metadata(c,table)
        if not pk or not isinstance(key,dict) or set(key)!=set(pk):abort(400,"Chiave primaria non valida")
        if not isinstance(changes,dict) or not changes or any(k not in cols or k in pk or k in auto for k in changes):
            abort(400,"Campi da modificare non validi")
        c.execute("UPDATE "+quoted(table)+" SET "+",".join(quoted(k)+"=%s" for k in changes)+
                  " WHERE "+" AND ".join(quoted(k)+"=%s" for k in pk),
                  list(changes.values())+[key[k] for k in pk])
        conn.commit()
        return jsonify(ok=True,changed=c.rowcount)
    return connection_scope(run)

@app.get("/")
def home():
    from dashboard import PAGE as DASHBOARD
    return render_template_string(DASHBOARD)

from workflow import bp as workflow_bp
from excel_import import bp as import_bp
app.register_blueprint(workflow_bp)
app.register_blueprint(import_bp)
