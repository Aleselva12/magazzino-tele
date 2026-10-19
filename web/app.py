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

PAGE = """<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Magazzino Tele</title><style>
body{font:15px system-ui,Arial;margin:0;background:#f5f6f8;color:#172435}
header{background:#173552;color:#fff;padding:18px 24px}header h1{margin:0;font-size:23px}
nav{background:white;padding:12px;display:flex;gap:7px;flex-wrap:wrap}
button,input{padding:9px;border:1px solid #bdc8d2;border-radius:5px;font:inherit}
button{background:white;cursor:pointer}button.sel,button.primary{background:#175d95;color:#fff}
main{padding:20px}.actions{display:flex;gap:9px;flex-wrap:wrap;margin:0 0 13px}
.scroll{overflow:auto;background:#fff;max-height:70vh}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #dfe5ea;padding:9px;text-align:left}
th{background:#e8eff5;white-space:nowrap}td{max-width:230px;overflow-wrap:anywhere}
dialog{width:min(600px,92vw);max-height:80vh;overflow:auto;border:1px solid #c3cad1;border-radius:8px}
label.field{display:block;margin:10px 0}label.field input{box-sizing:border-box;width:100%;display:block;margin:5px 0}
#status{white-space:pre-wrap;padding:9px 0;color:#8a3519}
</style></head><body><header><h1>Magazzino Tele</h1>Gestione magazzino</header><nav id="tabs"></nav>
<main><div class="actions"><input id="search" placeholder="Cerca..." aria-label="Cerca nei dati">
<button onclick="page=0;load()">Cerca</button><button onclick="load()">Aggiorna</button>
<button class="primary" onclick="edit()">Aggiungi</button></div><div id="status"></div>
<div class="scroll"><table><thead id="head"></thead><tbody id="body"></tbody></table></div>
<p><button onclick="page=Math.max(0,page-1);load()">Indietro</button> <span id="paging"></span> <button onclick="page++;load()">Avanti</button></p></main>
<dialog id="dialog"><h2 id="caption"></h2><form id="form"></form>
<button class="primary" onclick="save()">Salva</button> <button onclick="document.getElementById('dialog').close()">Chiudi</button></dialog>
<script>
const tabs=['ordini','righe','clienti','colori','modelli','prodotti','magazzino'];
let tab='ordini',page=0,columns=[],keys=[],automatic=[],current=null;
const $=id=>document.getElementById(id);
const txt=(el,value)=>el.textContent=value==null?'':String(value);
tabs.forEach(t=>{const b=document.createElement('button');txt(b,t);b.id='tab_'+t;b.onclick=()=>{tab=t;page=0;load()};$('tabs').appendChild(b)});
async function req(url,opt){let r=await fetch(url,opt),data=await r.json();if(!r.ok)throw Error(data.error||'Errore');return data}
async function load(){try{
let d=await req('/api/'+tab+'?page='+page+'&search='+encodeURIComponent($('search').value));
columns=d.columns;keys=d.primary_key;automatic=d.auto_increment;$('head').replaceChildren();$('body').replaceChildren();
tabs.forEach(t=>$('tab_'+t).classList.toggle('sel',t===tab));
let tr=document.createElement('tr');columns.concat(['Azioni']).forEach(c=>{let h=document.createElement('th');txt(h,c);tr.appendChild(h)});$('head').appendChild(tr);
d.rows.forEach(row=>{let tr=document.createElement('tr');columns.forEach(c=>{let td=document.createElement('td');txt(td,row[c]);tr.appendChild(td)});
let td=document.createElement('td');let btn=document.createElement('button');txt(btn,'Modifica');btn.disabled=!keys.length;btn.onclick=()=>edit(row);td.appendChild(btn);tr.appendChild(td);$('body').appendChild(tr)});
txt($('status'),'');txt($('paging'),'Pagina '+(page+1)+' · '+d.rows.length+' record');
}catch(e){txt($('status'),e.message);$('head').replaceChildren();$('body').replaceChildren()}}
function edit(row=null){current=row;txt($('caption'),row?'Modifica '+tab:'Nuovo '+tab);$('form').replaceChildren();
columns.forEach(c=>{if(!row&&automatic.includes(c))return;let label=document.createElement('label');label.className='field';txt(label,c);
let inp=document.createElement('input');inp.name=c;inp.value=row&&row[c]!=null?row[c]:'';inp.disabled=!!row&&keys.includes(c);
label.appendChild(inp);$('form').appendChild(label)});$('dialog').showModal()}
async function save(){let values={};new FormData($('form')).forEach((v,k)=>values[k]=v===''?null:v);
let updating=!!current,key={};keys.forEach(k=>key[k]=current?.[k]);
try{await req('/api/'+tab,{method:updating?'PATCH':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(updating?{key,changes:values}:values)});
$('dialog').close();load()}catch(e){txt($('status'),e.message)}}
load();
</script></body></html>"""

@app.get("/")
def home():
    from dashboard import PAGE as DASHBOARD
    return render_template_string(DASHBOARD)

from workflow import bp as workflow_bp
from excel_import import bp as import_bp
app.register_blueprint(workflow_bp)
app.register_blueprint(import_bp)
