# Chat di assistenza clienti in tempo reale con smistamento automatico dei ticket

![CI](https://github.com/duate18/realtime-support-chat-triage/actions/workflows/ci.yml/badge.svg)

[English](README.md) | Italiano

Una piccola demo di help desk per un marketplace tra privati: i clienti scrivono a un operatore in tempo reale, e un classificatore di testo leggero **smista ogni messaggio in arrivo** (categoria, lingua, priorità) e **suggerisce una risposta all'operatore**. Quando il modello non è sicuro, lo dice invece di tirare a indovinare.

> Progetto personale indipendente, fatto per esercitarmi con backend in tempo reale e machine learning applicato. Non è affiliato a nessuna azienda. Tutti i dati sono sintetici e il testo dell'help center è inventato.

L'interfaccia delle pagine è in inglese; i messaggi si possono scrivere sia in italiano sia in inglese.

![Demo: un cliente scrive, la console ordina la coda, l'operatore risponde con la risposta suggerita](docs/demo.gif)

<details>
<summary>Schermate</summary>

![Console operatore](docs/agent-console.png)
![Chat del cliente](docs/customer-chat.png)

</details>

## Cosa fa

- **Chat del cliente** e **console dell'operatore**, collegate via WebSocket, una stanza per ticket.
- **Coda** per gli operatori: prima i ticket in attesa (priorità più alta tra i loro messaggi senza risposta, poi chi aspetta da più tempo), in fondo quelli già risposti. Si aggiorna in tempo reale.
- **Smistamento** di ogni messaggio del cliente: una di 5 categorie (spedizione, rimborso, articolo non conforme, account, pagamento), lingua (IT/EN), priorità e una risposta suggerita presa da una piccola FAQ.
- Il suggerimento va **solo all'operatore**, mai al cliente. Se la sicurezza del modello è sotto una soglia, la console mostra "needs a person" e non suggerisce nulla.
- Lo storico sopravvive all'aggiornamento della pagina, e le pagine si riconnettono da sole se il server si riavvia.
- Limiti sul server: i messaggi sopra i 1.000 caratteri vengono rifiutati, quelli vuoti ignorati, e una connessione può inviare al massimo 5 messaggi ogni 10 secondi. Le pagine mostrano l'errore invece di non fare nulla.

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

### Valutazione su dati veri e pubblici (Banking77)

I miei test sono troppo piccoli per dire quanto vale davvero il metodo, quindi `scripts/evaluate_banking77.py` esegue lo stesso modello (TF-IDF su caratteri + regressione logistica, lo stesso codice dell'app) su [Banking77](https://github.com/PolyAI-LDN/task-specific-datasets): 13.083 messaggi veri di clienti di una banca online, 77 categorie, con un test fisso di 3.080 messaggi che il modello non vede mai in addestramento. Dataset di Casanueva et al. (2020), licenza CC BY 4.0; lo scarica lo script e non è salvato in questo repository.

È un **compito diverso** (77 intenti bancari, non le mie 5 categorie da marketplace), quindi misura il metodo e l'idea della soglia di sicurezza, non le categorie dell'app.

![Valutazione su Banking77: precisione contro quota di messaggi a cui si risponde, e calibrazione](docs/banking77_coverage_accuracy.png)

| Modello (addestrato su 10.003 messaggi) | Test pulito | 2% di refusi | 5% di refusi |
|---|---|---|---|
| TF-IDF su caratteri (quello dell'app) | **88,2%** | 87,5% | 85,2% |
| TF-IDF su parole (confronto) | 85,7% | 81,2% | 73,3% |

- La baseline "classe più frequente" arriva all'1,3%. Per il modello dell'app l'intervallo al 95% sul test pulito è 87,1-89,3% (3.080 messaggi, quindi molto più stretto di quello dei miei 30); F1 macro 0,881.
- I refusi sono inseriti solo nei messaggi di test (ogni lettera ha il 2% o il 5% di probabilità di essere tolta, doppiata, scambiata o sostituita), dopo l'addestramento su testo pulito. Gli n-grammi di caratteri perdono 3 punti con il 5% di rumore, le parole 12. È il motivo per cui li ho scelti.
- **Tacere quando non si è sicuri funziona.** Alla soglia 0,35 il modello risponde al 71% dei messaggi e il 96,0% delle risposte è giusto, contro l'88,2% quando risponde sempre. Tace su 274 dei suoi 362 errori. A 0,5 risponde al 54% dei messaggi con il 98,3% di risposte giuste.
- **La sicurezza è calibrata male, nella direzione prudente.** L'errore di calibrazione (ECE) è 0,352: i messaggi per cui il modello dice "sicuro all'8%" sono giusti il 54% delle volte. Quindi il punteggio serve solo a ordinare i messaggi dal più sicuro al meno sicuro, e la soglia va letta dalla tabella sopra, non interpretata come una probabilità.
- La maggior parte degli errori è tra intenti quasi uguali (per esempio `virtual_card_not_working` previsto come `get_disposable_virtual_card`, 16 volte), che anche una persona troverebbe ambigui.
- Avvertenza: la soglia 0,35 l'avevo scelta prima sul mio test scritto a mano con 5 categorie e non è stata ottimizzata su Banking77. Qui dà per caso un compromesso sensato, ma con un numero diverso di categorie il valore giusto cambia.

I numeri completi, il seme e la versione della libreria usata sono in [`docs/banking77_report.json`](docs/banking77_report.json).

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

Test (49): `python -m pytest -v`

Valutazione su Banking77 (serve internet la prima volta, circa 30 secondi):

```bash
pip install -r requirements-eval.txt
python -m scripts.evaluate_banking77
```

Con Docker: `docker build -t live-support-demo . && docker run --rm -p 8000:8000 live-support-demo`. Il modello viene addestrato durante la build. A ogni push la CI costruisce l'immagine e controlla che risponda.

## Come è fatto

- `GET /` pagina del cliente, `GET /agent` console, `GET /health`, `GET /api/tickets/{id}` storico (404 se il ticket non esiste).
- `WS /ws/{ticket_id}?role=customer|agent`: si invia testo semplice; si riceve `{"type": "message", "from", "text"}`. Gli operatori ricevono anche `{"type": "suggestion", category, confidence, language, priority, needs_human, suggestion}`.
- `WS /ws-agents`: la "lobby" della console; riceve `{"type": "queue", "tickets": [...]}` alla connessione e dopo ogni messaggio.
- Lo smistamento gira in un thread separato, così il lavoro sulla CPU non blocca le chat degli altri.
- Le pagine sono HTML e JavaScript semplici, senza framework. Il testo degli utenti è sempre inserito con `textContent`, mai come HTML.

```
app/        main.py (stanze WebSocket, lobby, REST, pagine) · tickets.py (archivio + ordine della coda)
            triage.py (categoria, lingua, priorità, risposta) · classifier.py · limits.py (limite di frequenza) · pages/
scripts/    generate_data.py (ticket sintetici, con seme fisso) · train.py (addestramento + valutazione)
            evaluate_banking77.py (valutazione su dati veri e pubblici)
data/       tickets.csv (910 sintetici) · faq.json (help center inventato) · handwritten_test.csv (30)
tests/      49 test, tra cui flussi WebSocket, ordine della coda con un orologio finto, limiti e funzioni di valutazione
```

## Limiti

- Il modello a 5 categorie è addestrato su dati sintetici. I ticket veri sarebbero più sporchi, e non ne ha mai visto uno. Banking77 mostra che il metodo regge su testo vero, non che lo reggano queste 5 categorie.
- Il punteggio di sicurezza non è calibrato (vedi sopra).
- Nessuna autenticazione: chiunque può aprire `/agent`.
- I ticket stanno in memoria e si perdono al riavvio, e nulla limita quanti se ne possono creare. Lo stato è per processo, quindi funziona con un solo worker.
- Il limite di lunghezza viene controllato dopo aver letto tutto il messaggio (uvicorn accetta messaggi WebSocket fino a 16 MiB se non si abbassa `--ws-max-size`), e il limite di frequenza è per connessione, quindi aprendo molte connessioni si aggira.
- Il riconoscimento della lingua conosce solo italiano e inglese e può sbagliare sui messaggi molto corti.

## Cosa farei dopo

1. Raccogliere ed etichettare ticket veri, e valutare con un insieme di test separato.
2. Calibrare le probabilità (per esempio con la temperature scaling calcolata su un insieme di validazione) e regolare allo stesso modo la regolarizzazione, poi rimisurare sul test mai toccato.
3. Salvare i ticket su un database (SQLite/Postgres) e aggiungere l'autenticazione degli operatori.
4. Spostare stanze e coda su un broker condiviso (per esempio Redis pub/sub) per usare più worker.
