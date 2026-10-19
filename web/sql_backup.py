"""Safe SQL query-file import and downloadable MySQL database backup.

The backend remains MySQL. Only INSERTs into the seven existing tables are
interpreted; uploaded SQL is NEVER executed as a script (DROP, CREATE, ALTER,
procedures, etc.). Preview is fully transactional and rolls back.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import re
from flask import Blueprint, Response, abort, jsonify, request, stream_with_context
from mysql.connector import Error
from excel_import import ORDER, preview_signature, validate_receipt, q

bp = Blueprint("sql_backup", __name__, url_prefix="/api/workflow")
MAX_SQL_BYTES = 25 * 1024 * 1024
MAX_SQL_ROWS = 200000
IDENT = r'(?:' + chr(96) + r'[^' + chr(96) + r']+' + chr(96) + r'|\[[^\]]+\]|"[^"]+"|[A-Za-z_][\w ]*)'
TABLE_ALIASES = {re.sub(r'[\s_]+', '', name.lower()): name for name in ORDER}
TABLE_ALIASES.update({
    "customers": "customers", "orders": "ordini", "productsorders": "ordiniprodotti",
    "colors": "schema colori semplice", "models": "modelli",
    "products": "prodotti_completi", "inventory": "magazzino"
})


def split_statements(text):
    """Split MySQL/T-SQL batches respecting strings, comments and semicolons."""
    text = re.sub(r"(?im)^\s*GO\s*(?:--[^\n]*)?$", ";", text)
    output, buf = [], []
    quote = None
    escape = False
    line_comment = False
    block_comment = False
    i = 0
    while i < len(text):
        c = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if line_comment:
            if c == "\n":
                line_comment = False
                buf.append("\n")
            i += 1
            continue
        if block_comment:
            if c == "*" and nxt == "/":
                block_comment = False
                i += 2
            else:
                i += 1
            continue
        if quote:
            buf.append(c)
            if escape:
                escape = False
            elif c == "\\" and quote in ("'", '"'):
                escape = True
            elif c == quote:
                if nxt == quote:
                    buf.append(nxt)
                    i += 1
                else:
                    quote = None
            i += 1
            continue
        if c == "-" and nxt == "-" and text[i + 2:i + 3] in (" ", "\t", "\n", ""):
            line_comment = True
            i += 2
            continue
        if c == "#":
            line_comment = True
            i += 1
            continue
        if c == "/" and nxt == "*":
            block_comment = True
            i += 2
            continue
        if c in ("'", '"', chr(96)):
            quote = c
            buf.append(c)
        elif c == ";":
            s = "".join(buf).strip()
            if s:
                output.append(s)
            buf = []
        else:
            buf.append(c)
        i += 1
    if quote or block_comment:
        raise ValueError("SQL incompleto: stringa o commento non chiuso")
    last = "".join(buf).strip()
    if last:
        output.append(last)
    return output


def ident(raw):
    raw = raw.strip()
    if raw.startswith((chr(96), "[", '"')):
        raw = raw[1:-1]
    return raw


def parse_values(fragment):
    """Parse literal tuples, rejecting arbitrary expressions/SQL functions."""
    rows, pos = [], 0
    size = len(fragment)
    escape_map = {"0": "\0", "n": "\n", "r": "\r", "t": "\t", "b": "\b",
                  "Z": "\x1a", "\\": "\\", "'": "'", '"': '"'}
    def white():
        nonlocal pos
        while pos < size and fragment[pos].isspace():
            pos += 1
    def value():
        nonlocal pos
        white()
        if pos < size and fragment[pos] in ("N", "n") and pos + 1 < size and fragment[pos + 1] == "'":
            pos += 1
        if pos < size and fragment[pos] == "'":
            pos += 1
            chars = []
            while pos < size:
                c = fragment[pos]
                pos += 1
                if c == "'":
                    if pos < size and fragment[pos] == "'":
                        chars.append("'")
                        pos += 1
                    else:
                        return "".join(chars)
                elif c == "\\":
                    if pos >= size:
                        raise ValueError("Escape SQL incompleto")
                    nxt = fragment[pos]
                    pos += 1
                    chars.append(escape_map.get(nxt, nxt))
                else:
                    chars.append(c)
            raise ValueError("Stringa SQL non terminata")
        m = re.match(r"(?:NULL|TRUE|FALSE|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b",
                     fragment[pos:], re.I)
        if not m:
            raise ValueError("Il backup SQL contiene espressioni non consentite")
        pos += len(m.group(0))
        token = m.group(0)
        if token.upper() == "NULL":
            return None
        if token.upper() in ("TRUE", "FALSE"):
            return 1 if token.upper() == "TRUE" else 0
        return Decimal(token) if "." in token or "e" in token.lower() else int(token)
    while True:
        white()
        if pos >= size:
            break
        if fragment[pos] != "(":
            raise ValueError("VALUES SQL non riconosciuti: attese parentesi")
        pos += 1
        row = []
        while True:
            row.append(value())
            white()
            if pos >= size:
                raise ValueError("Riga SQL incompleta")
            delimiter = fragment[pos]
            pos += 1
            if delimiter == ")":
                break
            if delimiter != ",":
                raise ValueError("Separatore SQL non valido")
        rows.append(row)
        if len(rows) > MAX_SQL_ROWS:
            raise ValueError("Troppi record nel backup")
        white()
        if pos >= size:
            break
        if fragment[pos] != ",":
            raise ValueError("Separatore fra righe SQL non valido")
        pos += 1
    return rows


def read_backup(raw):
    if len(raw) > MAX_SQL_BYTES:
        raise ValueError("SQL superiore a 25 MB")
    try:
        sql = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        sql = raw.decode("cp1252")
    tables = {}
    ignored_ddl = 0
    for statement in split_statements(sql):
        s = statement.strip()
        if re.match(r"(?is)^INSERT\s+INTO\b", s):
            match = re.match(
                r"(?is)^INSERT\s+INTO\s+(?:(?:\[dbo\]|" + chr(96) +
                r"dbo" + chr(96) + r"|dbo)\s*\.\s*)?(" + IDENT +
                r")\s*\(([^()]*)\)\s*VALUES\s*(.*)$", s)
            if not match:
                raise ValueError("INSERT SQL non supportato: occorrono nomi di colonne espliciti")
            table_raw, column_raw, values_raw = match.groups()
            table = TABLE_ALIASES.get(re.sub(r"[\s_]+", "", ident(table_raw).lower()))
            if table is None:
                raise ValueError("Tabella SQL sconosciuta: " + ident(table_raw) +
                                 ". Non vengono importate tabelle nuove o spedizioni non previste.")
            columns = [ident(x) for x in column_raw.split(",")]
            if len(set(columns)) != len(columns) or not all(columns):
                raise ValueError("Colonne SQL non valide")
            rows = parse_values(values_raw)
            if any(len(row) != len(columns) for row in rows):
                raise ValueError("Numero valori SQL diverso dalle colonne")
            group = tables.setdefault(table, {"cols": columns, "rows": []})
            if [x.lower() for x in group["cols"]] != [x.lower() for x in columns]:
                raise ValueError("Lo stesso file usa due layout di colonne per " + table)
            group["rows"].extend(rows)
            if sum(len(x["rows"]) for x in tables.values()) > MAX_SQL_ROWS:
                raise ValueError("Troppi record SQL")
        elif re.match(r"(?is)^(?:CREATE\s+TABLE|DROP\s+TABLE\s+IF\s+EXISTS)\b", s):
            # DDL is inspected, never executed against the existing database.
            ignored_ddl += 1
        elif re.match(r"(?is)^(?:SET\b|USE\b|LOCK\s+TABLES\b|UNLOCK\s+TABLES\b|"
                      r"BEGIN\b|START\s+TRANSACTION\b|COMMIT\b|"
                      r"ROLLBACK\b|PRINT\b)", s):
            pass
        else:
            raise ValueError("Istruzione SQL non consentita. Sono accettati dump con INSERT "
                             "letterali; procedure, DELETE, ALTER e comandi arbitrari non vengono eseguiti.")
    if not tables:
        raise ValueError("Nel file non ci sono record INSERT nelle sette tabelle note")
    return tables, ignored_ddl


def literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    if isinstance(value, (datetime, date)):
        value = value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex()
    value = str(value).replace("\\", "\\\\").replace("\0", "\\0")
    value = value.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    value = value.replace("\x1a", "\\Z").replace("'", "''")
    return "'" + value + "'"


@bp.post("/sql-backup/preview")
@bp.post("/sql-backup/import")
def sql_import():
    is_apply = request.path.endswith("/import")
    upload = request.files.get("file")
    if not upload or not upload.filename or not upload.filename.lower().endswith(".sql"):
        abort(400, "Seleziona un file query .sql")
    raw = upload.read(MAX_SQL_BYTES + 1)
    if len(raw) > MAX_SQL_BYTES:
        abort(413, "Backup SQL superiore a 25 MB")
    digest = hashlib.sha256(raw).hexdigest()
    if is_apply and not validate_receipt(request.form.get("preview_token"), digest):
        abort(409, "Verifica prima lo stesso file SQL con Anteprima")
    try:
        tables, ignored = read_backup(raw)
    except ValueError as err:
        abort(422, str(err))
    from app import db
    conn = db()
    try:
        c = conn.cursor()
        summary = []
        for table in ORDER:
            if table not in tables:
                continue
            c.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                      "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",
                      (table,))
            columns = [x[0] for x in c.fetchall()]
            if not columns:
                abort(503, "Schema database non installato: " + table)
            given = tables[table]["cols"]
            if any(name.lower() not in {x.lower() for x in columns} for name in given):
                abort(422, "Colonne del backup incompatibili con " + table +
                      ": probabilmente usa uno schema SQL Server differente dal gestionale MySQL")
            c.execute("SELECT COUNT(*) FROM " + q(table))
            n = int(c.fetchone()[0])
            if n:
                abort(409, "La tabella " + table + " contiene già " + str(n) +
                      " record. Il ripristino non sovrascrive dati esistenti.")
            summary.append({"table": table, "rows": len(tables[table]["rows"])})
        # Do not use foreign_key_checks=0: replay in dependency order.
        for table in ORDER:
            if table not in tables:
                continue
            group = tables[table]
            fields = group["cols"]
            command = "INSERT INTO " + q(table) + " (" + ",".join(map(q, fields)) + \
                      ") VALUES (" + ",".join(["%s"] * len(fields)) + ")"
            for idx in range(0, len(group["rows"]), 500):
                c.executemany(command, group["rows"][idx:idx + 500])
        if is_apply:
            conn.commit()
        else:
            conn.rollback()
        return jsonify(validated=True, imported=is_apply, dialect="MySQL-compatible SQL data",
                       tables=summary, total=sum(x["rows"] for x in summary),
                       ddl_ignored=ignored, 
                       preview_token=None if is_apply else preview_signature(digest, int(datetime.now(timezone.utc).timestamp()) + 3600))
    except Error as err:
        conn.rollback()
        abort(409, "Il backup SQL non rispetta i vincoli del database: " + str(err.msg)[:180])
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@bp.get("/sql-backup/export")
def export_backup():
    """Download schema and all records; MySQL .sql, no cloud storage or public files."""
    from app import db
    def generate():
        conn = db()
        try:
            c = conn.cursor()
            yield b"-- Magazzino Tele - backup MySQL .sql\n"
            yield b"-- Contiene dati aziendali: conservare in privato\n"
            yield b"SET NAMES utf8mb4;\n"
            for table in ORDER:
                c.execute("SHOW CREATE TABLE " + q(table))
                statement = c.fetchone()[1]
                yield ("\n" + statement.rstrip(";") + ";\n").encode("utf-8")
            for table in ORDER:
                c.execute("SELECT * FROM " + q(table))
                cols = [x[0] for x in c.description]
                prefix = "INSERT INTO " + q(table) + " (" + ",".join(map(q, cols)) + ") VALUES "
                while True:
                    rows = c.fetchmany(250)
                    if not rows:
                        break
                    for row in rows:
                        yield (prefix + "(" + ",".join(literal(x) for x in row) + ");\n").encode("utf-8")
        finally:
            conn.close()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M")
    return Response(stream_with_context(generate()), mimetype="application/sql",
                    headers={"Content-Disposition": 'attachment; filename="database-backup-' +
                             stamp + '.sql"', "Cache-Control": "no-store",
                             "X-Content-Type-Options": "nosniff"})
