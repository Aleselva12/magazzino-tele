"""Extract schema-only DDL from an existing MySQL dump; never copy INSERT data."""
from pathlib import Path
import argparse
import re

TABLE_RE = re.compile(r"^CREATE TABLE\s+(?:IF NOT EXISTS\s+)?`?[^\s(]+`?", re.I)
ALLOWED = {"customers","magazzino","modelli","ordini","ordiniprodotti","prodotti_completi","schema colori semplice"}

def extract(source: Path) -> str:
    raw = source.read_text(encoding="utf-8-sig")
    result = []
    current = []
    collecting = False
    for line in raw.splitlines():
        line_clean = line.strip()
        if not collecting and TABLE_RE.match(line_clean):
            table = re.search(r"CREATE TABLE\s+(?:IF NOT EXISTS\s+)?(?:`([^`]+)`|([^\s(]+))",line_clean,re.I)
            if table and (table.group(1) or table.group(2)) in ALLOWED:
                collecting = True
                current = [line]
        elif collecting:
            current.append(line)
        if collecting and line_clean.endswith(";"):
            result.append("\n".join(current))
            current = []
            collecting = False
    if len(result) != len(ALLOWED):
        raise SystemExit(f"Attese {len(ALLOWED)} tabelle storiche; trovate {len(result)}. NON inizializzo un database incompleto.")
    return "SET NAMES utf8mb4;\n" + "\n\n".join(result) + "\n"

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("backup/2025-08-17_18-16-33/database_backup_2025-08-17_18-16-33.sql"))
    parser.add_argument("--output", type=Path, default=Path("deploy/init/01-schema.sql"))
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Output già presente: non sovrascrivo uno schema esistente")
    sql = extract(args.source)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(sql,encoding="utf-8")
    print(f"Schema generato: {args.output} (SOLO CREATE TABLE; nessun dato)")
