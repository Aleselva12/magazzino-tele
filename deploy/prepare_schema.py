"""Generate empty MySQL schema from the historical SQL dump, in FK-safe order.

No INSERT, DROP or private customer records are carried over.
"""
from pathlib import Path
import argparse
import re

ORDER = (
    "customers",
    "modelli",
    "schema colori semplice",
    "prodotti_completi",
    "ordini",
    "magazzino",
    "ordiniprodotti",
)
TABLE_START = re.compile(r"^CREATE TABLE\s+(?:IF NOT EXISTS\s+)?`([^`]+)`\s*\(", re.I)

def definitions(source: Path) -> dict[str, str]:
    sql = source.read_text(encoding="utf-8-sig")
    found = {}
    current = []
    name = None
    for line in sql.splitlines():
        if name is None:
            match = TABLE_START.match(line.strip())
            if match:
                name = match.group(1)
                current = [line]
        else:
            current.append(line)
        if name is not None and line.strip().endswith(";"):
            if name in found:
                raise ValueError("Tabella duplicata: " + name)
            found[name] = "\n".join(current)
            current, name = [], None
    if set(found) != set(ORDER):
        raise ValueError("Schema inatteso, trovate: " + ", ".join(sorted(found)))
    for name, statement in found.items():
        refs = re.findall(r"\bREFERENCES\s+`([^`]+)`", statement, re.I)
        if any(ref not in ORDER or ORDER.index(ref) >= ORDER.index(name) for ref in refs):
            raise ValueError("Dipendenza FK non rispettata per: " + name)
    return found

def extract(source: Path) -> str:
    d = definitions(source)
    return "SET NAMES utf8mb4;\n" + "\n\n".join(d[name] for name in ORDER) + "\n"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path,
        default=Path("backup/2025-08-17_18-16-33/database_backup_2025-08-17_18-16-33.sql"))
    parser.add_argument("--output", type=Path, default=Path("deploy/init/01-schema.sql"))
    parser.add_argument("--refresh", action="store_true",
        help="Replace only the locally generated schema file with FK-safe DDL")
    args = parser.parse_args()
    if args.output.exists() and not args.refresh:
        raise SystemExit("Schema già presente: usa --refresh per rigenerarlo esplicitamente")
    sql = extract(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        existing = args.output.read_text()
        if re.search(r"(?im)^\s*(INSERT|REPLACE|UPDATE|DELETE|DROP)\b", existing):
            raise SystemExit("Il file esistente contiene modifiche dati: rifiuto sovrascrittura")
    args.output.write_text(sql, encoding="utf-8")
    print(f"Schema DDL: {len(ORDER)} tabelle, in ordine FK; nessun record")

if __name__ == "__main__":
    main()
