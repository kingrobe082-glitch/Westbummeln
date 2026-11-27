"""Die echte Flotte der FF Westbummeln: Einheiten, Fahrzeugtypen und Fahrzeuge.

Quellen (Stand 10.11.2026): Wachübersicht, Alarm- und Ausrückeordnung (Abschnitt 2) und
Funkrufnamen-Verzeichnis der FF Westbummeln. Die Gerätehäuser GH1–GH5 haben je ein LF 10
(Entscheidung Lars, 27.11.2026); Anhänger, Abrollbehälter, ATV und die Gerätehäuser stehen nicht im
Funkrufnamen-Verzeichnis, ihre Rufnamen folgen demselben Schema (Vorschlag).

Diese Datei ist die Datenschnittstelle für Spiellogik und AAO: Kennungen und Typnamen nur
abgestimmt ändern. Reine Daten, ohne Django.

Koordinaten wie überall im Spiel: Anteile (0–1) der vollständigen Karte static/karte.webp.
Die gedruckte Karte ist anders beschriftet als die Wachübersicht (dort steht z. B. „LZ1 FW West“).
Es gilt die Wachübersicht; die Wachen sind nach Himmelsrichtung zugeordnet, das Frontend legt
eigene Standort-Schilder über die gedruckten (`schild`).
"""
import re

# ------------------------------------------------------------------ Einheiten

# Wachen auf der gedruckten Karte (Gebäude), über die die Einheiten verteilt sind.
_WACHE_ALTSTADT = [.466, .51]  # gedruckt „LZ2 FW Altstadt“ (E4)

EINHEITEN = {
    'LZ1': {
        'name': 'LZ 1 Mitte', 'standort_nr': 1, 'fachgebiet': 'Brandschutz',
        'wehrleitung': 'Samuel', 'stv': 'Felix', 'pos': [.41, .49],
        'karte': 'Gebäude „Freiwillige Feuerwehr Westbummeln“ (D4)', 'schild': [.395, .432],
    },
    'LZ2': {
        'name': 'LZ 2 Altstadt', 'standort_nr': 2, 'fachgebiet': 'Wasserversorgung',
        'wehrleitung': 'Jonas', 'stv': 'Sev', 'pos': _WACHE_ALTSTADT,
        'karte': 'FW Altstadt (E4, gedruckt „LZ2“)', 'schild': [.488, .471],
    },
    'LZ3': {
        'name': 'LZ 3 Süd', 'standort_nr': 3, 'fachgebiet': 'Verpflegung',
        'wehrleitung': 'Fynn', 'stv': 'Jonas', 'pos': [.548, .80],
        'karte': 'FW Süd (G6, gedruckt „LZ5“)', 'schild': [.573, .749],
    },
    'LZ4': {
        'name': 'LZ 4 Nord', 'standort_nr': 4, 'fachgebiet': 'Technische Hilfeleistung',
        'wehrleitung': 'Finn', 'stv': 'Paul', 'pos': [.565, .215],
        'karte': 'FW Nord (B6, gedruckt „LZ3“)', 'schild': [.59, .163],
    },
    'LZ5': {
        'name': 'LZ 5 West', 'standort_nr': 5, 'fachgebiet': 'Vegetation',
        'wehrleitung': 'Robin', 'stv': 'Lars', 'pos': [.235, .55],
        'karte': 'FW West (E1, gedruckt „LZ1“)', 'schild': [.26, .50],
    },
    'LZ6': {
        'name': 'LZ 6 Ost', 'standort_nr': 6, 'fachgebiet': 'Lagedienst',
        'wehrleitung': 'Benji', 'stv': 'Linnea', 'pos': [.827, .46],
        'karte': 'FW Ost (D10, gedruckt „LZ4“)', 'schild': [.85, .414],
    },
    'FTZ': {
        'name': 'FTZ Westbummeln', 'standort_nr': 7, 'fachgebiet': 'Führung und Logistik',
        'wehrleitung': 'Chris (Kreisbrandmeister)', 'stv': None, 'pos': _WACHE_ALTSTADT,
        'karte': 'bei LZ 2 Altstadt (E4)', 'schild': None,
    },
    'GH1': {
        'name': 'GH Birkenhof', 'standort_nr': 8, 'fachgebiet': None, 'wehrleitung': None, 'stv': None,
        'pos': [.38, .16], 'karte': 'Birkenweg 5 (B3)', 'schild': None,
    },
    'GH2': {
        'name': 'GH Ahorn', 'standort_nr': 9, 'fachgebiet': None, 'wehrleitung': None, 'stv': None,
        'pos': [.90, .37], 'karte': 'Ahornallee 12 (C11)', 'schild': None,
    },
    'GH3': {
        'name': 'GH Tannenfeld', 'standort_nr': 10, 'fachgebiet': None, 'wehrleitung': None, 'stv': None,
        'pos': [.88, .23], 'karte': 'Tannenweg 8 (B11)', 'schild': None,
    },
    'GH4': {
        'name': 'GH Bummelbach', 'standort_nr': 11, 'fachgebiet': None, 'wehrleitung': None, 'stv': None,
        'pos': [.27, .84], 'karte': 'Bachstraße 6 (G2)', 'schild': None,
    },
    'GH5': {
        'name': 'GH Industrie', 'standort_nr': 12, 'fachgebiet': None, 'wehrleitung': None, 'stv': None,
        'pos': [.92, .84], 'karte': 'Werkstraße 7 (G10)', 'schild': None,
    },
}
# Gedruckte Wache ohne Einheit: Das Frontend überdeckt dort das Schild „LZ6 FW Nordwest“.
FREIE_WACHEN = [{'name': 'Wache Nordwest', 'pos': [.276, .15], 'schild': [.282, .091], 'karte': 'A2'}]

