"""Maßnahmen-Katalog: nur Daten, keine Logik (die steckt in game/massnahmen.py).

Grundlage: docs/KONZEPT-MASSNAHMEN.md. Fahrzeuge werden über **Fähigkeiten** beschrieben, nicht über
Typnamen. Eine Maßnahme verlangt Fähigkeiten (z. B. `pumpe`), jedes Fahrzeug bringt welche mit. Ein neuer
Fahrzeugtyp (TLF, DLK, RW, ELW …) braucht deshalb nur einen Eintrag in FAHRZEUGTYPEN, ein neues Stichwort
nur einen Eintrag in KATALOG.

Bisher ist nur F1 als Katalog-Einsatz ausgebaut (Schlüssel = Stichwort, z. B. später „B 1“ nach NRW-Schema;
Leerzeichen und Groß-/Kleinschreibung zählen beim Erkennen nicht). Alle anderen Stichworte laufen über den alten
Fortschrittsbalken (Allgemein-Ablauf). Im Code gibt es keine festen Stichwort- oder Maßnahmen-Schlüssel: die Logik
fragt nach `wirkung` (erkunden, wasser, loeschen) und nach `gegen` (Gegenmaßnahme je Eskalationsregel).
"""

# Fähigkeiten (gleiche Namen wie game/flotte.py der Session „Echte Flotte“)
LOESCHEN = 'loeschen'                  # Löschwassertank + Schläuche: Angriff, Nachlöschen
PUMPE = 'pumpe'                        # Feuerlöschkreiselpumpe
WASSERVERSORGUNG = 'wasserversorgung'  # Hydrant → Pumpe aufbauen (Saug-/Sammelstück, B-Schläuche)
WASSER_TRANSPORT = 'wasser_transport'  # großer Tank / Pendelverkehr (TLF, Tankwagen) – ab PR B/C
RETTUNGSSATZ = 'rettungssatz'          # hydraulischer Rettungssatz (Schere/Spreizer), z. B. TH2
HUBRETTUNG = 'hubrettung'              # Drehleiter – ab PR B
FUEHRUNG = 'fuehrung'                  # Führungsfahrzeug (KdoW, ELW)

# Tankwasser: Verbrauch je löschendem Trupp und Nachspeisen über die Wasserversorgung (Liter je Sekunde).
# 2000 l / 50 l/s = 40 s Löschzeit ohne Hydrant.
VERBRAUCH_L_JE_S = 50
NACHSPEISEN_L_JE_S = 40
TANK_WARNUNG = 1 / 3  # Warnung, wenn nur noch ⅓ im Tank ist (⅔ verbraucht)

# Fahrzeugtypen. `tank_l` = Tank in Litern (Füllstand steht im Fahrzeug als v['tank']).
# Trupps ergeben sich aus den Sitzplätzen (TRUPPS_JE_SITZE). Die echte Flotte (game/flotte.py) ersetzt diese Tabelle.
FAHRZEUGTYPEN = {
    'HLF 20': {'faehigkeiten': (LOESCHEN, PUMPE, WASSERVERSORGUNG, RETTUNGSSATZ), 'tank_l': 2000},
    'LF 20': {'faehigkeiten': (LOESCHEN, PUMPE, WASSERVERSORGUNG), 'tank_l': 2000},
    'KdoW': {'faehigkeiten': (FUEHRUNG,), 'tank_l': 0},
}

# (höchstens so viele Sitze, so viele Trupps). Führung (der GF selbst) kommt immer dazu.
TRUPPS_JE_SITZE = ((3, 1), (6, 2), (12, 3))

# Wetter: Arbeitstempo steht in engine.WORK_FACTOR; hier nur die Wirkung auf das Brandwachstum.
BRAND_WETTER = {'Windig': 1.3, 'Regen': .8}

LOESCHRATE = .8  # Brandpunkte pro Sekunde je löschendem Trupp
WASSER_AUS_WACHSTUM = 2  # „Wasser aus“: Brand wächst doppelt so schnell
OHNE_ERKUNDEN_AUFBAU = 5  # Angriff ohne Erkundung: Trupp sucht erst den Brandherd (+5 s)

# Ampel (Konzept 4.2)
STUFEN = {
    0: ('🟢', 'Lage stabil'),
    1: ('🟡', 'Lage verschärft'),
    2: ('🟠', 'Stichworterhöhung'),
    3: ('🔴', 'Schaden eingetreten'),
}

# Sonderbedingungen in `hart`/`weich` (alle anderen Einträge sind Schlüssel von Maßnahmen, die fertig sein müssen).
BRAND_AUS = 'brand_aus'
BEDINGUNGEN = {BRAND_AUS: 'Erst muss das Feuer aus sein'}

