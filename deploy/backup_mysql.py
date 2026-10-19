"""Create a restricted MySQL dump outside Git and the app source tree."""
from datetime import datetime, timezone
from pathlib import Path
import gzip
import hashlib
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
TARGET=Path("/srv/apps/magazzino-tele-backups")
COMPOSE=["docker","compose","--env-file","deploy/.env","-f","deploy/compose.yml"]

def main():
    original=os.umask(0o077)
    try:
        TARGET.mkdir(mode=0o700, parents=True, exist_ok=True)
        if TARGET.is_symlink():raise ValueError("Directory backup non valida")
        filename=TARGET/("mysql-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+".sql.gz")
        command=[*COMPOSE,"exec","-T","db","sh","-c",
                 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -u root --single-transaction --set-gtid-purged=OFF --routines --triggers --databases "$MYSQL_DATABASE"']
        process=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            with filename.open("xb") as out, gzip.GzipFile(fileobj=out,mode="wb") as compressed:
                while data:=process.stdout.read(1024*1024):
                    compressed.write(data)
            err=process.stderr.read()
            if process.wait()!=0:
                filename.unlink(missing_ok=True)
                raise RuntimeError("mysqldump fallito: "+err.decode(errors="replace")[-700:])
        except Exception:
            process.kill()
            process.wait()
            filename.unlink(missing_ok=True)
            raise
        sha=hashlib.sha256(filename.read_bytes()).hexdigest()
        filename.with_suffix(filename.suffix+".sha256").write_text(sha+"  "+filename.name+"\n")
        print("Backup MySQL creato:",filename)
        print("SHA256:",sha)
        print("Conservare anche una copia su un disco separato.")
    finally:
        os.umask(original)

if __name__=="__main__":
    try:main()
    except (OSError,RuntimeError,ValueError) as e:
        print("Backup non riuscito:",e,file=sys.stderr)
        raise SystemExit(1)