# ------------------------------------------------------------------ Typen

KFZ, ANHAENGER, AB = 'kfz', 'anhaenger', 'ab'


def _typ(kategorie, sitze, grafik, faehigkeiten, tank_l=0, funk=None, zug=()):
    """funk: Fahrzeugteil im Rufnamen, falls er vom Typnamen abweicht (laut Funkrufnamen-Verzeichnis).
    zug: Typen, die diesen Anhänger bzw. Abrollbehälter ziehen bzw. tragen dürfen."""
    return {'kategorie': kategorie, 'sitze': sitze, 'tank_l': tank_l, 'faehigkeiten': list(faehigkeiten),
            'grafik': grafik, 'funk': funk, 'zug': list(zug)}


_LOESCH = ('loeschen', 'pumpe', 'atemschutz')
_KUECHE = ('GW-L1', 'MZF')
TYPEN = {
    # Löschfahrzeuge
    'HLF 20': _typ(KFZ, 9, 'lf-gross', (*_LOESCH, 'rettungssatz'), 2000),
    'HLF 10': _typ(KFZ, 9, 'lf-gross', (*_LOESCH, 'rettungssatz'), 1000),
    'LF 20': _typ(KFZ, 9, 'lf-gross', _LOESCH, 2000),
    'LF 20 Wald': _typ(KFZ, 9, 'lf-gross', (*_LOESCH, 'wald', 'gelaende'), 2000, funk='LF 20'),
    'LF 10': _typ(KFZ, 9, 'lf-klein', _LOESCH, 1200),
    'MLF': _typ(KFZ, 6, 'lf-klein', _LOESCH, 1000),
    'TSF-W': _typ(KFZ, 6, 'lf-klein', _LOESCH, 750),
    'TLF 3000': _typ(KFZ, 3, 'tlf', (*_LOESCH, 'wasser_transport'), 3000),
    'TLF 4000': _typ(KFZ, 3, 'tlf', (*_LOESCH, 'wasser_transport'), 4000),
    'GTLF': _typ(KFZ, 3, 'tlf', ('loeschen', 'pumpe', 'wasser_transport', 'wald'), 8000),
    # Hubrettung, Rüst- und Gerätewagen
    'DLK 23/12': _typ(KFZ, 3, 'dlk', ('hubrettung',), funk='DLK'),
    'RW': _typ(KFZ, 3, 'rw', ('rettungssatz', 'heben', 'oel')),
    'GW-L1': _typ(KFZ, 3, 'gw', ('logistik', 'verpflegung')),
    'GW-Öl': _typ(KFZ, 3, 'gw', ('oel',)),
    'GW HRett': _typ(KFZ, 6, 'gw', ('hoehenrettung',)),
    'GW-G': _typ(KFZ, 3, 'gw', ('gefahrgut',)),
    'GW-Nachschub': _typ(KFZ, 3, 'gw', ('logistik', 'atemschutz')),
    'GW-MANV': _typ(KFZ, 3, 'gw', ('manv',)),
    'SW 2000': _typ(KFZ, 3, 'gw', ('wasserversorgung',)),
    'Tankwagen': _typ(KFZ, 2, 'tlf', ('wasser_transport',), 10000),
    'WLF': _typ(KFZ, 3, 'wlf', ('wechsellader',)),
    # Führung und Transport
    'ELW 1': _typ(KFZ, 4, 'mtw', ('fuehrung',)),
    'ELW 2': _typ(KFZ, 6, 'mtw', ('fuehrung',)),
    'KdoW Wald': _typ(KFZ, 4, 'kdow', ('fuehrung', 'wald', 'gelaende'), funk='KdoW'),
    'KdoW Lage': _typ(KFZ, 4, 'kdow', ('fuehrung',), funk='KdoW'),
    'KdoW KBM': _typ(KFZ, 4, 'kdow', ('fuehrung',), funk='KdoW'),
    'MTW': _typ(KFZ, 9, 'mtw', ('transport',)),
    'MZF': _typ(KFZ, 6, 'mtw', ('transport', 'logistik')),
    'MZF Drohne': _typ(KFZ, 6, 'mtw', ('transport', 'drohne'), funk='MZF'),
    'ATV': _typ(KFZ, 2, 'atv', ('gelaende', 'wald')),
    # Anhänger: fahren nur hinter einem passenden Zugfahrzeug derselben Einheit
    'Anh Tierrettung': _typ(ANHAENGER, 0, 'anh', ('tierrettung',), zug=('HLF 20',)),
    'Anh Küche': _typ(ANHAENGER, 0, 'anh', ('verpflegung',), zug=_KUECHE),
    'Anh Kühlung': _typ(ANHAENGER, 0, 'anh', ('verpflegung',), zug=_KUECHE),
    'Anh Radlader': _typ(ANHAENGER, 0, 'anh', ('heben', 'gelaende'), zug=('GTLF', 'TLF 4000', 'WLF')),
    'Anh ATV Trans': _typ(ANHAENGER, 0, 'anh', ('gelaende', 'transport'), zug=('KdoW Wald', 'LF 20 Wald')),
    # Abrollbehälter: nur auf einem WLF derselben Einheit oder des FTZ
    'AB-Schlauch': _typ(AB, 0, 'ab', ('wasserversorgung',), zug=('WLF',)),
    'AB-Wasser': _typ(AB, 0, 'ab', ('wasser_transport',), 10000, zug=('WLF',)),
    'AB-Schiene': _typ(AB, 0, 'ab', ('schiene',), zug=('WLF',)),
    'AB-Wald': _typ(AB, 0, 'ab', ('wald', 'logistik'), zug=('WLF',)),
    'AB-Dekon P': _typ(AB, 0, 'ab', ('dekon',), zug=('WLF',)),
    'AB-Dekon G': _typ(AB, 0, 'ab', ('dekon', 'gefahrgut'), zug=('WLF',)),
    'AB-Telelader': _typ(AB, 0, 'ab', ('heben', 'logistik'), zug=('WLF',)),
}
# Einheit, deren WLF Abrollbehälter aller Löschzüge tragen dürfen.
AB_POOL = 'FTZ'

