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

## Checkpoint web, database e pulsante applicazioni (19 ottobre 2026)

**Causa schema incompleto:** il vecchio backup MySQL conteneva CREATE TABLE in ordine
non adatto alle FOREIGN KEY (`magazzino` prima di `prodotti_completi`,
`prodotti_completi` prima di `modelli` e colori). L'inizializzazione del
volume poteva interrompersi a metà e MySQL tornare healthy al riavvio senza
avere tutte le tabelle. Il generatore adesso emette le sette tabelle nel corretto
ordine delle dipendenze, senza importare clienti, colori o ordini storici.

**Sul server Debian già in funzione: non cancellare il volume MySQL.**
Dopo aver integrato la PR e verificato che il codice del repository sia aggiornato:

```bash
cd /srv/apps/magazzino-tele
git status --short
git pull --ff-only origin master
python3 deploy/prepare_schema.py --refresh
python3 deploy/reconcile_schema.py
```

Se l'ultima verifica stampa tabelle mancanti ma *zero record*, e soltanto in quel caso:

```bash
python3 deploy/reconcile_schema.py --apply
python3 deploy/reconcile_schema.py --require-complete
```

Se invece riscontra dati, tabelle inattese o colonne differenti **si ferma**.
Non forzare l'operazione. È stata scelta una procedura con verifica manuale prima
del primo recupero per evitare modifiche irreversibili.

Una volta completato lo schema:

```bash
docker compose --env-file deploy/.env -f deploy/compose.yml up -d --build --wait
docker compose --env-file deploy/.env -f deploy/compose.yml ps
curl -fsS http://100.112.253.3:8082/health
```

L'indirizzo browser resta `http://serverale.tail7b83c3.ts.net:8082/`.
L'accesso è limitato dalla tailnet Tailscale, non dal login della webapp.
Verificare gli ACL/grants prima dell'utilizzo da parte di altri dispositivi.

### Flussi disponibili nella nuova interfaccia

- Home con creazione ordine, ricerca e filtro colore, clienti/fornitori,
  inventario e anagrafiche.
- Creazione **reale** ordine + righe prodotto, in una transazione, e aggiornamento
  dello stato evaso. Nessun ordine demo.
- Aggiornamento manuale giacenze per codice prodotto, senza toccare l'inventario
  automaticamente durante la creazione di un ordine.
- Importazione Excel `.xlsx` multipla con anteprima/validazione e rollback,
  senza sovrascrivere tabelle già popolate. Nomi file accettati:
  `customers.xlsx`, `modelli.xlsx`, `schema colori semplice.xlsx`,
  `prodotti_completi.xlsx`, `ordini.xlsx`, `magazzino.xlsx`,
  `ordiniprodotti.xlsx` (alias italiani supportati).
- Le colonne devono corrispondere allo schema storico: la verifica segnala
  eventuali intestazioni o riferimenti incompatibili prima del salvataggio.

### Limiti residui e comportamento della versione desktop

La vecchia app Tkinter aveva viste diverse: i primi pannelli della webapp
non erano stati derivati dai flussi esistenti. Le nuove pagine riprendono le
funzioni fondamentali, ma **non sono ancora equivalenti al 100%**:
la modifica completa delle righe di un ordine, le etichette personalizzate,
l'aggiornamento bidirezionale dello stock legato all'evasione e il ripristino
guidato dei backup richiedono test e progettazione separati. Nel sorgente
desktop alcune funzioni apparentemente presenti erano in realtà placeholder
(tra cui il salvataggio del form `CreaOrdinePage._save_order`).

### Backup del database Tele (separato da Cora)

Prima di iniziare l'uso quotidiano, l'operatore può generare una copia MySQL
consistente, in cartella privata *fuori* dalla repository:

```bash
cd /srv/apps/magazzino-tele
python3 deploy/backup_mysql.py
```

I file sono in `/srv/apps/magazzino-tele-backups/`, con checksum SHA256.
Questo **non equivale ancora a un ripristino collaudato**: provare il restore su
un database isolato e conservare un'ulteriore copia su disco indipendente.
Non caricare dump o file Excel dei clienti su GitHub.

### Cora aggiorna Tele senza collegarlo all'IA

Il pulsante **Gestisci applicazioni → Aggiorna e verifica** usa il servizio
`cora-updater` sull'host, aggiorna il branch approvato, ricostruisce i container
e controlla la salute della webapp. Non modifica PostgreSQL Cora, né concede
tool IA su MySQL Tele. Il codice host dell'updater va aggiornato separatamente
dopo il merge di Serveria (vedi `docs/MANAGED_APPS.md` in Serveria).

## Prima prova con gli archivi originali forniti il 19/10/2026

**Verifica dei formati reali:**
- `123.zip` contiene `customers.csv` (11.557 righe), `modelli.csv`
  (34), `schema colori semplice.csv` (131), `prodotti_completi.csv`
  (4.454), `magazzino.csv` (matrice 131x35 ma **nessuna quantità
  compilata**), `ordini.csv` e `Prodottiordini.csv` vuoti.
- Contiene anche `schema colori.csv`, con **codici discordanti** rispetto
  alla versione semplice. Per conservare i riferimenti di
  `prodotti_completi.csv`, l'importer sceglie la mappa semplice e
  **mostra un avviso** sulla discordanza; la mappa estesa non è persa.
- `excel.zip` contiene ~140 vecchi fogli `.xls` riferiti a singoli
  colori, più la mappa `.xlsx` che conta **143 righe**, non 143 codici
  necessariamente univoci (sono presenti duplicati e codici alfanumerici).
  Queste non sono le stesse tabelle relazionali MySQL del vecchio database.
  Non vengono trasformate arbitrariamente in stock.
