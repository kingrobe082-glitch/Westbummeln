"""Alarm- und Ausrückeordnung (AAO) der FF Westbummeln: Daten und Auflösung in Fahrzeuge.

Quelle: „Alarm- und Ausrückeordnung (AAO)“, Entwurf Stand 10.11.2026 (Stichworte in Anlehnung an NRW).
Keine Django-Abhängigkeit; die Spiellogik (game.engine) ruft `vorschlag()` auf.

Alarmierung je Stichwort als Regeltext, nah am PDF:

    'zuständig: 1 HLF/LF (LZ2: MLF); LZ1: 1 DLK 23/12 [Rettungshöhe über 8 m]; FTZ: 1 ELW 1'

- Abschnitte mit „;“, je Abschnitt „Einheit: Fahrzeug, Fahrzeug“.
- Einheit: `zuständig` (LZ des Einsatzbereichs), `LZ1` … `LZ6`, `FTZ`, `LZ1 oder LZ3`, `alle LZ`.
- Fahrzeug: Anzahl und Typ (`1 DLK 23/12`) oder Typgruppe (`1 HLF/LF/TLF`, `1 TSF-W/MLF`); `alle` = die ganze Einheit.
- `(LZ2: MLF)` = Sonderfall, wenn diese Einheit zuständig ist. `[Bedingung]` = nur bei Bedarf (optional).
- `basis` = „Wie B 2 Y, zusätzlich …“: die Regeln der Basis gelten mit (Anzahlen addieren sich).
"""
import re
from functools import lru_cache

# ------------------------------------------------------------------ Einheiten (Abschnitt 1 und 2)

LOESCHZUEGE = ('LZ1', 'LZ2', 'LZ3', 'LZ4', 'LZ5', 'LZ6')
EINHEITEN = {
    'LZ1': 'LZ 1 Mitte', 'LZ2': 'LZ 2 Altstadt', 'LZ3': 'LZ 3 Süd', 'LZ4': 'LZ 4 Nord', 'LZ5': 'LZ 5 West',
    'LZ6': 'LZ 6 Ost', 'FTZ': 'FTZ Westbummeln',
}
FACHGEBIETE = {
    'LZ1': 'Brandschutz', 'LZ2': 'Wasserversorgung', 'LZ3': 'Verpflegung', 'LZ4': 'Technische Hilfeleistung',
    'LZ5': 'Vegetation', 'LZ6': 'Lagedienst',
}
# Fahrzeuge laut AAO, Abschnitt 2. Die Spielflotte (game/flotte.py) ist die Quelle für das Spiel; diese
# Liste dient zum Prüfen der Regeln und als Testflotte.
AAO_FLOTTE = {
    'LZ1': '2 HLF 20, 1 TLF 3000, 1 LF 20, 2 DLK 23/12, 2 MTW, 1 Anh Tierrettung',
    'LZ2': '2 MLF, 2 TSF-W, 2 WLF, 1 Tankwagen, 2 SW 2000, 4 MTW, 1 AB-Schlauch, 1 AB-Wasser',
    'LZ3': '1 HLF 20, 1 DLK 23/12, 1 ELW 1, 1 GW-L1, 2 MZF, 1 Anh Küche, 1 Anh Kühlung',
    'LZ4': '2 HLF 10, 2 RW, 1 GW-Öl, 1 WLF, 1 AB Schiene, 1 GW HRett, 1 GW-G',
    'LZ5': '2 TLF 3000, 1 TLF 4000, 1 GTLF, 2 ATV, 1 KdoW Wald, 1 WLF, 1 LF 20 Wald, 1 AB Wald, 1 AB Schlauch, '
           '1 Anh Radlader, 1 Anh ATV Trans',
    'LZ6': '1 HLF 20, 1 RW, 2 MTW, 2 MZF Drohne, 1 ELW 1, 1 KdoW Lage',
    'FTZ': '1 KdoW KBM, 2 ELW 1, 1 ELW 2, 1 GW-Nachschub, 1 GW-MANV, 2 WLF, 1 AB Dekon P, 1 AB Dekon G, '
           '1 AB Telelader',
}

# Typgruppen in Regeln („HLF/LF“). Reihenfolge = Vorrang bei der Auswahl.
TYPGRUPPEN = {
    'HLF': ('HLF 20', 'HLF 10'),
    'LF': ('LF 20', 'LF 10', 'LF 20 Wald'),
    'TLF': ('TLF 3000', 'TLF 4000', 'GTLF'),
}
# Gleichwertige Fahrzeuge für den Ersatz, wenn das verlangte Fahrzeug fehlt oder nicht frei ist.
GLEICHWERTIG = (
    ('HLF 20', 'HLF 10', 'LF 20', 'LF 10', 'LF 20 Wald', 'MLF', 'TSF-W'),
    ('TLF 3000', 'TLF 4000', 'GTLF'),
    ('MTW', 'MZF'),
    ('KdoW', 'KdoW KBM', 'KdoW Lage', 'KdoW Wald'),
)
WLF = 'WLF'

# ------------------------------------------------------------------ Stichworte (Abschnitte 3–7)

RD_POL = ('Rettungsdienst', 'Polizei')
PRESSE = 'Kreispressesprecher'

