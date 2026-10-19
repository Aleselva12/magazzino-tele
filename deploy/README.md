# Magazzino Tele sul Debian (autonomo da Cora)

Questa è una prima versione **web** indipendente. La GUI Tkinter storica resta disponibile nella repository per riferimento: sul PC della zia non è richiesta alcuna installazione eccetto Tailscale e un browser.

## Cosa esiste

- `web/app.py`: viste browser per le 7 tabelle storiche, ricerca, aggiunta e modifica generica di record. I form guidati per gli ordini e l'importazione Excel restano da realizzare/testare.
- `deploy/compose.yml`: MySQL 8.4 persistente, web Gunicorn, riavvio automatico e healthcheck; web sulla **sola interfaccia Tailscale** (`8082`), nessuna esposizione MySQL all'host.
- `deploy/prepare_schema.py`: legge il dump SQL già presente su GitHub e crea soltanto CREATE TABLE, **non importa INSERT o dati**. Verifica che esistano le sette tabelle. Genera un file SQL escluso da Git.
- Nessun collegamento a Serveria, agenti o IA. Nessun login nell'interfaccia web; la porta deve essere limitata a Tailscale con ACL/grants.

## Prima installazione (sul Debian, NON eseguita da questa PR)

```bash
sudo mkdir -p /srv/apps
cd /srv/apps
git clone https://github.com/Aleselva12/magazzino-tele.git
cd magazzino-tele
git checkout feat/web-tailscale-debian
python3 deploy/prepare_schema.py
cp deploy/.env.example deploy/.env
chmod 600 deploy/.env
# Modificare deploy/.env con IP Tailscale Debian e password random MySQL distinte.
docker compose --env-file deploy/.env -f deploy/compose.yml config
docker compose --env-file deploy/.env -f deploy/compose.yml up -d --build
docker compose --env-file deploy/.env -f deploy/compose.yml ps
```

Nota: GitHub contiene un backup storico con clienti e altri dati; **non** usarlo per il primo popolamento. Il file `deploy/init/01-schema.sql` è l'unico SQL applicato sul primo volume vuoto. L'init di MySQL gira solo quando il volume database è nuovo: rigenerare lo schema non aggiorna database già inizializzati.

L'interfaccia sarà `http://<IP-TAILSCALE-DEBIAN>:8082` dai dispositivi che Tailscale autorizza a connettersi al server. Configurare ACL/grants Tailscale per permettere soltanto il dispositivo della zia e quelli amministrativi sulla porta 8082. Verificare binding locale e Docker firewall. Nessuna apertura del router.

## Requisiti ancora aperti prima dell'uso definitivo

1. Esaminare `deploy/init/01-schema.sql` prodotto dallo storico: charset, tipi, indici, FK e PK devono corrispondere al vecchio MySQL. Non modificare i dati storici automaticamente.
2. Collaudare creazione ordine e righe associate e aggiungere i flussi guidati che sostituiscono quelli Tkinter. La UI attuale è genericamente CRUD e non completa il workflow storico.
3. Sviluppare importatore Excel per le sette tabelle con anteprima, mapping colonne reali, validazione dei riferimenti e rollback atomico. Non inserire dati d'esempio.
4. Creare backup MySQL dedicato e provarne il restore in un volume nuovo; il backup Cora non include Tele.
5. Il vecchio progetto contiene credenziali MySQL hardcoded nei sorgenti pubblici: NON riutilizzarle; rimuovere i riferimenti e ruotare i segreti storici se ancora attivi.

## Separazione

```text
/srv/apps/cora/                 # applicazione IA separata
/srv/apps/magazzino-tele/       # checkout Git originale
    web/                       # interfaccia browser
    deploy/                    # compose, config e schema
Docker volume magazzino-tele_tele_mysql  # MySQL persistente autonomo
```

Non passare credenziali di Tele a Cora e non montare i volumi Tele nei container Cora. Per ora l'accesso remoto è limitato al browser via Tailscale. HTTP non offre cifratura end-to-end oltre il trasporto Tailscale; se un giorno serve accesso esterno alla tailnet, rivalutare HTTPS e autenticazione.


## Correzione avvio MySQL: permessi initdb

Se i log riportano `ls: cannot open directory '/docker-entrypoint-initdb.d/': Permission denied`,
la versione iniziale montava `deploy/init/` come directory host read-only. Su Debian,
un permesso insufficiente sul percorso montato rendeva MySQL inutilizzabile.

Il Dockerfile `deploy/init/Dockerfile` inserisce ora il file generato
`01-schema.sql` direttamente nell'immagine MySQL. **Non usare un mount**
`./init:/docker-entrypoint-initdb.d`, non serve più.

Dopo il merge, sul Debian già clonato:

```bash
cd /srv/apps/magazzino-tele
git status --short
git pull --ff-only origin master
test -s deploy/init/01-schema.sql || python3 deploy/prepare_schema.py
docker compose --env-file deploy/.env -f deploy/compose.yml config --quiet
docker compose --env-file deploy/.env -f deploy/compose.yml up -d --build --wait
docker compose --env-file deploy/.env -f deploy/compose.yml ps
```

**Non eseguire `docker compose down -v` né cancellare il volume del database.**
Se l'inizializzazione MySQL è avvenuta soltanto in parte, il primo volume potrebbe
non ricevere nuovamente gli script DDL: verificare `SHOW TABLES`, stato e log.
In quel caso serve una procedura di recupero specifica dopo aver verificato che
il volume non contenga dati. Nessuna re-inizializzazione automatica è prevista.

Lo schema SQL generato rimane fuori da Git e viene copiato nell'immagine durante
il build; la password MySQL continua a essere letta dal file privato `deploy/.env`.