- La fotografia dello schema ERD aggiunge `Shipments`: è un **disegno
  concettuale**, diverso dalle sette tabelle effettive dello storico SQL
  e dalle tabelle usate oggi dalla webapp. L'introduzione di spedizioni
  e dei dettagli colore richiede una migrazione esplicita, non è stata
  eseguita in questa versione per non compromettere le chiavi esistenti.

**Per la prima accensione:**
1. Eseguire un backup del database Tele esistente con
   `python3 deploy/backup_mysql.py` (il dump rimane fuori da Git).
2. Aggiornare la repository `master`, quindi ricostruire
   `docker compose --env-file deploy/.env -f deploy/compose.yml up -d --build --wait`.
3. Aprire `http://serverale.tail7b83c3.ts.net:8082/` da un dispositivo
   Tailscale autorizzato.
4. Menu **Importa Excel**: caricare direttamente `123.zip` con
   selettore `ZIP, CSV, XLS, XLSX`; avviare **Controlla file**.
5. Leggere l'elenco delle tabelle, i conteggi e gli avvisi sui file
   esclusi. Premere **Importa dopo verifica**. Il token anteprima è
   legato ai byte dei file e scade dopo un'ora.
6. Non caricare due volte lo stesso archivio: le tabelle già popolate
   bloccano intenzionalmente la duplicazione.
7. I fogli per singolo colore `.xls` vengono riconosciuti come sorgenti,
   ma **non assegnano scorte**. Si deve definire una mappa affidabile
   delle celle/formule per importarli automaticamente.
8. In caso di errore, raccogliere
   `docker compose --env-file deploy/.env -f deploy/compose.yml logs --tail=60 web`,
   ma non pubblicare le righe contenenti dati clienti.

### Pulsante temporaneo: Cancella tutta la memoria

Ambito **esclusivamente MySQL Magazzino Tele**. È disattivato per
impostazione predefinita. Per abilitarlo solo durante la costruzione
del gestionale, generare un segreto sul server e aggiungere le seguenti
chiavi nel file **privato** `deploy/.env`:

```ini
TELE_DEV_RESET_ENABLED=true
TELE_DEV_RESET_TOKEN=<genera-un-valore-casuale-lungo-almeno-24-caratteri>
```

Per generare il codice nel Debian: `python3 -c 'import secrets;print(secrets.token_urlsafe(36))'`.
Riavviare **soltanto il servizio web** con
`docker compose --env-file deploy/.env -f deploy/compose.yml up -d --no-deps web`.

L'operatore deve digitare esattamente `CANCELLA MAGAZZINO TELE`, inserire
il token privato e dare conferma. Il server crea **prima** un backup
JSON compresso in un volume Docker persistente `tele_reset_backups`
(indipendente dal volume MySQL), e poi cancella in transazione solo
le righe delle sette tabelle, senza eliminare le tabelle. **Il reset
non cancella mai Cora, il NAS, foto o dati delle altre applicazioni.**

Non esporre il token in chat, screenshot o GitHub. Dopo i collaudi
rimuovere le due variabili dal file privato, spegnere la funzione e
togliere il pulsante dal frontend.

**Nota sicurezza:** fintanto che la webapp non usa login applicativo,
mantenere la porta HTTP vincolata all'IP Tailscale e restringere gli
accessi con le grants/ACL Tailscale.

## Backup SQL scaricabile e ripristinabile dal browser

Nel gestionale, aprire **Backup SQL**:
- **Scarica backup SQL (.sql)**: ottiene `database-backup-YYYY-MM-DD_HH-MM.sql`
  contenente CREATE TABLE e INSERT delle sette tabelle MySQL attuali.
  Conservare il file in privato, perché contiene dati cliente.
- **Verifica backup SQL**: aprire un file `.sql`. Il server controlla la
  sintassi supportata, i nomi delle tabelle, le colonne e i vincoli sul
  database, eseguendo l'inserimento dentro una transazione poi annullata.
- **Importa backup dopo verifica**: richiede lo stesso identico file verificato;
  conferma l'importazione soltanto se le tabelle di destinazione non
  contengono record; in caso di errori esegue rollback.

**Compatibilità di formato:** su Windows l'estensione `.sql` può apparire come
«Microsoft SQL Server Query File» anche quando il contenuto è MySQL.
Il file esportato è un dump **MySQL** con estensione `.sql`, non una
copia binaria `.bak` e non uno script T-SQL eseguibile su SQL Server.
Si accettano MySQL dump con INSERT e un sottoinsieme di SQL Server con
INSERT espliciti compatibili. Schema SQL Server distinto (`[dbo].[Shipments]`,
colonne `business_name`, ecc.), funzioni T-SQL, stored procedure e
modifiche DDL richiedono una migrazione concordata e non vengono eseguite.
Non basta rinominare un file `.bak` in `.sql`.

Il vecchio dump MySQL `backup/2025-08-17_18-16-33/database_backup_2025-08-17_18-16-33.sql`
è incluso nei test automatici per la lettura del formato. Importarlo nel
database reale è una **scelta separata** dall'importazione di `123.zip`;
non caricare entrambe le sorgenti come se si potessero sommare.
Le operazioni di anteprima e ripristino sono limitate a 25 MB/200.000 record
per file e non eseguono nessun `DROP`, `ALTER`, `DELETE` o SQL arbitrario.

**Correzione prodotti omonimi:** due codici differenti possono avere lo stesso
modello e nome colore. Il codice prodotto identifica il record; la sola
combinazione di nomi non è una chiave univoca. Le celle vuote della matrice
`magazzino.csv` non richiedono associazione a un prodotto. Se la cella
contiene una quantità ma la coppia modello/colore è ambigua, l'anteprima
mostra i codici candidati e richiede una fonte con codice esatto.