STICHWORTE = {
    # Brand
    'B 1': dict(gruppe='Brand', name='Kleinbrand', beschreibung='Mülleimer, Kleinfeuer, Fahrzeugbrand klein',
                alarm='zuständig: 1 HLF/LF (LZ2: MLF)'),
    'B 2': dict(gruppe='Brand', name='Mittelbrand',
                beschreibung='Zimmer-/Wohnungsbrand, Dachstuhlbrand klein, Pkw-/Lkw-Brand',
                alarm='zuständig: 1 HLF/LF/TLF, 1 MTW; LZ1: 1 HLF 20, 1 DLK 23/12; LZ2: 1 TSF-W/MLF; FTZ: 1 ELW 1'),
    'B 2 Y': dict(gruppe='Brand', name='Brand, Menschenleben in Gefahr', basis='B 2', meldungen=RD_POL,
                  alarm='LZ1: 1 HLF 20, 1 DLK 23/12; LZ4: 1 HLF 10, 1 GW HRett; LZ3: 1 DLK 23/12; LZ2: 1 MTW'),
    'B 3': dict(gruppe='Brand', name='Großbrand', beschreibung='Gewerbe-/Industriebrand, Brand mehrerer Gebäude',
                basis='B 2 Y', meldungen=(PRESSE,),
                alarm='LZ1: 1 TLF 3000, 1 LF 20, 1 DLK 23/12; '
                      'LZ2: 2 SW 2000, 1 AB-Schlauch, 1 AB-Wasser, 1 Tankwagen, 1 WLF; '
                      'LZ3: 1 HLF 20, 1 ELW 1, 1 Anh Küche; LZ5: 1 TLF 4000, 1 AB Schlauch, 1 WLF; '
                      'LZ6: 1 HLF 20, 1 ELW 1, 1 KdoW Lage; '
                      'FTZ: 1 ELW 2, 1 KdoW KBM, 1 GW-Nachschub, 1 AB Telelader'),
    'B 4': dict(gruppe='Brand', name='Sonderlage', beschreibung='Großschadenslage / Flächenlage', basis='B 3',
                hinweis='Alle LZ nach Anordnung der Einsatzleitung, FTZ als Führungsstelle',
                meldungen=('Kreisbrandmeister: Nachforderung überörtlicher Kräfte',),
                alarm='alle LZ: 1 HLF/LF/TLF (LZ2: MLF)'),
    'BMA': dict(gruppe='Brand', name='Brandmeldeanlage', beschreibung='Brandmeldeanlage ausgelöst',
                alarm='zuständig: 1 HLF/LF; LZ1: 1 DLK 23/12 [Rettungshöhe über 8 m]; FTZ: 1 ELW 1 [nach Objekt]'),
    'B Container': dict(gruppe='Brand', name='Container / Großfahrzeug', beschreibung='Brand Lkw, Bus, Container',
                        alarm='LZ1: 1 HLF 20, 1 TLF 3000; LZ2: 1 TSF-W/MLF, 1 Tankwagen; LZ4: 1 HLF 10'),
    'B Schiene': dict(gruppe='Brand', name='Schiene', beschreibung='Brand an Bahnanlage / Schienenfahrzeug',
                      orte=('schiene',),
                      alarm='LZ4: 1 HLF 10, 1 AB Schiene, 1 GW HRett; LZ2: 1 Tankwagen, 1 SW 2000; FTZ: 1 ELW 1'),
    # Vegetation
    'VEG 1': dict(gruppe='Vegetation', name='Kleiner Vegetationsbrand',
                  beschreibung='Kleiner Flächen-, Wiesen-, Böschungsbrand', orte=('feld', 'wald'),
                  alarm='LZ5: 1 LF 20 Wald; zuständig: 1 HLF/LF'),
    'VEG 2': dict(gruppe='Vegetation', name='Flächen-/Waldbrand', beschreibung='Größerer Flächen- oder Waldbrand',
                  orte=('feld', 'wald'),
                  alarm='LZ5: 1 TLF 3000, 1 TLF 4000, 1 LF 20 Wald, 1 KdoW Wald, 1 ATV, 1 Anh ATV Trans; '
                        'LZ2: 1 Tankwagen, 1 SW 2000; FTZ: 1 ELW 1'),
    'VEG 3': dict(gruppe='Vegetation', name='Großer Waldbrand', beschreibung='Großer Waldbrand, unwegsames Gelände',
                  orte=('feld', 'wald'), basis='VEG 2', meldungen=(PRESSE,),
                  alarm='LZ5: alle; LZ2: 2 SW 2000, 1 AB-Schlauch, 1 AB-Wasser; LZ3: 1 ELW 1, 1 Anh Küche; '
                        'LZ6: 2 MZF Drohne, 1 KdoW Lage; FTZ: 1 ELW 2, 1 KdoW KBM, 1 GW-Nachschub'),
    # Technische Hilfeleistung
    'TH 1': dict(gruppe='Technische Hilfe', name='Kleine Hilfeleistung', beschreibung='Tür öffnen, Ölspur, Baum',
                 alarm='zuständig: 1 HLF/LF/MLF'),
    'TH 2': dict(gruppe='Technische Hilfe', name='Mittlere Hilfeleistung',
                 beschreibung='Verkehrsunfall mit Einklemmung, Gebäudeschaden',
                 alarm='LZ4: 1 HLF 10, 1 RW; zuständig: 1 HLF/LF; FTZ: 1 ELW 1'),
    'TH Y': dict(gruppe='Technische Hilfe', name='Hilfeleistung, Menschenleben in Gefahr',
                 beschreibung='VU mit mehreren eingeklemmten Personen', basis='TH 2', meldungen=RD_POL,
                 alarm='LZ4: 1 HLF 10, 1 RW, 1 GW HRett; LZ1 oder LZ3: 1 HLF 20; LZ6: 1 RW, 1 ELW 1; FTZ: 1 ELW 1'),
    'TH 3': dict(gruppe='Technische Hilfe', name='Große Hilfeleistung',
                 beschreibung='Gebäudeeinsturz, schwerer Unfall mit vielen Fahrzeugen', basis='TH Y',
                 meldungen=(PRESSE,),
                 alarm='LZ4: 1 WLF, 1 GW HRett; LZ1: 1 DLK 23/12, 1 HLF 20; LZ3: 1 HLF 20, 1 GW-L1; '
                       'LZ6: 1 HLF 20, 1 KdoW Lage; FTZ: 1 ELW 2, 1 GW-MANV, 1 KdoW KBM, 1 GW-Nachschub'),
    'TH Öl': dict(gruppe='Technische Hilfe', name='Ölschaden',
                  beschreibung='Ölschaden, Betriebsstoffe, Gewässerverunreinigung',
                  alarm='LZ4: 1 GW-Öl, 1 HLF 10; zuständig: 1 HLF/LF'),
    'TH Wasser': dict(gruppe='Technische Hilfe', name='Wasserschaden',
                      beschreibung='Wasserschaden, Rohrbruch, Unwetter, Überflutung',
                      alarm='zuständig: 1 HLF/LF/MLF; LZ2: 1 SW 2000, 1 MTW; '
                            'LZ2: 1 AB-Schlauch [größere Lage], 1 WLF [größere Lage]'),
    'TH Sturm': dict(gruppe='Technische Hilfe', name='Sturm / Unwetter',
                beschreibung='Unwetterlage, viele Einsatzstellen',
                     hinweis='Alle LZ jeweils im eigenen Bereich', meldungen=(PRESSE,),
                     alarm='alle LZ: 1 HLF/LF/MLF; FTZ: 1 ELW 2, 1 KdoW KBM; LZ6: 1 KdoW Lage, 2 MZF Drohne'),
    'TH Tier': dict(gruppe='Technische Hilfe', name='Tierrettung', beschreibung='Tierrettung',
                    alarm='LZ1: 1 HLF 20, 1 Anh Tierrettung; LZ4: 1 RW [Großtier]'),
    'TH Bahn': dict(gruppe='Technische Hilfe', name='Unfall an der Schiene', beschreibung='Unfall an der Schiene',
                    orte=('schiene',), meldungen=(*RD_POL, 'Bahnbetreiber'),
                    alarm='LZ4: 1 HLF 10, 1 RW, 1 AB Schiene, 1 GW HRett; FTZ: 1 ELW 1, 1 ELW 2'),
    'TH Drohne': dict(gruppe='Technische Hilfe', name='Drohne',
                beschreibung='Lageerkundung / Personensuche aus der Luft',
                      alarm='LZ6: 1 MZF Drohne, 1 KdoW Lage'),
    # Gefahrstoffe
    'ABC 1': dict(gruppe='Gefahrstoffe', name='Kleiner Gefahrstoffeinsatz',
                  beschreibung='Kleiner Gefahrgutaustritt, unklare Geruchslage',
                  alarm='LZ4: 1 GW-G, 1 HLF 10; zuständig: 1 HLF/LF; FTZ: 1 ELW 1'),
    'ABC 2': dict(gruppe='Gefahrstoffe', name='Mittlerer Gefahrgutunfall', beschreibung='Gefahrgut, Personenschaden',
                  basis='ABC 1', meldungen=('Rettungsdienst',),
                  alarm='LZ4: 1 GW-Öl, 1 RW; LZ2: 1 Tankwagen, 1 AB-Wasser; LZ6: 1 ELW 1; '
                        'FTZ: 1 ELW 2, 1 AB Dekon P, 1 GW-Nachschub'),
    'ABC 3': dict(gruppe='Gefahrstoffe', name='Großes Gefahrgut-/CBRN-Ereignis', beschreibung='Großes CBRN-Ereignis',
                  basis='ABC 2', meldungen=(PRESSE, 'Weitere Kräfte aus dem Kreis'),
                  alarm='FTZ: 1 AB Dekon G, 1 GW-MANV, 1 WLF, 1 KdoW KBM; LZ3: 1 ELW 1, 1 Anh Küche, 1 Anh Kühlung'),
    # MANV und sonstige Lagen
    'MANV 1': dict(gruppe='MANV / Sonstiges', name='MANV bis 10 Betroffene', beschreibung='Massenanfall von Verletzten',
                   meldungen=('Rettungsdienst',),
                   alarm='zuständig: 1 HLF; FTZ: 1 GW-MANV, 1 ELW 1; LZ6: 1 ELW 1'),
    'MANV 2': dict(gruppe='MANV / Sonstiges', name='MANV über 10 Betroffene',
                beschreibung='Massenanfall von Verletzten',
                   basis='MANV 1', meldungen=(PRESSE,),
                   alarm='FTZ: 1 ELW 2, 1 WLF, 1 KdoW KBM; LZ3: 1 ELW 1, 1 MZF; LZ1: 1 HLF; LZ4: 1 HLF; LZ2: 2 MTW'),
    'Verpflegung': dict(gruppe='MANV / Sonstiges', name='Verpflegung',
                beschreibung='Einsatzverpflegung bei langen Einsätzen',
                        alarm='LZ3: 1 Anh Küche, 1 Anh Kühlung, 1 GW-L1, 1 MZF'),
    'Nachschub': dict(gruppe='MANV / Sonstiges', name='Nachschub / Logistik',
                      beschreibung='Material-, Wechsellader- und Atemschutznachschub',
                      alarm='FTZ: 1 GW-Nachschub, 1 WLF, 1 AB Telelader; LZ2: 1 WLF [bei Bedarf]'),
    'Führung': dict(gruppe='MANV / Sonstiges', name='Führung / Lage', beschreibung='Führungsstelle, Lagedarstellung',
                    alarm='FTZ: 1 ELW 2, 1 KdoW KBM; LZ6: 1 KdoW Lage, 1 ELW 1, 1 MZF Drohne'),
}

