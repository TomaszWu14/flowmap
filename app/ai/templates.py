"""Built-in process templates used by the no-AI mode (and the public example page).

A template is a small graph of steps. Questions walk it: the successors of the step a node was
created from become the suggested tiles.
"""

import re

S = dict  # step shorthand

TEMPLATES = {
    "booking": {
        "name": "Rezerwacja wizyty",
        "keywords": r"wizyt|salon|rezerw|umówi|termin|fryzjer|lekarz",
        "start_actor": "Klient",
        "steps": {
            "start": S(type="start", title="Klient chce umówić wizytę", actor="Klient"),
            "service": S(type="screen", title="Wybór usługi", actor="Klient",
                         outputs=["Lista usług", "Cena", "Czas trwania"], inputs=["Usługa"]),
            "slot": S(type="screen", title="Wybór terminu i specjalisty", actor="Klient",
                      outputs=["Kalendarz wolnych terminów", "Lista specjalistów"],
                      inputs=["Data", "Godzina", "Specjalista"]),
            "free": S(type="decision", title="Czy termin jest wolny?", actor="System", branches=["tak", "nie"]),
            "contact": S(type="user_action", title="Klient podaje dane kontaktowe", actor="Klient",
                         inputs=["Imię i nazwisko", "Telefon", "E-mail", "Zgoda RODO"]),
            "prepay": S(type="decision", title="Czy usługa wymaga przedpłaty?", actor="System",
                        branches=["tak", "nie"]),
            "payment": S(type="integration", title="Płatność online", actor="Klient",
                         description="Przekierowanie do bramki płatności.",
                         inputs=["Kwota", "Metoda płatności"], outputs=["Status płatności"]),
            "pay_retry": S(type="screen", title="Płatność nieudana — spróbuj ponownie", actor="Klient",
                           outputs=["Komunikat o błędzie", "Przycisk ponów"]),
            "confirm": S(type="automation", title="Wysłanie potwierdzenia rezerwacji", actor="System",
                         outputs=["SMS", "E-mail z terminem"]),
            "wait": S(type="wait", title="Oczekiwanie na termin wizyty", actor="System"),
            "remind": S(type="automation", title="Przypomnienie dzień przed wizytą", actor="System",
                        outputs=["SMS z przypomnieniem"]),
            "end": S(type="end", title="Wizyta odbyta", actor="Klient"),
        },
        "edges": [
            ("start", "service", ""), ("service", "slot", ""), ("slot", "free", ""),
            ("free", "contact", "tak"), ("free", "slot", "nie"), ("contact", "prepay", ""),
            ("prepay", "payment", "tak"), ("prepay", "confirm", "nie"),
            ("payment", "confirm", ""), ("payment", "pay_retry", "brak płatności"),
            ("pay_retry", "payment", ""), ("confirm", "wait", ""), ("wait", "remind", ""), ("remind", "end", ""),
        ],
    },
    "order": {
        "name": "Zamówienie w sklepie",
        "keywords": r"zamów|sklep|kup|koszyk|produkt|zakup",
        "start_actor": "Klient",
        "steps": {
            "start": S(type="start", title="Klient chce kupić produkt", actor="Klient"),
            "catalog": S(type="screen", title="Katalog produktów", actor="Klient",
                         outputs=["Lista produktów", "Filtry", "Cena"]),
            "cart": S(type="user_action", title="Dodanie produktu do koszyka", actor="Klient",
                      inputs=["Produkt", "Ilość"]),
            "checkout": S(type="screen", title="Podsumowanie koszyka i dostawa", actor="Klient",
                          outputs=["Produkty w koszyku", "Suma"], inputs=["Adres dostawy", "Metoda dostawy"]),
            "stock": S(type="decision", title="Czy produkty są dostępne?", actor="System", branches=["tak", "nie"]),
            "nostock": S(type="screen", title="Informacja o braku towaru", actor="Klient",
                         outputs=["Lista niedostępnych produktów"]),
            "payment": S(type="integration", title="Płatność za zamówienie", actor="Klient",
                         inputs=["Kwota", "Metoda płatności"], outputs=["Status płatności"]),
            "pay_fail": S(type="screen", title="Płatność odrzucona", actor="Klient",
                          outputs=["Komunikat", "Zmień metodę płatności"]),
            "confirm": S(type="automation", title="Potwierdzenie zamówienia e-mailem", actor="System",
                         outputs=["E-mail z numerem zamówienia"]),
            "pack": S(type="user_action", title="Kompletacja i wysyłka paczki", actor="Magazynier",
                      inputs=["Numer zamówienia"], outputs=["Numer przesyłki"]),
            "courier": S(type="integration", title="Zlecenie kuriera", actor="System",
                         inputs=["Adres dostawy"], outputs=["Numer śledzenia"]),
            "end": S(type="end", title="Zamówienie dostarczone", actor="Klient"),
        },
        "edges": [
            ("start", "catalog", ""), ("catalog", "cart", ""), ("cart", "checkout", ""), ("checkout", "stock", ""),
            ("stock", "payment", "tak"), ("stock", "nostock", "nie"), ("nostock", "catalog", ""),
            ("payment", "confirm", ""), ("payment", "pay_fail", "brak płatności"), ("pay_fail", "payment", ""),
            ("confirm", "pack", ""), ("pack", "courier", ""), ("courier", "end", ""),
        ],
    },
    "service": {
        "name": "Zgłoszenie serwisowe",
        "keywords": r"serwis|zgłosz|awari|napraw|usterk|reklamac|helpdesk",
        "start_actor": "Klient",
        "steps": {
            "start": S(type="start", title="Klient zgłasza usterkę", actor="Klient"),
            "form": S(type="screen", title="Formularz zgłoszenia", actor="Klient",
                      outputs=["Pola formularza"], inputs=["Opis problemu", "Zdjęcia", "Numer urządzenia", "Kontakt"]),
            "register": S(type="automation", title="Rejestracja zgłoszenia i nadanie numeru", actor="System",
                          outputs=["Numer zgłoszenia"]),
            "triage": S(type="user_action", title="Weryfikacja zgłoszenia", actor="Serwisant",
                        inputs=["Numer zgłoszenia"], outputs=["Kategoria", "Priorytet"]),
            "warranty": S(type="decision", title="Czy naprawa gwarancyjna?", actor="Serwisant",
                          branches=["tak", "nie"]),
            "quote": S(type="screen", title="Wycena naprawy do akceptacji", actor="Klient",
                       outputs=["Koszt", "Termin"], inputs=["Akceptacja"]),
            "accept": S(type="decision", title="Czy klient akceptuje wycenę?", actor="Klient",
                        branches=["tak", "nie"]),
            "repair": S(type="user_action", title="Naprawa urządzenia", actor="Serwisant",
                        outputs=["Raport z naprawy"]),
            "notify": S(type="automation", title="Powiadomienie klienta o zakończeniu", actor="System",
                        outputs=["SMS", "E-mail"]),
            "closed": S(type="end", title="Zgłoszenie zamknięte", actor="Serwisant"),
            "rejected": S(type="end", title="Zgłoszenie anulowane", actor="Klient"),
        },
        "edges": [
            ("start", "form", ""), ("form", "register", ""), ("register", "triage", ""), ("triage", "warranty", ""),
            ("warranty", "repair", "tak"), ("warranty", "quote", "nie"), ("quote", "accept", ""),
            ("accept", "repair", "tak"), ("accept", "rejected", "nie"), ("repair", "notify", ""),
            ("notify", "closed", ""),
        ],
    },
}

