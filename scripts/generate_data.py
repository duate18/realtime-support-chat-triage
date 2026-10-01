"""Genera ticket di assistenza INVENTATI (italiano e inglese) e un help center finto.

Usa solo la libreria standard di Python. Il seme fisso rende i dati riproducibili.
Uso:  python scripts/generate_data.py
"""
import csv
import json
import random
from pathlib import Path

rng = random.Random(42)
OUT = Path("data")
PER_GROUP = 100  # ticket per categoria e lingua

ITEMS = {
    "it": ["la giacca", "la borsa", "le scarpe", "il vestito", "i jeans", "il maglione"],
    "en": ["the jacket", "the bag", "the shoes", "the dress", "the jeans", "the sweater"],
}
OPENERS = {
    "it": ["Buongiorno,", "Salve,", "Ciao,", ""],
    "en": ["Hello,", "Hi,", "Good morning,", ""],
}
CLOSERS = {
    "it": ["Grazie.", "Potete aiutarmi?", "Attendo una risposta.", ""],
    "en": ["Thanks.", "Can you help me?", "Waiting for your reply.", ""],
}

TEMPLATES = {
    "shipping": {
        "it": [
            "Il pacco con {item} non è arrivato dopo {days} giorni.",
            "Il tracking dell'ordine {order} è fermo da {days} giorni.",
            "Il corriere dice che ha consegnato ma io non ho ricevuto niente.",
            "Ordine {order}: la spedizione è in ritardo, mi sapete dire dov'è?",
            "Sono passati {days} giorni e il pacco con {item} non si vede.",
        ],
        "en": [
            "My parcel with {item} has not arrived after {days} days.",
            "The tracking for order {order} has been stuck for {days} days.",
            "The courier says it was delivered but I received nothing.",
            "Order {order}: the shipment is late, can you tell me where it is?",
            "It has been {days} days and my parcel with {item} is nowhere to be seen.",
        ],
    },
    "refund": {
        "it": [
            "Voglio un rimborso per l'ordine {order}.",
            "Ho restituito {item} {days} giorni fa e non ho ancora ricevuto il rimborso.",
            "Come posso annullare l'ordine {order} e riavere i miei soldi?",
            "Mi hanno addebitato due volte l'ordine {order}, chiedo il rimborso.",
            "Il rimborso per {item} è ancora in attesa da {days} giorni.",
        ],
        "en": [
            "I want a refund for order {order}.",
            "I returned {item} {days} days ago and I still haven't received my refund.",
            "How can I cancel order {order} and get my money back?",
            "I was charged twice for order {order}, I am asking for a refund.",
            "My refund for {item} has been pending for {days} days.",
        ],
    },
    "not_as_described": {
        "it": [
            "L'articolo ricevuto ({item}) è diverso dalle foto dell'annuncio.",
            "Nell'annuncio non c'erano macchie ma l'articolo ({item}) è rovinato.",
            "Ho comprato {item} in taglia M ma è arrivata una taglia diversa.",
            "Il venditore ha descritto l'articolo ({item}) come nuovo ma è usato e consumato.",
            "L'ordine {order} non corrisponde alla descrizione: il colore è completamente diverso.",
        ],
        "en": [
            "The item I received ({item}) is different from the photos in the listing.",
            "The listing showed no stains but the item ({item}) is damaged.",
            "I bought {item} in size M but a different size arrived.",
            "The seller described the item ({item}) as new but it is used and worn.",
            "Order {order} does not match the description: the colour is completely different.",
        ],
    },
    "account": {
        "it": [
            "Non riesco ad accedere al mio account, la password non funziona.",
            "Il mio account è stato bloccato senza spiegazioni.",
            "Vorrei cambiare l'email del mio profilo.",
            "Non mi arriva il codice di verifica per entrare.",
            "Ho dimenticato la password e il recupero non mi manda l'email.",
        ],
        "en": [
            "I can't log in to my account, my password doesn't work.",
            "My account was blocked without any explanation.",
            "I would like to change the email on my profile.",
            "I am not receiving the verification code to log in.",
            "I forgot my password and the recovery email never arrives.",
        ],
    },
    "payment": {
        "it": [
            "Ho venduto {item} ma il pagamento non è ancora arrivato sul mio saldo.",
            "Il trasferimento del mio saldo è fermo da {days} giorni.",
            "Il pagamento dell'ordine {order} è stato rifiutato.",
            "Non riesco ad aggiungere la carta per pagare.",
            "I soldi della vendita ({item}) non risultano accreditati dopo {days} giorni.",
        ],
        "en": [
            "I sold {item} but the payment has not reached my balance yet.",
            "The transfer of my balance has been stuck for {days} days.",
            "The payment for order {order} was declined.",
            "I can't add my card to pay.",
            "The money from my sale ({item}) has not been credited after {days} days.",
        ],
    },
}