# Stufen je Familie; „ab B 2“ heißt: B 2 und alle höheren Stufen derselben Familie.
FAMILIEN = (
    ('B 1', 'B 2', 'B 2 Y', 'B 3', 'B 4'),
    ('TH 1', 'TH 2', 'TH Y', 'TH 3'),
    ('VEG 1', 'VEG 2', 'VEG 3'),
    ('ABC 1', 'ABC 2', 'ABC 3'),
    ('MANV 1', 'MANV 2'),
)

# Besondere Regelungen (Abschnitt 8): (Name, ab Stichworten, Einheit, Typen, Anzahl). Sie gelten mindestens –
# stehen die Fahrzeuge schon in der Alarmierung, ändert sich nichts.
BESONDERE = (
    ('Wasserversorgung', ('B 2',), 'LZ2', 'TSF-W/MLF/SW 2000/Tankwagen', 1),
    ('Führungsdienst', ('B 2 Y', 'TH Y', 'VEG 2', 'ABC 2'), 'FTZ', 'ELW 1', 1),
    ('Führungsdienst', ('B 3', 'TH 3'), 'FTZ', 'ELW 2', 1),
    ('Kreisbrandmeister', ('B 3', 'VEG 3', 'TH 3', 'ABC 3', 'MANV 2'), 'FTZ', 'KdoW KBM', 1),
)
PRESSE_AB = ('B 3', 'VEG 3', 'TH 3', 'ABC 3', 'MANV 2')

