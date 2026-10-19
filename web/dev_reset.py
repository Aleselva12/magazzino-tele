"""Development-only, explicitly authorized reset of Magazzino Tele data ONLY.

Never touches the schema, PostgreSQL/Cora, Nextcloud or any other application.
Before deleting rows, save a private compressed snapshot on a persistent Docker volume.
"""
import gzip
import hmac
import json
import os
from pathlib import Path
import secrets
from datetime import datetime, timezone
from flask import Blueprint, abort, jsonify, request
from mysql.connector import Error

bp=Blueprint("dev_reset",__name__,url_prefix="/api/workflow/dev-reset")
ORDER=("ordiniprodotti","magazzino","ordini","prodotti_completi",
       "schema colori semplice","modelli","customers")
BACKUPS=Path("/private-backups")
CONFIRM="CANCELLA MAGAZZINO TELE"

def enabled():
    return os.environ.get("TELE_DEV_RESET_ENABLED","").lower()=="true"

@bp.get("/status")
def status():
    return jsonify(enabled=enabled(),scope="Esclusivamente record MySQL di Magazzino Tele",
                   backup_required=True)

@bp.post("")
def reset():
    if not enabled():abort(404,"Funzione disattivata")
    configured=os.environ.get("TELE_DEV_RESET_TOKEN","")
    if len(configured)<24:abort(503,"Token reset non configurato sul server")
    token=request.headers.get("X-Dev-Reset-Token","")
    if not hmac.compare_digest(configured,token):
        abort(403,"Codice amministratore non valido")
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or data.get("confirm")!=CONFIRM:
        abort(400,"Digitare la frase di conferma esatta")
    from app import db
    conn=db()
    cursor=conn.cursor()
    locked=False
    backup=None
    try:
        cursor.execute("SELECT GET_LOCK('tele_development_reset',5)")
        locked=cursor.fetchone()[0]==1
        if not locked:abort(409,"Un reset è già in corso")
        # Ensure persistent volume is present/writable before any destructive action.
        if not BACKUPS.is_dir() or BACKUPS.is_symlink():
            abort(503,"Volume persistente backup non disponibile")
        conn.start_transaction(consistent_snapshot=True)
        snapshot={}
        for name in ORDER:
            cursor.execute("SELECT * FROM "+chr(96)+name+chr(96))
            names=[x[0] for x in cursor.description]
            snapshot[name]=[dict(zip(names,row)) for row in cursor.fetchall()]
        record_count=sum(len(rows) for rows in snapshot.values())
        timestamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path=BACKUPS/("before-reset-"+timestamp+"-"+secrets.token_hex(5)+".json.gz")
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
        descriptor=os.open(path,flags,0o600)
        try:
            with os.fdopen(descriptor,"wb") as stream:
                with gzip.GzipFile(fileobj=stream,mode="wb") as compressed:
                    compressed.write(json.dumps(snapshot,ensure_ascii=False,default=str).encode())
                    compressed.flush()
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            path.unlink(missing_ok=True)
            raise
        backup=path.name
        # DELETE, not TRUNCATE: transactional, foreign-key compliant and reversible
        # until commit; leaves tables, constraints, users, and sequences intact.
        for name in ORDER:
            cursor.execute("DELETE FROM "+chr(96)+name+chr(96))
        conn.commit()
        return jsonify(reset=True,rows_removed=record_count,backup=backup,
                       scope="Solo database Magazzino Tele")
    except Error as e:
        conn.rollback()
        abort(409,"Impossibile azzerare Magazzino Tele: "+str(e.msg)[:130])
    except Exception:
        conn.rollback()
        raise
    finally:
        if locked:
            try:
                cursor.execute("SELECT RELEASE_LOCK('tele_development_reset')")
                cursor.fetchone()
            except Exception:pass
        cursor.close()
        conn.close()