# Help center FINTO: risposte inventate per la demo, non sono le regole di nessuna azienda reale.
FAQ = {
    "shipping": {
        "it": "Controlla il tracking nella pagina dell'ordine. Se è fermo da più di 7 giorni, contatta il corriere e apri una segnalazione sul pacco.",
        "en": "Check the tracking on the order page. If it has not moved for more than 7 days, contact the courier and open a parcel report.",
    },
    "refund": {
        "it": "I rimborsi vengono elaborati dopo la conferma di ricezione del reso. Verifica lo stato nella pagina dell'ordine; se sono passati più di 10 giorni, apri una richiesta.",
        "en": "Refunds are processed once the return is confirmed as received. Check the status on the order page; if more than 10 days have passed, open a request.",
    },
    "not_as_described": {
        "it": "Se l'articolo non corrisponde all'annuncio, invia foto del difetto entro 2 giorni dalla consegna e apri una richiesta di reso.",
        "en": "If the item does not match the listing, send photos of the defect within 2 days of delivery and open a return request.",
    },
    "account": {
        "it": "Prova il recupero password dalla schermata di accesso. Se l'account risulta bloccato, ti serve la verifica dell'identità: apri una richiesta indicando l'email del profilo.",
        "en": "Try the password recovery on the login screen. If the account is blocked, identity verification is needed: open a request with your profile email.",
    },
    "payment": {
        "it": "I pagamenti di vendita vengono accreditati dopo la conferma di consegna. Controlla il saldo e i metodi di pagamento; se non risulta nulla dopo 7 giorni, apri una richiesta.",
        "en": "Sale payments are credited after delivery is confirmed. Check your balance and payment methods; if nothing shows up after 7 days, open a request.",
    },
}


def typo(text: str) -> str:
    """Con probabilità 15% scambia due lettere vicine, per simulare un errore di battitura."""
    if len(text) < 8 or rng.random() > 0.15:
        return text
    i = rng.randrange(1, len(text) - 2)
    return text[:i] + text[i + 1] + text[i] + text[i + 2:]


def make_ticket(category: str, lang: str) -> str:
    template = rng.choice(TEMPLATES[category][lang])
    body = template.format(
        item=rng.choice(ITEMS[lang]),
        days=rng.randint(3, 20),
        order=f"#{rng.randint(10000, 99999)}",
    )
    parts = [rng.choice(OPENERS[lang]), body, rng.choice(CLOSERS[lang])]
    text = " ".join(p for p in parts if p)
    if rng.random() < 0.2:
        text = text.lower()
    return typo(text)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    rows = set()
    for category in TEMPLATES:
        for lang in ("it", "en"):
            for _ in range(PER_GROUP):
                rows.add((lang, category, make_ticket(category, lang)))
    rows = sorted(rows)
    rng.shuffle(rows)

    with open(OUT / "tickets.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "language", "category", "text"])
        for i, (lang, category, text) in enumerate(rows, start=1):
            writer.writerow([i, lang, category, text])

    with open(OUT / "faq.json", "w", encoding="utf-8") as f:
        json.dump(FAQ, f, ensure_ascii=False, indent=2)

    print(f"Creati {len(rows)} ticket in {OUT / 'tickets.csv'} e l'help center in {OUT / 'faq.json'}")


if __name__ == "__main__":
    main()