# Alte Stichworte (vor der AAO) → neue. Gespeicherte Räume und der Maßnahmen-Katalog nutzen das.
ALT = {
    'F1': 'B 1', 'F2': 'B 2', 'F2Y': 'B 2 Y', 'F3': 'B 3', 'F4': 'B 4', 'TH': 'TH 1', 'THY': 'TH Y',
    'VU': 'TH 2', 'BMA': 'BMA', 'GAS': 'ABC 1', 'THWASSERSCHADEN': 'TH Wasser', 'THOEL': 'TH Öl',
}

# ------------------------------------------------------------------ Einsatzbereiche

# Zuständiger LZ und Nachbar-LZ je Einsatzort: die zwei Löschzüge mit der kürzesten Fahrzeit über das
# Straßennetz (Fahrzeit nach Straßenart aus PR #42, Wachen-Standorte aus game/flotte.py: LZ 1 Mitte am Gebäude
# „Freiwillige Feuerwehr“, LZ 5 West an der gedruckten „LZ1“-Wache usw.). Neu berechnen mit
# `python tools/einsatzbereiche.py`. LZ 5 (Vegetation, ganz im Westen) ist für keinen Ort der Liste am schnellsten.
EINSATZBEREICHE = {
    'Hauptstraße': ('LZ1', 'LZ2'), 'Marktplatz': ('LZ1', 'LZ2'), 'Schulstraße': ('LZ6', 'LZ4'),
    'Waldstraße': ('LZ1', 'LZ2'), 'Dorfstraße': ('LZ3', 'LZ6'), 'Nelkenweg': ('LZ6', 'LZ2'),
    'Mathias-Berg-Straße': ('LZ6', 'LZ2'), 'Robin-Hof-Straße': ('LZ3', 'LZ6'), 'Werkstraße': ('LZ3', 'LZ6'),
    'Buchenstraße': ('LZ6', 'LZ3'), 'Eichenstraße': ('LZ4', 'LZ1'), 'Bachstraße': ('LZ3', 'LZ6'),
    'Flurstraße': ('LZ4', 'LZ6'), 'Tannenweg': ('LZ4', 'LZ6'), 'Ahornallee': ('LZ6', 'LZ4'),
    'Kreuzbergstraße': ('LZ4', 'LZ6'), 'Jägerstraße': ('LZ1', 'LZ2'), 'Scheunenweg': ('LZ4', 'LZ1'),
    'Blütenstraße': ('LZ4', 'LZ1'), 'Sportplatzring': ('LZ1', 'LZ4'), 'Kirchstraße': ('LZ2', 'LZ1'),
    'Rosenstraße': ('LZ2', 'LZ1'), 'Sonnenstraße': ('LZ2', 'LZ1'), 'Mozartweg': ('LZ6', 'LZ3'),
    'Uferstraße': ('LZ3', 'LZ1'), 'Mühlenweg': ('LZ3', 'LZ6'), 'Gartenweg': ('LZ3', 'LZ6'),
    'Wiesenstraße': ('LZ3', 'LZ6'), 'Bummelbachweg': ('LZ3', 'LZ6'), 'Dorflick': ('LZ3', 'LZ6'),
    'Bürgerstraße': ('LZ3', 'LZ6'), 'Forstweg': ('LZ4', 'LZ1'), 'Feldweg': ('LZ4', 'LZ6'),
    'Am Rathauspark': ('LZ1', 'LZ2'), 'Erlenstraße': ('LZ6', 'LZ3'),
}