# ------------------------------------------------------------------ Fahrzeuge

# Bestand je Einheit in der Reihenfolge der Wachübersicht: (Typ, Anzahl).
BESTAND = {
    'LZ1': [('HLF 20', 2), ('TLF 3000', 1), ('LF 20', 1), ('DLK 23/12', 2), ('MTW', 2), ('Anh Tierrettung', 1)],
    'LZ2': [('MLF', 2), ('TSF-W', 2), ('WLF', 2), ('Tankwagen', 1), ('SW 2000', 2), ('MTW', 4),
            ('AB-Schlauch', 1), ('AB-Wasser', 1)],
    'LZ3': [('HLF 20', 1), ('DLK 23/12', 1), ('ELW 1', 1), ('GW-L1', 1), ('MZF', 2), ('Anh Küche', 1),
            ('Anh Kühlung', 1)],
    'LZ4': [('HLF 10', 2), ('RW', 2), ('GW-Öl', 1), ('WLF', 1), ('AB-Schiene', 1), ('GW HRett', 1), ('GW-G', 1)],
    'LZ5': [('TLF 3000', 2), ('TLF 4000', 1), ('GTLF', 1), ('ATV', 2), ('KdoW Wald', 1), ('WLF', 1),
            ('LF 20 Wald', 1), ('AB-Wald', 1), ('AB-Schlauch', 1), ('Anh Radlader', 1), ('Anh ATV Trans', 1)],
    'LZ6': [('HLF 20', 1), ('RW', 1), ('MTW', 2), ('MZF Drohne', 2), ('ELW 1', 1), ('KdoW Lage', 1)],
    'FTZ': [('KdoW KBM', 1), ('ELW 1', 2), ('ELW 2', 1), ('GW-Nachschub', 1), ('GW-MANV', 1), ('WLF', 2),
            ('AB-Dekon P', 1), ('AB-Dekon G', 1), ('AB-Telelader', 1)],
    **{f'GH{n}': [('LF 10', 1)] for n in range(1, 6)},
}
_ASCII = str.maketrans({'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue', 'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss'})


