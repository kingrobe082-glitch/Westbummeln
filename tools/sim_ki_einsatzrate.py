"""Simuliert die KI-Leitstelle ohne menschliche Leitstelle und misst, wie gut die Gruppenführer ausgelastet sind.

Nur ein Entwicklerwerkzeug, kein Teil der App. Die Zeit wird über `now` vorgespult, es braucht kein Django.

    python tools/sim_ki_einsatzrate.py                  # 1, 3 und 8 GF, je 30 Minuten, 5 Seeds
    python tools/sim_ki_einsatzrate.py --spieler 2 5 --minuten 60

Jeder simulierte GF besetzt ein eigenes Fahrzeug (je zwei an den Wachen der alten Flotte, ALT_IDS) und startet die
Maßnahmen REAKTION Sekunden nach Ankunft an der Einsatzstelle. Das Wetter wechselt wie im Spiel automatisch.

Spalten der Ausgabe:
  Einsätze   neu entstandene Einsätze im Zeitraum
  fertig     davon abgeschlossen
  idle       Anteil der Zeit, in der ein GF-Fahrzeug frei auf der Wache steht
  offen      gleichzeitig offene Einsätze, Mittelwert / Maximum
  Wartezeit  Sekunden vom Entstehen eines Einsatzes bis zum ersten Alarm (Mittelwert)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import engine  # noqa: E402

START = 1_000_000.0
ORDER = [engine.ALT_IDS[f'WB-{unit}-{kind}'] for kind in ('HLF20', 'LF20') for unit in range(1, 7)]


def simulate(players, minutes=30, seed=1, reaction=5):
    r = engine.new_room('SIM', seed=seed)
    pids = []
    for n in range(players):
        pid = engine.handle(r, {'action': 'join'}, n, f'GF{n}', False, START)['id']
        engine.handle(r, {'action': 'claim', 'id': pid, 'vehicle': ORDER[n]}, n, 'x', False, START)
        pids.append(pid)
    created, idle_seconds, open_sum, open_max = {}, 0, 0, 0
    first_alarm = {}
    seconds = minutes * 60
    for t in range(seconds):
        now = START + t
        for p in r['players'].values():
            p['last'] = now
        engine.update(r, now)
        for n, pid in enumerate(pids):
            v = r['vehicles'][ORDER[n]]
            inc = next((i for i in r['incidents'] if i['id'] == v['incident']), None)
            if inc and not inc['closed'] and not inc['working'] and v['phase'] == 'vorort' \
                    and now - v['phase_at'] >= reaction:
                engine.handle(r, {'action': 'work', 'id': pid, 'incident': inc['id']}, n, 'x', False, now)
            if v['phase'] == 'wache' and not v['incident']:
                idle_seconds += 1
        open_now = [i for i in r['incidents'] if not i['closed']]
        open_sum += len(open_now)
        open_max = max(open_max, len(open_now))
        for i in r['incidents']:
            created.setdefault(i['id'], (now, i))
            if i['assigned']:
                first_alarm.setdefault(i['id'], now)
    incidents = [i for _, i in created.values()]
    waits = [first_alarm.get(iid, START + seconds) - at for iid, (at, _) in created.items()]
    return {
        'created': len(incidents),
        'closed': sum(i['closed'] for i in incidents),
        'idle': idle_seconds / (seconds * players),
        'open_avg': open_sum / seconds,
        'open_max': open_max,
        'wait': sum(waits) / len(waits) if waits else 0,
        'titles': sorted({i['title'] for i in incidents}),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--spieler', type=int, nargs='+', default=[1, 3, 8])
    parser.add_argument('--minuten', type=int, default=30)
    parser.add_argument('--seeds', type=int, default=5)
    parser.add_argument('--reaktion', type=int, default=5)
    args = parser.parse_args()
    print('| GF | Einsätze | fertig | idle | offen Ø / max | Wartezeit Ø |')
    print('|---:|---:|---:|---:|---:|---:|')
    for players in args.spieler:
        runs = [simulate(players, args.minuten, seed, args.reaktion) for seed in range(1, args.seeds + 1)]

        def avg(key, runs=runs):
            return sum(run[key] for run in runs) / len(runs)
        print(f'| {players} | {avg("created"):.0f} | {avg("closed"):.0f} | {avg("idle"):.0%} | '
              f'{avg("open_avg"):.1f} / {max(run["open_max"] for run in runs)} | {avg("wait"):.0f} s |')


if __name__ == '__main__':
    main()