# Merkmale der Einsatzorte für die KI (VEG nur an Feld/Wald). Eine Bahnstrecke gibt es auf der Karte nicht,
# deshalb erzeugt die KI keine Schienen-Stichworte.
ORTE = {
    'Waldstraße': ('wald',), 'Forstweg': ('wald',), 'Jägerstraße': ('wald',), 'Eichenstraße': ('wald',),
    'Kreuzbergstraße': ('wald', 'feld'), 'Feldweg': ('feld',), 'Flurstraße': ('feld',), 'Scheunenweg': ('feld',),
    'Wiesenstraße': ('feld', 'gewaesser'), 'Gartenweg': ('feld', 'gewaesser'), 'Bummelbachweg': ('feld', 'gewaesser'),
    'Dorflick': ('feld',), 'Mühlenweg': ('gewaesser',), 'Uferstraße': ('gewaesser',), 'Bachstraße': ('gewaesser',),
    'Werkstraße': ('gewerbe',),
}


# ------------------------------------------------------------------ Hilfsfunktionen

def _norm(typ):
    """Typname zum Vergleichen: Groß/klein, Leerzeichen, Bindestriche, Punkte egal („AB-Schlauch“ = „AB Schlauch“)."""
    return re.sub(r'[\s\-_.]', '', str(typ)).lower()


_GLEICH = {_norm(t): group for group in GLEICHWERTIG for t in group}


def einheit_von(v):
    """'LZ1', 'FTZ', 'GH3' … aus einem Fahrzeug (game/flotte.py: `einheit`; alte Flotte: `unit` = Zahl)."""
    e = v.get('einheit', v.get('unit'))
    if isinstance(e, int):
        return f'LZ{e}'
    return re.sub(r'\s', '', str(e or '')).upper()


def typ_von(v):
    return v.get('typ') or v.get('kind') or ''


def kurz(e):
    """'LZ1' → 'LZ 1', sonst unverändert."""
    return f'LZ {e[2:]}' if re.fullmatch(r'LZ\d', e or '') else e


def _typen(text):
    """'HLF/LF/TLF' → ['HLF 20', 'HLF 10', 'LF 20', …]; 'DLK 23/12' bleibt ein Typ."""
    text = text.strip()
    if text in TYPGRUPPEN:
        return list(TYPGRUPPEN[text])
    if '/' not in text or re.fullmatch(r'DLK \d+/\d+', text):
        return [text]
    return [t for part in text.split('/') for t in _typen(part)]


_ITEM = re.compile(r'^(?P<n>\d+|alle)\s*(?P<typ>[^(\[]*?)\s*(?:\((?P<sonder>[^)]*)\))?\s*(?:\[(?P<bed>[^\]]*)\])?$')


def parse_alarm(text, quelle=''):
    """Regeltext → Liste von Regeln (dict: einheiten, typen, typ_text, anzahl, optional, bedingung, sonder, quelle)."""
    regeln = []
    for abschnitt in filter(None, (a.strip() for a in text.split(';'))):
        einheit, _, items = abschnitt.partition(':')
        einheit = einheit.strip()
        for item in filter(None, (i.strip() for i in items.split(','))):
            m = _ITEM.match(item)
            if not m:
                raise ValueError(f'AAO-Regel nicht lesbar: {item!r} ({quelle})')
            sonder = {}
            if m['sonder']:
                unit, _, typ = m['sonder'].partition(':')
                sonder[unit.strip()] = _typen(typ)
            alle = m['n'] == 'alle'
            regeln.append({
                'einheit': einheit, 'typ_text': 'alle Fahrzeuge' if alle else m['typ'].strip(),
                'typen': [] if alle else _typen(m['typ']), 'anzahl': 0 if alle else int(m['n']), 'alle': alle,
                'optional': bool(m['bed']), 'bedingung': (m['bed'] or '').strip(), 'sonder': sonder,
                'quelle': quelle,
            })
    return regeln


def flotte_liste(flotte=None):
    """AAO_FLOTTE als Fahrzeugliste [{'id', 'typ', 'einheit'}] (Testflotte)."""
    fahrzeuge = []
    for einheit, text in (flotte or AAO_FLOTTE).items():
        for item in text.split(','):
            n, typ = item.strip().split(' ', 1)
            for i in range(int(n)):
                fahrzeuge.append({'id': f'{einheit}-{_norm(typ)}-{i + 1}', 'typ': typ, 'einheit': einheit,
                                  'call': f'{kurz(einheit)} {typ}' + (f' {i + 1}' if int(n) > 1 else '')})
    return fahrzeuge


# ------------------------------------------------------------------ Stichworte nachschlagen

def _compact(text):
    return re.sub(r'\s', '', str(text or '')).upper().replace('Ö', 'OE')


_KEYS = {_compact(k): k for k in STICHWORTE}