KATALOG = {
    'F1': {
        'name': 'Kleinbrand',
        'aao': ['LF 20'],
        'lage': {'brand': 15, 'wachstum': .2},
        # Brand-Schwelle → neues Stichwort. `warnung` Punkte vorher kommt die Warnung, unter `einfangen` gilt
        # die Lage wieder als unter Kontrolle.
        'eskalation': {'schwelle': 40, 'warnung': 10, 'einfangen': 25, 'stichwort': 'F2',
                       'aao': ['HLF 20', 'LF 20', 'KdoW'], 'ziel': 'Carport/Wohnhaus'},
        # Varianten: zufällig beim Anlegen (oder aus dem Titel), Erkunden deckt sie auf.
        'varianten': {
            'muelltonne': {'name': 'Mülltonne', 'brand': 10, 'titel': ('mülltonne', 'container'),
                           'meldung': 'Mülltonne brennt frei stehend, keine Ausbreitung.'},
            'gartenhuette': {'name': 'Gartenhütte', 'brand': 25, 'titel': ('gartenhütte', 'schuppen'),
                             'meldung': 'Gartenhütte brennt in voller Ausdehnung, Hecke zum Wohnhaus.'},
            'hecke': {'name': 'Hecke am Haus', 'brand': 20, 'wachstum': .3, 'titel': ('hecke',),
                      'meldung': 'Hecke brennt auf 10 m, Feuer läuft Richtung Wohnhaus.'},
            'pkw': {'name': 'PKW', 'brand': 20, 'wachstum': .25, 'titel': ('pkw', 'fahrzeug'), 'zufall': False,
                    'meldung': 'PKW brennt im Motorraum, keine Personen im Fahrzeug.'},
        },
        'ki': ['erkunden', 'angriff', 'wasser', 'nachloeschen'],
        # Gegenmaßnahme je Regel: die KI nimmt sie zuerst (E1 Wasser aus, E2 Feuer greift über).
        'gegen': {'E1': 'wasser', 'E2': 'angriff'},
        'richtzeit': 150,  # Sekunden ab Eintreffen bis Abschluss für den Zeitbonus
        'tipps': {
            'wasser_aus': 'Wasserversorgung parallel zum Angriff aufbauen – der Tank hält nur 30–40 s.',
            'ohne_erkunden': 'Erst erkunden: Dann weißt du, ob Tankwasser reicht.',
            'eskalation': 'Früh mit zwei Trupps angreifen, dann greift das Feuer nicht über.',
        },
        'massnahmen': {
            'erkunden': {
                'name': 'Erkunden', 'icon': '🧭', 'dauer': 10, 'platz': 'fuehrung', 'braucht': (),
                'wirkung': 'erkunden',
                'info': 'Rundgang um die Einsatzstelle: Was brennt, wohin breitet es sich aus?',
            },
            'wasser': {
                'name': 'Wasserversorgung aufbauen', 'icon': '💧', 'dauer': 30, 'platz': 'trupp',
                'braucht': (WASSERVERSORGUNG,), 'wirkung': 'wasser',
                'info': 'Hydrant → Sammelstück → Pumpe. Danach ist Löschwasser unbegrenzt.',
            },
            'angriff': {
                'name': 'Angriffsleitung legen & löschen', 'icon': '🧯', 'dauer': 15, 'platz': 'trupp',
                'braucht': (LOESCHEN,), 'wirkung': 'loeschen', 'max': 2, 'pflicht': True,
                'weich': ['erkunden', 'wasser'], 'ki_warten': ['erkunden'],
                'info': 'C-Rohr vornehmen. Ohne Wasserversorgung löscht der Trupp mit dem Tankwasser.',
            },
            'nachloeschen': {
                'name': 'Nachlöschen & Kontrolle', 'icon': '🔦', 'dauer': 20, 'platz': 'trupp',
                'braucht': (LOESCHEN,), 'hart': [BRAND_AUS], 'pflicht': True,
                'info': 'Glutnester ablöschen, mit der Wärmebildkamera kontrollieren.',
            },
        },
        # Hinweise, wenn eine weiche Voraussetzung fehlt (⚠️ Unterzeile am Button).
        'weich_text': {
            'erkunden': 'ohne Erkunden: Trupp sucht erst den Brandherd (+5 s)',
            'wasser': 'ohne Wasserversorgung: nur Tankwasser',
        },
    },
}

# Für Hinweise „Nur … “: welche Typen haben eine Fähigkeit?
FAEHIGKEIT_TEXT = {
    LOESCHEN: 'Löschwassertank',
    PUMPE: 'Pumpe',
    WASSERVERSORGUNG: 'Wasserversorgung',
    WASSER_TRANSPORT: 'Wassertransport',
    RETTUNGSSATZ: 'Rettungssatz',
    HUBRETTUNG: 'Drehleiter',
    FUEHRUNG: 'Einsatzleitung',
}
