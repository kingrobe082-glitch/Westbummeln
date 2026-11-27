"""Einsatzbereiche neu berechnen: je Einsatzort die zwei Löschzüge mit der kürzesten Fahrt.

Aufruf im Projektordner:  .venv\\Scripts\\python tools\\einsatzbereiche.py
Gibt die Tabelle für game/aao.py (EINSATZBEREICHE) und eine lesbare Übersicht aus. Mit Fahrzeit nach Straßenart
(strassen.plan, ab PR #42), sonst nach Weglänge (strassen.route).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game import aao, engine, strassen  # noqa: E402

try:  # Wachen-Standorte der echten Flotte, sonst die alten aus der Spiellogik
    from game import flotte  # noqa: E402
    STANDORTE = {e: d['pos'] for e, d in flotte.EINHEITEN.items() if e in aao.LOESCHZUEGE}
except ImportError:
    STANDORTE = {f'LZ{n}': pos for n, pos in engine.BASE.items()}


def fahrt(start, ziel):
    if hasattr(strassen, 'plan'):
        return strassen.plan(start, ziel)[1][-1], 's'
    return strassen.length(strassen.route(start, ziel)), ' Einheiten'


def main():
    zeilen, tabelle = [], {}
    for name, x, y in engine.PLACES:
        werte = sorted((fahrt(pos, (x, y))[0], lz) for lz, pos in STANDORTE.items())
        (t1, lz1), (t2, lz2) = werte[:2]
        tabelle[name] = (lz1, lz2)
        zeilen.append(f'| {name} | {aao.kurz(lz1)} ({t1:.1f}) | {aao.kurz(lz2)} ({t2:.1f}) |')
    print('EINSATZBEREICHE = {')
    for name, (lz1, lz2) in tabelle.items():
        print(f"    '{name}': ('{lz1}', '{lz2}'),")
    print('}\n')
    print('| Ort | zuständig | Nachbar |\n|---|---|---|')
    print('\n'.join(zeilen))
    if tabelle != aao.EINSATZBEREICHE:
        print('\nAchtung: weicht von game/aao.py ab.')


if __name__ == '__main__':
    main()