def normalisiere(text):
    """'B2Y', 'b 2 y', 'F2', 'TH1' → 'B 2 Y', 'B 2', 'TH 1'. None, wenn unbekannt."""
    compact = _compact(text)
    return _KEYS.get(compact) or ALT.get(compact)


def stichwort_aus_titel(title):
    """'B 2 · Wohnungsbrand' → 'B 2'; altes 'F1 · Kleinbrand' → 'B 1'; 'TH · Wasserschaden' → 'TH Wasser'."""
    title = str(title or '')
    head, sep, rest = title.partition('·')
    key = normalisiere(head)
    if key == 'TH 1' and re.sub(r'\s', '', head).upper() == 'TH' and 'wasser' in rest.lower():
        return 'TH Wasser'
    if key:
        return key
    # Ohne „·“: längstes bekanntes Stichwort am Anfang („B 2 Y Wohnungsbrand“).
    for k in sorted(STICHWORTE, key=len, reverse=True):
        if re.match(re.escape(k) + r'(\b|$)', title.strip(), re.IGNORECASE):
            return k
    first = title.split()[0] if title.split() else ''
    return normalisiere(first)


def titel(stichwort, meldebild=''):
    meldebild = str(meldebild or '').strip() or STICHWORTE[stichwort]['name']
    return f'{stichwort} · {meldebild}'


def migriere_titel(title):
    """Alter Titel → neuer Titel mit AAO-Stichwort ('F1 · Kleinbrand' → 'B 1 · Kleinbrand'). Unbekanntes bleibt."""
    key = stichwort_aus_titel(title)
    if not key:
        return title
    head, sep, rest = str(title).partition('·')
    if sep:
        return f'{key} · {rest.strip()}' if head.strip() != key else title
    if normalisiere(title):
        return titel(key)
    return title


def stufe(stichwort):
    """Zahl der Stufe im Stichwort (B 2 Y = 2, TH Öl = 1)."""
    m = re.search(r'(\d)', stichwort or '')
    return max(1, int(m.group(1))) if m else 1


def ab(stichwort, schwellen):
    """True, wenn stichwort eine der Schwellen oder eine höhere Stufe derselben Familie ist."""
    for familie in FAMILIEN:
        if stichwort in familie:
            rang = familie.index(stichwort)
            if any(s in familie and familie.index(s) <= rang for s in schwellen):
                return True
    return False


def kette(stichwort):
    """Basis-Kette, z. B. B 3 → ['B 2', 'B 2 Y', 'B 3']."""
    result = []
    while stichwort:
        result.insert(0, stichwort)
        stichwort = STICHWORTE[stichwort].get('basis')
    return result


@lru_cache
def regeln(stichwort):
    """Alle Regeln eines Stichworts inklusive Basis-Stufen und besonderer Regelungen (nicht verändern: Cache)."""
    alle = [r for s in kette(stichwort) for r in parse_alarm(STICHWORTE[s]['alarm'], s)]
    for name, schwellen, einheit, typen, anzahl in BESONDERE:
        if not ab(stichwort, schwellen):
            continue
        wanted = {_norm(t) for t in _typen(typen)}
        if not any(r['einheit'] == einheit and not r['optional'] and wanted & {_norm(t) for t in r['typen']}
                   for r in alle):
            alle.append({'einheit': einheit, 'typ_text': typen, 'typen': _typen(typen), 'anzahl': anzahl,
                         'alle': False, 'optional': False, 'bedingung': '', 'sonder': {}, 'quelle': name})
    return tuple(alle)


def meldungen(stichwort):
    """Virtuelle Kräfte über die Leitstelle (Rettungsdienst, Polizei, Presse …), keine Fahrzeuge."""
    result = []
    for s in kette(stichwort):
        result += [m for m in STICHWORTE[s].get('meldungen', ()) if m not in result]
    if ab(stichwort, PRESSE_AB) and PRESSE not in result:
        result.append(PRESSE)
    return result


def passt_zum_ort(stichwort, ort):
    """Ortsbedingung (VEG nur an Feld/Wald, Schiene nur an einer Bahnstrecke)."""
    need = STICHWORTE.get(stichwort, {}).get('orte')
    return not need or bool(set(need) & set(ORTE.get(ort, ())))


def frontend_liste():
    """Stichwortliste fürs Frontend (Auswahl der Leitstelle)."""
    return [{'key': k, 'name': s['name'], 'gruppe': s['gruppe'], 'beschreibung': s.get('beschreibung', ''),
             'hinweis': s.get('hinweis', ''), 'basis': s.get('basis', ''), 'meldungen': meldungen(k)}
            for k, s in STICHWORTE.items()]


# ------------------------------------------------------------------ Einsatzbereich und Vorschlag

def einsatzbereich(ort=None, pos=None, standorte=None):
    """(zuständiger LZ, Nachbar-LZ). Bekannte Orte aus EINSATZBEREICHE, sonst die zwei nächsten LZ-Standorte."""
    text = str(ort or '').lower()
    for name, bereich in EINSATZBEREICHE.items():
        if name.lower() in text:
            return bereich
    if pos and standorte:
        lz = sorted((e for e in standorte if e in LOESCHZUEGE), key=lambda e: _dist(standorte[e], pos))
        if len(lz) >= 2:
            return lz[0], lz[1]
    return 'LZ1', 'LZ2'


def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** .5


