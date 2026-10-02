# Chat di assistenza in tempo reale con assistente di smistamento

![CI](https://github.com/duate18/realtime-support-triage/actions/workflows/ci.yml/badge.svg)

[English](README.md) | Italiano

Una piccola demo di help desk per un marketplace tra privati: i clienti scrivono a un operatore in tempo reale, e un classificatore di testo leggero **smista ogni messaggio in arrivo** (categoria, lingua, priorità) e **suggerisce una risposta all'operatore**. Quando il modello non è sicuro, lo dice invece di tirare a indovinare.

> Progetto personale indipendente, fatto per esercitarmi con backend in tempo reale e machine learning applicato. Non è affiliato a nessuna azienda. Tutti i dati sono sintetici e il testo dell'help center è inventato.

L'interfaccia delle pagine è in inglese; i messaggi si possono scrivere sia in italiano sia in inglese.

![Console operatore](docs/agent-console.png)
![Chat del cliente](docs/customer-chat.png)

## Cosa fa

- **Chat del cliente** e **console dell'operatore**, collegate via WebSocket, una stanza per ticket.
- **Coda** per gli operatori: prima i ticket in attesa (priorità più alta, poi chi aspetta da più tempo), in fondo quelli già risposti. Si aggiorna in tempo reale.
- **Smistamento** di ogni messaggio del cliente: una di 5 categorie (spedizione, rimborso, articolo non conforme, account, pagamento), lingua (IT/EN), priorità e una risposta suggerita presa da una piccola FAQ.
- Il suggerimento va **solo all'operatore**, mai al cliente. Se la sicurezza del modello è sotto una soglia, la console mostra "needs a person" e non suggerisce nulla.
- Lo storico sopravvive all'aggiornamento della pagina, e le pagine si riconnettono da sole se il server si riavvia.

## Come funziona lo smistamento

- **Classificatore:** TF-IDF su n-grammi di caratteri (2-5) + regressione logistica (scikit-learn). Gli n-grammi di caratteri gestiscono abbastanza bene i refusi e il mix italiano/inglese nello stesso modello.
- **Soglia di sicurezza:** 0,35. Sotto questa soglia il messaggio va a una persona.
- **Priorità:** regole esplicite e leggibili: una priorità di base per categoria, aumentata da parole urgenti ("twice", "blocked", "scam", "due volte", "truffa"...). Ho preferito regole che so spiegare a un secondo modello che non saprei valutare.
- **Lingua:** conteggio semplice di parole molto comuni in italiano e in inglese.

## Risultati (leggi le avvertenze)

| Valutazione | Accuratezza |
|---|---|
| Classe più frequente (baseline) | 22% |
| Test sintetico (182 messaggi) | 100% |
| 30 messaggi scritti a mano da me | 83,3% |

- Il dato sintetico è **gonfiato**: messaggi di addestramento e di test vengono dagli stessi modelli di frase. Lo riporto solo per mostrare che il modello impara il compito, non per dire che funziona.
- Il test scritto a mano è il dato onesto, ma con 30 messaggi l'incertezza è grande: circa 66-93% con confidenza al 95%.
- Con la soglia a 0,35 il modello ha risposto da solo a 22 dei 30 messaggi scritti a mano, e 21 erano giusti. Gli 8 passati a una persona comprendono 4 dei suoi 5 errori.
- La sicurezza è un punteggio grezzo del modello, non una probabilità calibrata.

## Come provarlo

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m scripts.train          # crea models/classifier.joblib da data/tickets.csv
uvicorn app.main:app --reload
```

Apri `http://127.0.0.1:8000/agent` (console) e `http://127.0.0.1:8000/` in una o più altre schede (ogni scheda è un cliente diverso). Prova, per esempio:

- `Parcel still not here, tracking says nothing since last week` (priorità bassa)
- `Mi hanno addebitato due volte l'ordine #12345, chiedo il rimborso.` (priorità alta: sale in cima alla coda)
- `I can't sign in anymore, the app keeps logging me out` (il modello non è sicuro, quindi nessun suggerimento)

Test (27): `python -m pytest -v`

Con Docker: `docker build -t live-support-demo . && docker run --rm -p 8000:8000 live-support-demo`. Il modello viene addestrato durante la build. A ogni push la CI costruisce l'immagine e controlla che risponda.

## Come è fatto

- `GET /` pagina del cliente, `GET /agent` console, `GET /health`, `GET /api/tickets/{id}` storico (404 se il ticket non esiste).
- `WS /ws/{ticket_id}?role=customer|agent`: si invia testo semplice; si riceve `{"type": "message", "from", "text"}`. Gli operatori ricevono anche `{"type": "suggestion", category, confidence, language, priority, needs_human, suggestion}`.
- `WS /ws-agents`: la "lobby" della console; riceve `{"type": "queue", "tickets": [...]}` alla connessione e dopo ogni messaggio.
- Lo smistamento gira in un thread separato, così il lavoro sulla CPU non blocca le chat degli altri.
- Le pagine sono HTML e JavaScript semplici, senza framework. Il testo degli utenti è sempre inserito con `textContent`, mai come HTML.

```
app/        main.py (stanze WebSocket, lobby, REST, pagine) · tickets.py (archivio + ordine della coda)
            triage.py (categoria, lingua, priorità, risposta) · classifier.py · pages/
scripts/    generate_data.py (ticket sintetici, con seme fisso) · train.py (addestramento + valutazione)
data/       tickets.csv (910 sintetici) · faq.json (help center inventato) · handwritten_test.csv (30)
tests/      27 test, tra cui flussi WebSocket e ordine della coda con un orologio finto
```

## Limiti

- I dati di addestramento sono sintetici. I ticket veri sarebbero più sporchi, e questo modello non ne ha mai visto uno.
- La priorità è calcolata solo sull'**ultimo** messaggio del cliente: un seguito come "hello?" può abbassare la priorità di un ticket urgente.
- Nessuna autenticazione: chiunque può aprire `/agent`.
- I ticket stanno in memoria e si perdono al riavvio. Lo stato è per processo, quindi funziona con un solo worker.
- La lunghezza dei messaggi è limitata solo nel browser, non sul server. Nessun limite di frequenza.
- Il riconoscimento della lingua conosce solo italiano e inglese e può sbagliare sui messaggi molto corti.

## Cosa farei dopo

1. Raccogliere ed etichettare ticket veri, e valutare con un insieme di test separato e probabilità calibrate.
2. Salvare i ticket su un database (SQLite/Postgres) e aggiungere l'autenticazione degli operatori.
3. Tenere la priorità più alta tra i messaggi senza risposta di un ticket.
4. Spostare stanze e coda su un broker condiviso (per esempio Redis pub/sub) per usare più worker.