TEMPLATE_CHOICES = [("auto", "Dobierz automatycznie"), ("none", "Bez szablonu")] + [
    (k, t["name"]) for k, t in TEMPLATES.items()
]


def match_template(sentence: str) -> str | None:
    text = sentence.lower()
    for key, tpl in TEMPLATES.items():
        if re.search(tpl["keywords"], text):
            return key
    return None


def successors(template_key: str | None, step_key: str | None, label: str | None) -> list[tuple[str, str]]:
    """(target_step, edge_label) pairs leaving a template step on the given branch label."""
    tpl = TEMPLATES.get(template_key or "")
    if not tpl or not step_key:
        return []
    out = [(dst, lab) for src, dst, lab in tpl["edges"] if src == step_key]
    if tpl["steps"][step_key]["type"] == "decision":
        return [(dst, lab) for dst, lab in out if lab == (label or "")]
    return out


def step(template_key: str, step_key: str) -> dict:
    return TEMPLATES[template_key]["steps"][step_key]


def full_graph(template_key: str, start_sentence: str | None = None) -> dict:
    """The complete template as a graph dict (example page, tests)."""
    tpl = TEMPLATES[template_key]
    nodes = []
    for key, s in tpl["steps"].items():
        title = start_sentence if key == "start" and start_sentence else s["title"]
        data = {"tpl": key}
        if s.get("branches"):
            data["branches"] = list(s["branches"])
        nodes.append({
            "key": key, "type": s["type"], "title": title, "description": s.get("description", ""),
            "actor": s.get("actor", ""), "inputs": list(s.get("inputs", [])), "outputs": list(s.get("outputs", [])),
            "data": data, "x": None, "y": None,
        })
    edges = [
        {"source": a, "target": b, "label": lab, "condition": "error" if lab == "brak płatności" else ""}
        for a, b, lab in tpl["edges"]
    ]
    return {"nodes": nodes, "edges": edges}
