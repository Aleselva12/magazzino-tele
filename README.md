# 🏭 Magazzino Tele - Sistema di Gestione

Un sistema completo di gestione magazzino per tessuti con interfaccia grafica moderna e database MySQL.

## 🚀 Features Principali

- **📋 Gestione Ordini Completa** - Visualizzazione, modifica, ricerca e filtraggio ordini
- **🎨 Interfaccia Grafica Moderna** - Design pulito con bottoni bianchi e UI intuitiva
- **🗄️ Database MySQL** - Struttura normalizzata con foreign keys e integrità referenziale
- **🔍 Ricerca Avanzata** - Filtri per cliente, modello, colore, stato evaso
- **✏️ Modifica Ordini** - Dialog dedicato per modificare tutti i campi ordine
- **📊 Statistiche Real-time** - Contatori ordini evasi e in lavorazione
- **🔒 Type Safety** - Annotazioni complete Python per robustezza codice

## 🏗️ Architettura

```
magazzino-tele/
├── 🚀 run_magazzino.py          # Entry point applicazione
├── 📁 backend/
│   └── crud.py                   # Operazioni database MySQL
├── 📁 interfaccia/
│   ├── pages/
│   │   ├── gestisci_ordini.py   # ⭐ Gestione ordini principale
│   │   ├── welcome.py           # Pagina benvenuto
│   │   └── home.py              # Homepage
│   ├── utils/
│   │   └── styling.py           # Stili UI
│   └── widgets/
│       └── autocomplete.py      # Widget autocomplete
└── 📁 test/                     # Test e utility
```

## 🛠️ Installazione

### Prerequisiti
- Python 3.13+
- MySQL Server
- pip (gestore pacchetti Python)

### Setup Database
1. Installa MySQL Server
2. Crea database `magazzino_tele`
3. Importa schema dalle tabelle in `DATABASE PROVA FINALE/`

### Installazione Dipendenze
```bash
# Attiva ambiente virtuale
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Installa dipendenze
pip install mysql-connector-python
pip install tkinter  # Di solito incluso in Python
```

## 🚀 Avvio Applicazione

```bash
python run_magazzino.py
```

## 📱 Utilizzo

### Gestione Ordini
1. **Visualizza Ordini** - Lista completa con dettagli cliente, modello, colore
2. **Cerca/Filtra** - Usa i campi di ricerca per trovare ordini specifici
3. **Modifica Ordine** - Doppio click su ordine per aprire dialog modifica
4. **Salva Modifiche** - Usa pulsante "💾 Salva Modifiche" per confermare
5. **Elimina Ordine** - Pulsante "🗑️ Elimina Ordine" con conferma

### Dialog Modifica Ordini
- **Campi Modificabili**: Cliente, Codice Cliente, Modello, Colore, Quantità, Note
- **Checkbox Evaso**: Segna ordine come completato
- **Validazione**: Controlli automatici su campi obbligatori
- **Pulsanti**: Salva, Elimina, Annulla

## 🎨 Design System

### Colori
- **Bottoni Principali**: Bianco con bordo grigio (`WhiteButton.TButton`)
- **Successo**: Verde per conferme
- **Pericolo**: Rosso per eliminazioni
- **Warning**: Arancione per avvertimenti

### Layout
- **Grid System**: Layout organizzato con padding consistente
- **Responsive**: Interfaccia adattiva alle dimensioni finestra
- **Icons**: Emoji per migliorare UX (💾 🗑️ ❌ ✅)

## 🗄️ Database Schema

### Tabelle Principali
- `ordini` - Ordini clienti con dettagli
- `prodotti_completi` - Catalogo prodotti
- `ordiniprodotti` - Relazione ordini-prodotti (foreign keys)
- `customers` - Anagrafica clienti
- `modelli` - Tipologie prodotti

### Relazioni
- `ordini.id` ↔ `ordiniprodotti.ordine_id`
- `prodotti_completi.id` ↔ `ordiniprodotti.prodotto_id`

## 📊 Statistiche Progetto

- **Files**: 50 files
- **Righe di Codice**: 4,709 lines
- **Linguaggi**: Python 95%, SQL 5%
- **Framework**: Tkinter (GUI), MySQL (Database)

## 🔧 Funzionalità Avanzate

### Ricerca Intelligente
- **Ricerca Globale**: Cerca in tutti i campi contemporaneamente
- **Filtri Specifici**: Cliente, modello, colore, stato evaso
- **Aggiornamento Real-time**: Risultati istantanei durante digitazione

### Gestione Errori
- **Validazione Input**: Controlli automatici su quantità e campi obbligatori
- **Messaggi Informativi**: Feedback chiaro per ogni operazione
- **Rollback Automatico**: Sicurezza nelle operazioni database

### Type Safety
- **Annotazioni Complete**: Tutti i metodi e variabili tipizzati
- **Type Aliases**: `OrderDataTuple` per strutture dati complesse
- **IDE Support**: Intellisense e controllo errori automatici

## 🐛 Troubleshooting

### Problemi Comuni
- **Database non raggiungibile**: Verifica MySQL Server attivo
- **Import Error**: Controlla ambiente virtuale attivato
- **GUI non visualizzata**: Verifica installazione Tkinter

### Log e Debug
- Console output per operazioni database
- Messaggi di errore dettagliati
- Statistiche caricamento dati

## 🤝 Contribuire

1. Fork del repository
2. Crea feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit modifiche (`git commit -m 'Add AmazingFeature'`)
4. Push branch (`git push origin feature/AmazingFeature`)
5. Apri Pull Request

## 📝 License

Progetto sviluppato per gestione magazzino tessuti.

## 👨‍💻 Sviluppo

**Generated by Copilot** - Assistente AI per sviluppo software  
**Data**: Agosto 2025  
**Versione**: 1.0.0

---

### 🎯 Prossimi Sviluppi

- [ ] Aggiunta nuovi ordini da interfaccia
- [ ] Export/Import Excel
- [ ] Report e statistiche avanzate
- [ ] Backup automatico database
- [ ] Sistema notifiche
- [ ] API REST per integrazione esterna
