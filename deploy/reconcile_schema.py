"""Recover missing legacy tables without destroying a partially initialized MySQL volume.

Stops if any legacy table contains records or if an existing table's columns differ.
This is an operator-invoked step; no schema repair runs on every web request.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path
from prepare_schema import ORDER, definitions

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "--env-file", "deploy/.env", "-f", "deploy/compose.yml"]
SOURCE = ROOT / "backup/2025-08-17_18-16-33/database_backup_2025-08-17_18-16-33.sql"
SQL_COMMAND = ["exec", "-T", "db", "sh", "-c",
               'MYSQL_PWD="$MYSQL_PASSWORD" exec mysql -u "$MYSQL_USER" "$MYSQL_DATABASE" --default-character-set=utf8mb4 --batch --skip-column-names']

def sql(statement: str) -> str:
    result = subprocess.run([*COMPOSE, *SQL_COMMAND], input=statement,
                            cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError("MySQL ha rifiutato l'operazione: " + result.stderr[-900:])
    return result.stdout.strip()

def query_rows() -> tuple[set[str], dict[str, int]]:
    existing = set(sql("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE();").splitlines())
    counts = {}
    for name in ORDER:
        if name in existing:
            escaped = name.replace("`", "``")
            counts[name] = int(sql(f"SELECT COUNT(*) FROM `{escaped}`;"))
    return existing, counts

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Create only missing tables after non-destructive preflight")
    args = parser.parse_args()
    expected = definitions(SOURCE)
    existing, counts = query_rows()
    print("Tabelle storiche presenti:", ", ".join(name for name in ORDER if name in existing) or "nessuna")
    print("Record totali attuali:", sum(counts.values()))
    unexpected = existing - set(ORDER)
    if unexpected:
        raise SystemExit("Altre tabelle presenti: " + ", ".join(sorted(unexpected)) + ". Nessuna modifica.")
    # Validate the exact legacy column order for each table already in the DB.
    for name in ORDER:
        if name not in existing:
            continue
        quoted = name.replace("'", "''")
        cols = sql("SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                   f"WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='{quoted}' ORDER BY ORDINAL_POSITION;").splitlines()
        expected_cols = [c for c in re.findall(r"^\s+`([^`]+)`\s+", expected[name], flags=re.M)]
        if cols != expected_cols:
            raise SystemExit("Colonne incompatibili in " + name + ": nessuna modifica")
    missing = [name for name in ORDER if name not in existing]
    if not missing:
        print("Schema completo: 7/7; nessuna modifica")
        return
    if any(counts.values()):
        raise SystemExit("Database già popolato: recupero automatico vietato. Necessaria revisione manuale.")
    print("Tabelle mancanti:", ", ".join(missing))
    if not args.apply:
        print("Solo verifica. Per creare le tabelle mancanti usa --apply.")
        return
    for name in missing:
        sql(expected[name])
        print("Creata:", name)
    after, _ = query_rows()
    if set(ORDER) != after:
        raise RuntimeError("Schema ancora incompleto: controlla errori e ripeti la diagnostica")
    print("Recupero completato: 7/7 tabelle, zero record importati.")

if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        print("Recupero interrotto:", error, file=sys.stderr)
        raise SystemExit(1)