def _id_teil(typ):
    """Typname als Teil der Fahrzeug-ID: nur ASCII, ohne Leerzeichen und Schrägstriche."""
    return re.sub(r'[^A-Za-z0-9-]', '', typ.translate(_ASCII))


def _funk_teil(typ):
    """Fahrzeugteil des Rufnamens. Im Verzeichnis fehlende Anhänger/AB: Leerzeichen werden Bindestriche."""
    funk = TYPEN[typ]['funk']
    if funk:
        return funk
    return typ.replace(' ', '-') if TYPEN[typ]['kategorie'] != KFZ else typ


def _fahrzeuge():
    liste = []
    for einheit, bestand in BESTAND.items():
        standort = EINHEITEN[einheit]['standort_nr']
        laufend = {}  # die laufende Nummer zählt je Standort und Rufnamen-Teil (z. B. „KdoW“)
        for typ, anzahl in bestand:
            for nr in range(1, anzahl + 1):
                funk = _funk_teil(typ)
                laufend[funk] = laufend.get(funk, 0) + 1
                liste.append({
                    'id': f'{einheit}-{_id_teil(typ)}-{nr}', 'typ': typ, 'einheit': einheit,
                    'rufname': f'Florian Westbummeln {standort} {funk}-{laufend[funk]}', 'nr': nr,
                })
    return liste


FAHRZEUGE = _fahrzeuge()
FAHRZEUG = {f['id']: f for f in FAHRZEUGE}


# ------------------------------------------------------------------ Hilfsfunktionen

def kategorie(fahrzeug_id):
    return TYPEN[FAHRZEUG[fahrzeug_id]['typ']]['kategorie']


def fahrzeuge_der_einheit(einheit):
    """Alle Fahrzeuge einer Einheit (Kennung wie 'LZ2'), in der Reihenfolge der Wachübersicht."""
    return [f for f in FAHRZEUGE if f['einheit'] == einheit]


def mit_faehigkeit(faehigkeit, einheit=None):
    """Fahrzeuge mit dieser Fähigkeit, optional nur einer Einheit."""
    return [f for f in FAHRZEUGE if faehigkeit in TYPEN[f['typ']]['faehigkeiten']
            and (einheit is None or f['einheit'] == einheit)]


def zugfahrzeuge_fuer(fahrzeug_id):
    """Alle Fahrzeuge, die diesen Anhänger bzw. Abrollbehälter ziehen dürfen, in Vorzugsreihenfolge:
    erst die eigene Einheit (in der Reihenfolge von TYPEN[typ]['zug']), bei Abrollbehältern danach die
    WLF des FTZ. Leer für Kfz."""
    f = FAHRZEUG[fahrzeug_id]
    typ = TYPEN[f['typ']]
    if typ['kategorie'] == KFZ:
        return []
    einheiten = [f['einheit']] + ([AB_POOL] if typ['kategorie'] == AB and f['einheit'] != AB_POOL else [])
    return [z for e in einheiten
            for z in sorted((z for z in fahrzeuge_der_einheit(e) if z['typ'] in typ['zug']),
                            key=lambda z: typ['zug'].index(z['typ']))]


def zugfahrzeug_fuer(fahrzeug_id, frei=None):
    """Erstes passendes Zugfahrzeug für einen Anhänger/Abrollbehälter oder None.

    frei: optionale Prüfung fahrzeug_id -> bool (z. B. „steht frei auf der Wache“)."""
    return next((z for z in zugfahrzeuge_fuer(fahrzeug_id) if frei is None or frei(z['id'])), None)


def frontend_daten():
    """Feste Daten fürs Frontend (einmal mit der Seite ausgeliefert, nicht bei jeder Abfrage)."""
    return {
        'einheiten': [{'id': k, 'name': e['name'], 'fachgebiet': e['fachgebiet'], 'schild': e['schild'],
                       'standort_nr': e['standort_nr'], 'pos': e['pos']} for k, e in EINHEITEN.items()],
        'freie_wachen': FREIE_WACHEN,
    }