def _slots(stichwort, zust):
    """Regeln in einzelne Plätze (je ein Fahrzeug) auflösen."""
    slots, alle_einheiten = [], []
    for r in regeln(stichwort):
        if r['alle']:
            alle_einheiten.append((r['einheit'], r))
            continue
        if r['einheit'] == 'alle LZ':
            einheiten_liste = [[lz] for lz in LOESCHZUEGE]
        elif r['einheit'] == 'zuständig':
            einheiten_liste = [[zust]]
        else:
            einheiten_liste = [[e.strip() for e in r['einheit'].split(' oder ')]]
        for einheiten in einheiten_liste:
            typen = r['typen']
            if len(einheiten) == 1 and einheiten[0] in r['sonder']:
                typen = r['sonder'][einheiten[0]]
            label = 'zuständig' if r['einheit'] == 'zuständig' else ' oder '.join(kurz(e) for e in einheiten)
            if r['einheit'] == 'zuständig':
                label += f' ({kurz(zust)})'
            for _ in range(r['anzahl']):
                slots.append({'einheiten': einheiten, 'typen': typen, 'norm': [_norm(t) for t in typen],
                              'optional': r['optional'], 'bedingung': r['bedingung'], 'quelle': r['quelle'],
                              'zustaendig': r['einheit'] == 'zuständig',
                              'regel': f'{label}: {"/".join(typen) if len(typen) < 4 else r["typ_text"]}'})
    # Erst feste Typen, dann Gruppen; Pflicht vor optional. sorted() ist stabil: sonst Reihenfolge der AAO.
    slots.sort(key=lambda s: (s['optional'], len(s['typen']) > 1))
    return slots, alle_einheiten


