"""Pictograms: what a step looks like on the map (envelope for e-mail, keyboard for manual data entry, …).

Picked automatically from the step text (Polish word stems, no AI); the user can override it per step
(`node.data["icon"]`). Each pictogram also says which BPMN task type the step exports as.
Icons: Lucide (ISC licence, app/static/icons/LICENSE-lucide.txt), bundled in app/static/icons.json.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

# key -> (Polish name, BPMN element). Order = order in the picker.
PICTOGRAMS = {
    "mail": ("Wysłanie e-maila", "sendTask"),
    "mail-open": ("Odebranie wiadomości", "receiveTask"),
    "message-square": ("SMS / komunikator", "sendTask"),
    "phone": ("Telefon", "manualTask"),
    "keyboard": ("Wprowadzanie danych", "userTask"),
    "scan-barcode": ("Skanowanie kodu", "userTask"),
    "printer": ("Drukowanie", "manualTask"),
    "signature": ("Zatwierdzenie / podpis", "userTask"),
    "clipboard-check": ("Sprawdzenie / kontrola", "userTask"),
    "search": ("Wyszukiwanie", "userTask"),
    "calendar": ("Rezerwacja / termin", "userTask"),
    "file-text": ("Dokument", "userTask"),
    "credit-card": ("Płatność", "serviceTask"),
    "receipt": ("Faktura", "serviceTask"),
    "server": ("System (SAP, ERP)", "serviceTask"),
    "package": ("Magazyn / pakowanie", "manualTask"),
    "truck": ("Transport / wysyłka", "manualTask"),
    "hand": ("Praca ręczna", "manualTask"),
    "timer": ("Oczekiwanie / termin", "timer"),
    "monitor": ("Ekran", "userTask"),
    "user": ("Zadanie osoby", "userTask"),
    "cog": ("Automatyzacja", "serviceTask"),
    "arrow-left-right": ("Integracja", "serviceTask"),
    "play": ("Start", "startEvent"),
    "square": ("Koniec", "endEvent"),
}

# First match wins: specific activities before generic ones.
RULES = [
    ("mail-open", r"(otrzym|odbier|przychodz|wpływ|czeka na).{0,25}(e-?mail|maila|wiadomo|odpowied)|skrzynk"),
    ("message-square", r"\bsms|wiadomoś[ćc] tekst|czat|chat|komunikator|\bteams\b|slack|push"),
    ("mail", r"e-?mail|\bmail|mailow|newsletter|powiadom"),
    ("phone", r"telefon|dzwon|zadzwo|infolini|call ?cent"),
    ("scan-barcode", r"skan|kod kreskow|barcode|czytnik|\bqr\b"),
    ("printer", r"druk|wydruk"),
    ("keyboard", r"wpisuj|wpisan|wprowad|ręczn|przepisuj|uzupełni|wypełni|rejestruje w system"),
    ("signature", r"zatwierd|akceptuj|akceptacj|podpis|autoryz|zgod[ay]|decyzj[aię] kierown"),
    ("clipboard-check", r"sprawd|weryfik|kontrol|inspekc|audyt|walidac"),
    ("search", r"wyszuk|szuka|przegląda"),
    ("credit-card", r"płat|przelew|zapłat|opłat|\bkart[aąy]|blik"),
    ("receipt", r"faktur|rachun|paragon|nota księg"),
    ("calendar", r"rezerw|kalendarz|wizyt|umówi|grafik|wyb\w* termin|wolny termin|termin (wizyty|spotkania)"),
    ("truck", r"wysyłk|kurier|transport|dostaw|ciężarów|załadun|rozładun|spedyc"),
    ("package", r"kompletuj|kompletac|pakuj|pakowan|magazyn|towar|paczk|palet|przyjęci[ea] towar"),
    ("timer", r"czeka|oczekiw|po \d+ ?(dni|dniach|godz|h)|przypomn|timeout|upływ|termin"),
    ("server", r"\bsap\b|\berp\b|\bwms\b|\bcrm\b|baza danych|bazie danych|system automatycz|zapis.{0,10}w systemie"),
    ("file-text", r"dokument|raport|umow|wniosek|\bpdf\b|plik|protokół"),
]
_COMPILED = [(key, re.compile(rx, re.I)) for key, rx in RULES]

BY_TYPE = {"start": "play", "end": "square", "screen": "monitor", "user_action": "user", "automation": "cog",
           "integration": "arrow-left-right", "wait": "timer"}
NO_ICON_TYPES = ("decision", "parallel")  # gateways speak through their shape


def detect(title: str, node_type: str, description: str = "") -> str | None:
    """Pictogram key for a step. Gateways get none; start/end always keep their event icon."""
    if node_type in NO_ICON_TYPES:
        return None
    if node_type in ("start", "end"):
        return BY_TYPE[node_type]
    text = f"{title} {description}"
    for key, rx in _COMPILED:
        if rx.search(text):
            return key
    return BY_TYPE.get(node_type, "user")


def icon_for(node: dict) -> str | None:
    """Manual choice (node.data.icon) wins over detection."""
    chosen = (node.get("data") or {}).get("icon")
    if chosen in PICTOGRAMS:
        return chosen
    return detect(node.get("title", ""), node["type"], node.get("description", ""))


def bpmn_element(node: dict) -> str:
    key = icon_for(node)
    return PICTOGRAMS[key][1] if key else ""


def pictogram_svg(key: str | None, size: int = 18):
    """Inline <svg> for templates. Bodies come from the bundled icon file, never from user input."""
    from markupsafe import Markup

    body = svg_bodies().get(key or "")
    if not body:
        return Markup("")
    return Markup(f'<svg class="picto" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
                  f'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
                  f'aria-hidden="true">{body}</svg>')


@lru_cache(maxsize=1)
def svg_bodies() -> dict[str, str]:
    """Inner SVG markup per icon, for server-rendered pickers (static, trusted content)."""
    path = Path(__file__).resolve().parent.parent / "static" / "icons.json"
    return json.loads(path.read_text(encoding="utf-8"))
