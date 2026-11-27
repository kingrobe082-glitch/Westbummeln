"""Maßnahmen-Katalog: nur Daten, keine Logik (die steckt in game/massnahmen.py).

Grundlage: docs/KONZEPT-MASSNAHMEN.md. Fahrzeuge werden über **Fähigkeiten** beschrieben, nicht über
Typnamen. Eine Maßnahme verlangt Fähigkeiten (z. B. `pumpe`), jedes Fahrzeug bringt welche mit. Ein neuer
Fahrzeugtyp (TLF, DLK, RW, ELW …) braucht deshalb nur einen Eintrag in FAHRZEUGTYPEN, ein neues Stichwort
nur einen Eintrag in KATALOG.

Bisher ist nur F1 als Katalog-Einsatz ausgebaut. Alle anderen Stichworte laufen über den alten
Fortschrittsbalken (Allgemein-Ablauf).
"""

# Fähigkeiten
ERKUNDEN = 'erkunden'          # Lage erkunden, Rückmeldung geben (jedes Fahrzeug mit Führungskraft)
PUMPE = 'pumpe'                # Feuerlöschkreiselpumpe: Wasserversorgung aufbauen, Schläuche speisen
LOESCHWASSER = 'loeschwasser'  # Löschwasserbehälter an Bord (Schnellangriff ohne Hydrant)
RETTUNGSSATZ = 'rettungssatz'  # hydraulischer Rettungssatz (Schere/Spreizer), z. B. TH2
EINSATZLEITUNG = 'einsatzleitung'  # Führungsfahrzeug mit Funk/Lagekarte

# Tankwasser in Spielsekunden Löschzeit je Liter (2000 l → 40 s).
TANK_SEKUNDEN_JE_LITER = 1 / 50

# Fahrzeugtypen. `tank` in Litern. Trupps ergeben sich aus den Sitzplätzen (TRUPPS_JE_SITZE).
FAHRZEUGTYPEN = {
    'HLF 20': {'faehigkeiten': (ERKUNDEN, PUMPE, LOESCHWASSER, RETTUNGSSATZ), 'tank': 1600},
    'LF 20': {'faehigkeiten': (ERKUNDEN, PUMPE, LOESCHWASSER), 'tank': 2000},
    'KdoW': {'faehigkeiten': (ERKUNDEN, EINSATZLEITUNG), 'tank': 0},
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
        'richtzeit': 150,  # Sekunden ab Eintreffen bis Abschluss für den Zeitbonus
        'tipps': {
            'wasser_aus': 'Wasserversorgung parallel zum Angriff aufbauen – der Tank hält nur 30–40 s.',
            'ohne_erkunden': 'Erst erkunden: Dann weißt du, ob Tankwasser reicht.',
            'eskalation': 'Früh mit zwei Trupps angreifen, dann greift das Feuer nicht über.',
        },
        'massnahmen': {
            'erkunden': {
                'name': 'Erkunden', 'icon': '🧭', 'dauer': 10, 'platz': 'fuehrung', 'braucht': (ERKUNDEN,),
                'info': 'Rundgang um die Einsatzstelle: Was brennt, wohin breitet es sich aus?',
            },
            'wasser': {
                'name': 'Wasserversorgung aufbauen', 'icon': '💧', 'dauer': 30, 'platz': 'trupp',
                'braucht': (PUMPE,), 'wirkung': 'wasser',
                'info': 'Hydrant → Sammelstück → Pumpe. Danach ist Löschwasser unbegrenzt.',
            },
            'angriff': {
                'name': 'Angriffsleitung legen & löschen', 'icon': '🧯', 'dauer': 15, 'platz': 'trupp',
                'braucht': (PUMPE, LOESCHWASSER), 'wirkung': 'loeschen', 'max': 2, 'pflicht': True,
                'weich': ['erkunden', 'wasser'], 'ki_warten': ['erkunden'],
                'info': 'C-Rohr vornehmen. Ohne Wasserversorgung löscht der Trupp mit dem Tankwasser.',
            },
            'nachloeschen': {
                'name': 'Nachlöschen & Kontrolle', 'icon': '🔦', 'dauer': 20, 'platz': 'trupp',
                'braucht': (PUMPE,), 'hart': [BRAND_AUS], 'pflicht': True,
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
    ERKUNDEN: 'Führungskraft',
    PUMPE: 'Pumpe',
    LOESCHWASSER: 'Löschwassertank',
    RETTUNGSSATZ: 'Rettungssatz',
    EINSATZLEITUNG: 'Einsatzleitung',
}