def vorschlag(stichwort, fahrzeuge, *, ort=None, pos=None, frei=lambda v: True, bereits=(), bevorzugt=None):
    """Fahrzeuge für ein Stichwort nach AAO.

    fahrzeuge: alle Fahrzeuge (dicts mit id, typ/kind, einheit/unit, base). frei(v): alarmierbar?
    bereits: IDs, die schon am Einsatz sind; sie füllen ihre Plätze (Hochstufen alarmiert nur die Differenz).
    bevorzugt(v): bei gleicher Eignung zuerst (z. B. Spielerfahrzeuge).

    Ergebnis: {'stichwort', 'zustaendig', 'nachbar', 'fahrzeuge': [{id, call, typ, einheit, status, regel,
    optional, hinweis}], 'fehlt': [{regel, hinweis, optional}], 'meldungen': [...]}. status: 'alarmiert' (schon
    da), 'neu' (laut AAO), 'ersatz' (anderes Fahrzeug oder andere Einheit, Grund in hinweis).
    """
    if stichwort not in STICHWORTE:
        raise ValueError('Unbekanntes Stichwort')
    fahrzeuge = list(fahrzeuge)
    by_id = {v['id']: v for v in fahrzeuge}
    standorte = {}
    for v in fahrzeuge:
        if v.get('base'):
            standorte.setdefault(einheit_von(v), v['base'])
    zust, nachbar = einsatzbereich(ort, pos, standorte)
    slots, alle_einheiten = _slots(stichwort, zust)
    target = pos or standorte.get(zust)
    used = set()
    ergebnis = []

    def entry(v, slot, status, hinweis=''):
        used.add(v['id'])
        ergebnis.append({'id': v['id'], 'call': v.get('call', v['id']), 'typ': typ_von(v), 'einheit': einheit_von(v),
                         'status': status, 'regel': slot['regel'], 'optional': slot['optional'],
                         'bedingung': slot['bedingung'], 'hinweis': hinweis})

    # 1. Fahrzeuge, die schon am Einsatz sind, füllen passende Plätze.
    offen = list(slots)
    schon = [by_id[i] for i in bereits if i in by_id]
    for passt in (lambda v, s: einheit_von(v) in s['einheiten'] and _norm(typ_von(v)) in s['norm'],
                  lambda v, s: _norm(typ_von(v)) in s['norm'],
                  lambda v, s: any(_GLEICH.get(_norm(typ_von(v))) is _GLEICH.get(n) is not None for n in s['norm'])):
        for v in schon:
            if v['id'] in used:
                continue
            slot = next((s for s in offen if not s['optional'] and passt(v, s)), None)
            if slot:
                offen.remove(slot)
                entry(v, slot, 'alarmiert')
    for v in schon:  # nachalarmierte Zusatzfahrzeuge ohne AAO-Platz
        if v['id'] not in used:
            used.add(v['id'])
            ergebnis.append({'id': v['id'], 'call': v.get('call', v['id']), 'typ': typ_von(v),
                             'einheit': einheit_von(v), 'status': 'alarmiert', 'regel': 'zusätzlich',
                             'optional': False, 'bedingung': '', 'hinweis': ''})

    fehlt = []

    def waehle(slot, bis_rang=9):
        """Bestes freies Fahrzeug für einen Platz: (Fahrzeug, Hinweis) oder (None, Grund).

        Rang 0: verlangte Einheit und Typ; 1: zuständiger LZ mit gleichwertigem Fahrzeug; 2: Typ aus anderer
        Einheit; 3/4: gleichwertig aus der Einheit bzw. von anderswo. bis_rang begrenzt die Suche."""
        heim = slot['einheiten']
        gleich = {_norm(t) for n in slot['norm'] for t in _GLEICH.get(n, ())} - set(slot['norm'])

        def rang(v):
            e, t = einheit_von(v), _norm(typ_von(v))
            if e in heim and t in slot['norm']:
                return 0
            if slot['zustaendig'] and e in heim and t in gleich:
                return 1  # zuständiger LZ mit gleichwertigem Fahrzeug rückt selbst aus
            if t in slot['norm']:
                return 2
            if e in heim and t in gleich:
                return 3
            if t in gleich:
                return 4
            return None

        kandidaten = []
        for v in fahrzeuge:
            if v['id'] in used or not frei(v):
                continue
            rg = rang(v)
            if rg is None or rg > bis_rang:
                continue
            e = einheit_von(v)
            entfernung = _dist(v['base'], target) if v.get('base') and target else 0
            kandidaten.append(((rg, heim.index(e) if e in heim else 9, not (bevorzugt and bevorzugt(v)), e != nachbar,
                                entfernung, slot['norm'].index(_norm(typ_von(v))) if _norm(typ_von(v)) in
                                slot['norm'] else 9, v['id']), v))
        eigene = [x for x in fahrzeuge if einheit_von(x) in heim and _norm(typ_von(x)) in slot['norm']]
        if not eigene:
            grund = 'nicht vorhanden'
        elif any(frei(x) for x in eigene):
            grund = 'alle schon eingeplant'
        else:
            grund = 'nicht frei'
        if not kandidaten:
            return None, grund
        (rg, *_), v = min(kandidaten, key=lambda k: k[0])
        if rg == 0:
            return v, ''
        return v, f'Ersatz für {slot["regel"]} ({grund})'

    # 2. Freie Plätze füllen: erst alle mit Fahrzeugen der eigenen Einheit, dann Ersatz. So nimmt ein Ersatz
    #    keinem späteren Platz das eigene Fahrzeug weg.
    rest = []
    for slot in offen:
        v, hinweis = waehle(slot, bis_rang=1)
        if v:
            entry(v, slot, 'ersatz' if hinweis else 'neu', hinweis)
        else:
            rest.append(slot)
    for slot in rest:
        v, hinweis = waehle(slot)
        if v:
            entry(v, slot, 'ersatz' if hinweis else 'neu', hinweis)
        else:
            fehlt.append({'regel': slot['regel'], 'hinweis': hinweis, 'optional': slot['optional']})

    # 3. „alle“: die übrigen Fahrzeuge der Einheit.
    for einheit, r in alle_einheiten:
        slot = {'regel': f'{kurz(einheit)}: alle Fahrzeuge', 'optional': r['optional'], 'bedingung': r['bedingung']}
        for v in fahrzeuge:
            if einheit_von(v) == einheit and v['id'] not in used:
                if v['id'] in bereits:
                    entry(v, slot, 'alarmiert')
                elif frei(v):
                    entry(v, slot, 'neu')
                else:
                    used.add(v['id'])
                    fehlt.append({'regel': f'{kurz(einheit)}: {typ_von(v)}', 'hinweis': 'nicht frei',
                                  'optional': r['optional']})

    # 4. Abrollbehälter nur mit WLF (besondere Regelung): je AB ein WLF, bevorzugt aus derselben Einheit.
    pflicht = [x for x in ergebnis if not x['optional']]
    for einheit in sorted({x['einheit'] for x in pflicht}):
        abs_ = sum(1 for x in pflicht if x['einheit'] == einheit and _norm(x['typ']).startswith('ab'))
        wlfs = sum(1 for x in pflicht if x['einheit'] == einheit and _norm(x['typ']) == _norm(WLF))
        for _ in range(abs_ - wlfs):
            slot = {'einheiten': [einheit, 'FTZ'], 'typen': [WLF], 'norm': [_norm(WLF)], 'optional': False,
                    'bedingung': '', 'zustaendig': False, 'regel': f'{kurz(einheit)}: WLF für Abrollbehälter'}
            v, hinweis = waehle(slot)
            if v:
                entry(v, slot, 'neu' if not hinweis and einheit_von(v) == einheit else 'ersatz',
                      hinweis or ('' if einheit_von(v) == einheit else f'WLF aus {kurz(einheit_von(v))}'))
            else:
                fehlt.append({'regel': slot['regel'], 'hinweis': hinweis, 'optional': False})

    return {'stichwort': stichwort, 'name': STICHWORTE[stichwort]['name'], 'zustaendig': zust, 'nachbar': nachbar,
            'hinweis': STICHWORTE[stichwort].get('hinweis', ''), 'fahrzeuge': ergebnis, 'fehlt': fehlt,
            'meldungen': meldungen(stichwort)}


def soll(stichwort, fahrzeuge=None, ort=None):
    """Zahl der Pflichtfahrzeuge laut AAO (mit der AAO-Flotte, ohne Rücksicht auf frei/belegt)."""
    v = vorschlag(stichwort, fahrzeuge or flotte_liste(), ort=ort)
    return sum(1 for x in v['fahrzeuge'] if not x['optional']) + sum(1 for x in v['fehlt'] if not x['optional'])


def migriere_einsatz(inc):
    """Einsatz aus einem gespeicherten Raum auf AAO-Stichworte umstellen (F1 → B 1, TH1 → TH 1 …)."""
    inc['title'] = migriere_titel(inc.get('title', ''))
    inc['stichwort'] = normalisiere(inc.get('stichwort')) or stichwort_aus_titel(inc['title'])
    return inc
