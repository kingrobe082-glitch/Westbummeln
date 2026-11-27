"""Straßennetz der Einsatzkarte und schnellste Wege darauf.

Koordinaten wie überall im Spiel: Anteile (0–1) der vollständigen Karte static/karte.webp
(1536 × 1024 Pixel, inklusive Legende). Die Straßen wurden von der Karte abgelesen; jede Straße ist
eine Punktfolge, gemeinsame Kreuzungen stehen in JUNCTIONS und werden über ihren Namen verbunden.

Für Abstände wird x mit dem Seitenverhältnis der Karte gestreckt, damit eine Strecke in x-Richtung
genauso lang zählt wie eine gleich lange Strecke in y-Richtung.

Jede Straße hat eine Klasse wie in der Kartenlegende (Hauptstraße, Nebenstraße, Wohnstraße,
Weg/Feldweg). Die Fahrzeit einer Strecke ist Länge in Metern / Geschwindigkeit ihrer Klasse; der
schnellste Weg (plan) darf deshalb einen längeren Umweg über die Hauptstraße nehmen.
"""
import heapq
from functools import lru_cache
from itertools import pairwise

ASPECT = 1536 / 1024
# Maßstabsleiste unten rechts auf der Karte: 0–500 m sind 231 Pixel. Eine Abstandseinheit ist die Kartenhöhe (1024 px).
METERS_PER_UNIT = 1024 * 500 / 231

# Straßenklassen der Kartenlegende und Fahrgeschwindigkeit in Spiel-Metern pro Sekunde. Das Spiel läuft
# im Zeitraffer: Eine Fahrt im Ort dauert ~10 s, quer über die Karte ~30 s. Per Env änderbar
# (DRIVE_SPEED_* in westbummeln/settings.py, übertragen in game/apps.py).
CLASSES = ('haupt', 'neben', 'wohn', 'weg')
CLASS_NAMES = {'haupt': 'Hauptstraße', 'neben': 'Nebenstraße', 'wohn': 'Wohnstraße', 'weg': 'Weg / Feldweg'}
SPEED = {'haupt': 160, 'neben': 120, 'wohn': 90, 'weg': 50}
DOCK_CLASS = 'wohn'  # Anbindung von Wache oder Einsatzort an die nächste Straße (Hofeinfahrt)

JUNCTIONS = {
    'forst': (.430, .045),           # Forstweg / Abzweig Richtung Jägerstraße Ost
    'eichen_w': (.237, .210),        # Waldstraße / Eichenstraße
    'jaeger_w_n': (.213, .372),      # Jägerstraße West / Sportplatzring
    'bluete_s': (.252, .370),        # Blütenstraße / Sportplatzring
    'jaeger_o_s': (.418, .370),      # Jägerstraße Ost / Sportplatzring
    'jaeger_o_n': (.461, .122),      # Jägerstraße Ost, oberes Ende
    'eichen_o': (.431, .212),        # Eichenstraße / Jägerstraße Ost / Scheunenweg
    'bluete_o': (.424, .273),        # Blütenstraße / Jägerstraße Ost
    'schul_o': (.694, .401),         # Schulstraße / Querstraße zur Kirchstraße
    'kreuz_s': (.760, .375),         # Kreuzbergstraße / Ahornallee / Schulstraße
    'kreuz_flur': (.794, .249),      # Kreuzbergstraße / Flurstraße
    'kreuz_tanne': (.788, .303),     # Kreuzbergstraße / Tannenweg
    'kreuz_tf': (.835, .165),        # Kreuzbergstraße / Tannenfeld
    'kreuz_feld': (.853, .115),      # Kreuzbergstraße / Feldweg
    'tannenfeld_o': (.957, .273),    # Tannenfeld-Ring / Tannenweg
    'ahorn_o': (.977, .379),         # Ahornallee / östliche Randstraße
    'ahorn_quer': (.880, .380),      # Ahornallee / Verbindung zur Buchenstraße
    'buchen_w': (.876, .481),        # Buchenstraße / Nelkenweg / Zufahrt Kreisel
    'buchen_o': (.977, .462),        # Buchenstraße / östliche Randstraße
    'nelken_w': (.686, .475),        # Nelkenweg / Querstraße
    'kirch_o': (.655, .551),         # Kirchstraße / Querstraße / Mathias-Berg-Straße
    'kreisel': (.843, .547),         # Kreisverkehr
    'mozart_w': (.830, .598),        # Robin-Hof-Straße / Mozartweg
    'mozart_o': (.937, .660),        # Mozartweg / östliche Randstraße
    'mozart_gewerbe': (.868, .627),  # Mozartweg / Zufahrt Gewerbepark
    'erlen_o': (.976, .606),         # Erlenstraße, östliches Ende
    'buerger_m': (.672, .745),       # Bürgerstraße / Dorfblick (Nord) / Werkstraße
    'buerger_dorf': (.642, .818),    # Bürgerstraße / Dorfstraße
    'buerger_bach': (.620, .890),    # Bürgerstraße / Bummelbachweg / Dorfblick (Süd)
    'werk_gewerbe': (.745, .777),    # Werkstraße / Zufahrt Gewerbepark
    'sonne_dorfblick': (.558, .703),  # Sonnenstraße / Dorfblick (Nord)
    'sonne_kirch': (.577, .553),     # Sonnenstraße / Kirchstraße
    'rosen_kirch': (.512, .552),     # Rosengasse / Kirchstraße
    'kirch_w': (.475, .551),         # Kirchstraße, westliches Ende
    'haupt_gasse': (.437, .517),     # Hauptstraße / Gasse zur Kirchstraße
    'haupt_w': (.318, .515),         # Hauptstraße / Zufahrt FW West und Am Rathauspark
    'jaeger_w_s': (.223, .495),      # Jägerstraße West, unteres Ende
    'rosen_s': (.484, .707),         # Rosengasse / Straße am Marktplatz
    'markt_s': (.414, .706),         # Straße am Marktplatz / Zufahrt Marktplatz
    'rathaus_knick': (.362, .662),   # Am Rathauspark / Straße am Marktplatz
    'rathaus_w': (.317, .672),       # Am Rathauspark / Bachstraße
    'ufer_muehle': (.362, .793),     # Uferstraße / Bachstraße (keine Brücke zum Mühlenweg)
    'ufer_dorf': (.490, .815),       # Uferstraße geht in die Dorfstraße über
    'muehle_garten': (.245, .909),   # Mühlenweg / Gartenweg
    'garten_wiese': (.369, .957),    # Gartenweg / Wiesenstraße
}

# (Name, Punktfolge). Strings sind Kreuzungen aus JUNCTIONS, Tupel Zwischenpunkte entlang der Straße.
STREETS = [
    ('Waldstraße', ['forst', (.408, .065), (.388, .078), (.362, .095), (.346, .112), (.333, .142),
                    (.317, .156), (.287, .168), (.261, .186), 'eichen_w']),
    ('Jägerstraße West', ['eichen_w', (.222, .244), (.214, .293), 'jaeger_w_n']),
    ('Jägerstraße West', ['jaeger_w_n', (.211, .393), (.206, .442), (.208, .466), 'jaeger_w_s']),
    ('Hauptstraße', ['jaeger_w_s', (.250, .510), (.290, .515), 'haupt_w']),
    ('Hauptstraße', ['haupt_w', (.343, .515), (.408, .513), 'haupt_gasse', (.462, .515)]),
    ('Zufahrt FW West', ['haupt_w', (.313, .550), (.304, .569), (.280, .578), (.255, .575)]),
    ('Forstweg', ['forst', (.437, .029)]),
    ('Jägerstraße Ost', ['forst', (.440, .068), (.453, .098), 'jaeger_o_n']),
    ('Hofzufahrt', ['jaeger_o_n', (.480, .132), (.499, .117)]),
    ('Jägerstraße Ost', ['jaeger_o_n', (.447, .161), (.437, .190), 'eichen_o']),
    ('Jägerstraße Ost', ['eichen_o', (.424, .259), 'bluete_o', (.421, .303), (.419, .342), 'jaeger_o_s']),
    ('Eichenstraße', ['eichen_w', (.287, .205), (.315, .222), (.349, .214), (.375, .205),
                      (.408, .205), 'eichen_o']),
    ('Blütenstraße', ['bluete_s', (.248, .342), (.250, .303), (.255, .273), (.278, .259),
                      (.294, .254), (.330, .256), (.375, .264), (.408, .271), 'bluete_o']),
    ('Sportplatzring', ['jaeger_w_n', 'bluete_s', (.300, .371), (.350, .371), 'jaeger_o_s']),
    ('Schulstraße', ['jaeger_o_s', (.480, .369), (.560, .369), (.642, .369), (.668, .383), 'schul_o']),
    ('Schulstraße', ['schul_o', (.720, .390), 'kreuz_s']),
    ('Scheunenweg', ['eichen_o', (.460, .225), (.489, .227), (.547, .234), (.603, .239), (.668, .239)]),
    ('Flurstraße', [(.668, .239), (.700, .239), (.749, .244), (.775, .248), 'kreuz_flur']),
    ('Feldweg', [(.684, .112), (.700, .117), (.733, .105), (.765, .095), (.798, .093), (.830, .103),
                 'kreuz_feld']),
    ('Kreuzbergstraße', [(.877, .029), (.876, .073), 'kreuz_feld', 'kreuz_tf', (.820, .195),
                         'kreuz_flur', 'kreuz_tanne', (.788, .342), 'kreuz_s']),
    ('Tannenfeld', ['kreuz_tf', (.850, .173), (.895, .183), (.928, .195), (.947, .220), (.960, .254),
                    'tannenfeld_o']),
    ('Tannenweg', ['kreuz_tanne', (.824, .303), (.863, .293), (.912, .283), 'tannenfeld_o']),
    ('Tannenfeld', ['tannenfeld_o', (.970, .313), (.977, .352), 'ahorn_o']),
    ('Ahornallee', ['kreuz_s', (.800, .376), 'ahorn_quer', (.940, .379), 'ahorn_o']),
    ('Östliche Randstraße', ['ahorn_o', (.980, .418), 'buchen_o']),
    ('Querweg Ahornallee', ['ahorn_quer', (.879, .442), 'buchen_w']),
    ('Buchenstraße', ['buchen_w', (.912, .481), (.947, .476), 'buchen_o']),
    ('Querstraße', ['schul_o', (.691, .432), 'nelken_w', (.674, .515), 'kirch_o']),
    ('Nelkenweg', ['nelken_w', (.700, .481), (.749, .476), (.798, .481), (.837, .488), (.860, .489),
                   'buchen_w']),
    ('Zufahrt Kreisel', ['buchen_w', (.863, .491), (.853, .515), 'kreisel']),
    ('Kirchstraße', ['kirch_w', 'rosen_kirch', 'sonne_kirch', (.620, .551), 'kirch_o']),
    ('Mathias-Berg-Straße', ['kirch_o', (.668, .556), (.700, .559), (.749, .550), (.798, .542),
                             'kreisel']),
    ('Erlenstraße', ['kreisel', (.879, .550), (.912, .564), (.947, .584), 'erlen_o']),
    ('Östliche Randstraße', ['erlen_o', (.965, .635), 'mozart_o']),
    ('Robin-Hof-Straße', ['kreisel', (.837, .569), 'mozart_w', (.818, .610), (.804, .633),
                          (.765, .657), (.733, .676), (.700, .694), 'buerger_m']),
    ('Mozartweg', ['mozart_w', (.856, .623), 'mozart_gewerbe', (.895, .637), 'mozart_o']),
    # Zufahrt zwischen Moped-Garage und den Hallen hindurch, nicht quer über die Dächer.
    ('Gewerbepark', ['mozart_gewerbe', (.866, .674), (.851, .703), (.831, .720), (.807, .709), (.778, .710),
                     (.762, .728), (.742, .765), 'werk_gewerbe']),
    ('Werkstraße', ['buerger_m', (.700, .772), 'werk_gewerbe', (.798, .801), (.846, .821), (.895, .835),
                    (.944, .860), (.970, .884), (.983, .913)]),
    ('Bürgerstraße', ['buerger_m', (.655, .786), 'buerger_dorf', (.632, .850), 'buerger_bach',
                      (.609, .933), (.600, .962)]),
    ('Dorfblick', ['sonne_dorfblick', (.600, .704), (.640, .715), 'buerger_m']),
    ('Dorfblick', ['buerger_bach', (.642, .894), (.668, .913), (.700, .933), (.740, .953)]),
    ('Sonnenstraße', ['sonne_kirch', (.564, .593), (.557, .637), (.554, .681), 'sonne_dorfblick']),
    ('Rosengasse', ['rosen_kirch', (.505, .593), (.495, .633), (.486, .676), 'rosen_s']),
    ('Gasse', ['haupt_gasse', (.455, .537), 'kirch_w']),
    ('Am Marktplatz', ['rathaus_knick', (.379, .690), 'markt_s', (.440, .713), 'rosen_s']),
    ('Marktplatz', ['markt_s', (.412, .660)]),
    ('Am Rathauspark', ['haupt_w', (.326, .593), (.336, .613), (.350, .640), 'rathaus_knick']),
    ('Am Rathauspark', ['rathaus_w', (.340, .667), 'rathaus_knick']),
    ('Bachstraße', ['rathaus_w', (.304, .713), (.306, .738), (.326, .767), (.349, .786), 'ufer_muehle']),
    ('Uferstraße', ['ufer_muehle', (.375, .796), (.408, .801), (.440, .806), 'ufer_dorf']),
    ('Dorfstraße', ['ufer_dorf', (.548, .818), 'buerger_dorf']),
    # Der Bummelbachweg beginnt am Ende von Garten- und Wiesenstraße; über ihn und die Brücke der
    # Bürgerstraße ist der Südwesten (Mühlenweg, GH4) angebunden.
    ('Bummelbachweg', ['garten_wiese', (.386, .960), (.405, .957), (.414, .933), (.427, .913), (.460, .903),
                       (.538, .884), (.586, .882), 'buerger_bach']),
    # Der Mühlenweg endet am Ufer: Zwischen Bachstraße und Mühlenweg gibt es keine Brücke.
    ('Mühlenweg', [(.335, .842), (.300, .840), (.278, .840), (.258, .855),
                   (.248, .884), 'muehle_garten']),
    ('Mühlenweg', ['muehle_garten', (.229, .938), (.216, .962)]),
    ('Gartenweg', ['muehle_garten', (.278, .899), (.310, .896), (.349, .896), (.362, .913),
                   (.367, .943), 'garten_wiese']),
    ('Wiesenstraße', ['garten_wiese', (.330, .957), (.287, .956)]),
]

# Klasse je Straßenname, abgelesen an Breite und Zeichnung auf der Karte. Namen auf -weg sind Feld- und
# Schotterwege, außer sie sind auf der Karte als Wohnstraße mit Häusern gezeichnet (Nelkenweg, Tannenweg …).
STREET_CLASS = {
    'Hauptstraße': 'haupt', 'Kreuzbergstraße': 'haupt', 'Schulstraße': 'haupt', 'Waldstraße': 'haupt',
    'Jägerstraße West': 'haupt', 'Robin-Hof-Straße': 'haupt', 'Werkstraße': 'haupt', 'Bürgerstraße': 'haupt',
    'Sportplatzring': 'neben', 'Kirchstraße': 'neben', 'Mathias-Berg-Straße': 'neben', 'Ahornallee': 'neben',
    'Erlenstraße': 'neben', 'Uferstraße': 'neben', 'Dorfstraße': 'neben', 'Jägerstraße Ost': 'neben',
    'Eichenstraße': 'neben', 'Flurstraße': 'neben', 'Scheunenweg': 'neben', 'Querstraße': 'neben',
    'Am Rathauspark': 'neben', 'Bachstraße': 'neben', 'Tannenfeld': 'neben', 'Östliche Randstraße': 'neben',
    'Zufahrt Kreisel': 'neben', 'Gewerbepark': 'neben', 'Am Marktplatz': 'neben', 'Zufahrt FW West': 'neben',
    'Blütenstraße': 'wohn', 'Tannenweg': 'wohn', 'Nelkenweg': 'wohn', 'Buchenstraße': 'wohn', 'Mozartweg': 'wohn',
    'Sonnenstraße': 'wohn', 'Rosengasse': 'wohn', 'Gasse': 'wohn', 'Dorfblick': 'wohn', 'Marktplatz': 'wohn',
    'Querweg Ahornallee': 'wohn', 'Wiesenstraße': 'wohn', 'Gartenweg': 'wohn',
    'Forstweg': 'weg', 'Feldweg': 'weg', 'Bummelbachweg': 'weg', 'Mühlenweg': 'weg', 'Hofzufahrt': 'weg',
}

# Mittellinie des Bummelsbachs, von der Karte abgelesen (Prüfung in tests/test_strassennetz.py): Straßen
# dürfen ihn nur auf einer Brücke queren. Die einzige Brücke ist die der Bürgerstraße (Brückenstraße).
BUMMELSBACH = [
    (.203, .574), (.210, .586), (.218, .605), (.225, .645), (.229, .664), (.234, .684), (.244, .703), (.255, .723),
    (.266, .742), (.279, .762), (.291, .781), (.306, .801), (.322, .820), (.340, .835), (.365, .851), (.391, .859),
    (.417, .864), (.443, .866), (.469, .863), (.495, .859), (.521, .855), (.547, .854), (.573, .850), (.599, .851),
    (.628, .857), (.651, .866), (.677, .876), (.703, .891), (.729, .907), (.755, .918), (.781, .929), (.807, .945),
]
BRIDGES = [(.629, .858)]


def _point(p):
    return JUNCTIONS[p] if isinstance(p, str) else p


def distance(a, b):
    return (((a[0] - b[0]) * ASPECT) ** 2 + (a[1] - b[1]) ** 2) ** .5


def _build():
    nodes = []
    index = {}
    edges = {}
    rank = {c: i for i, c in enumerate(CLASSES)}
    for name, points in STREETS:
        road = STREET_CLASS[name]
        ids = []
        for p in points:
            xy = tuple(_point(p))
            if xy not in index:
                index[xy] = len(nodes)
                nodes.append(xy)
            ids.append(index[xy])
        for a, b in pairwise(ids):
            if a != b:
                key = (min(a, b), max(a, b))
                # Gehört ein Stück zu zwei Straßen, zählt die schnellere Klasse.
                if key not in edges or rank[road] < rank[edges[key]]:
                    edges[key] = road
    neighbours = {i: [] for i in range(len(nodes))}
    for (a, b), road in edges.items():
        length = distance(nodes[a], nodes[b])
        neighbours[a].append((b, length, road))
        neighbours[b].append((a, length, road))
    return nodes, sorted(edges), edges, neighbours


NODES, EDGES, EDGE_CLASS, NEIGHBOURS = _build()


def _project(p):
    """Nächster Punkt auf dem Straßennetz: (Abstand, Kante, Punkt auf der Kante)."""
    best = None
    for a, b in EDGES:
        ax, ay = NODES[a]
        bx, by = NODES[b]
        dx, dy = (bx - ax) * ASPECT, by - ay
        length2 = dx * dx + dy * dy
        t = 0 if not length2 else max(0, min(1, ((p[0] - ax) * ASPECT * dx + (p[1] - ay) * dy) / length2))
        q = (ax + (bx - ax) * t, ay + (by - ay) * t)
        d = distance(p, q)
        if best is None or d < best[0]:
            best = (d, (a, b), q)
    return best


def _seconds(a, b, road, speeds):
    return distance(a, b) * METERS_PER_UNIT / speeds[road]


def _dijkstra(sources, speeds):
    """sources: {Knoten: Startzeit}. Liefert Fahrzeiten und Vorgänger."""
    dist = dict(sources)
    prev = {}
    queue = [(d, n) for n, d in sources.items()]
    heapq.heapify(queue)
    while queue:
        d, n = heapq.heappop(queue)
        if d > dist.get(n, float('inf')):
            continue
        for m, length, road in NEIGHBOURS[n]:
            nd = d + length * METERS_PER_UNIT / speeds[road]
            if nd < dist.get(m, float('inf')):
                dist[m] = nd
                prev[m] = n
                heapq.heappush(queue, (nd, m))
    return dist, prev


@lru_cache(maxsize=4096)
def _plan(start, target, speed_key):
    speeds = dict(zip(CLASSES, speed_key, strict=True))
    _, (sa, sb), s_dock = _project(start)
    _, (ta, tb), t_dock = _project(target)
    s_road, t_road = EDGE_CLASS[(sa, sb)], EDGE_CLASS[(ta, tb)]
    # Punkte jeweils mit der Klasse des Stücks, das zu ihnen hinführt.
    legs = [(start, DOCK_CLASS), (s_dock, DOCK_CLASS)]
    if {sa, sb} == {ta, tb}:
        legs.append((t_dock, s_road))
    else:
        dist, prev = _dijkstra({n: _seconds(s_dock, NODES[n], s_road, speeds) for n in (sa, sb)}, speeds)
        end = min((ta, tb), key=lambda n: dist.get(n, float('inf')) + _seconds(NODES[n], t_dock, t_road, speeds))
        middle = [end]
        while middle[-1] in prev:
            middle.append(prev[middle[-1]])
        middle.reverse()
        legs.append((NODES[middle[0]], s_road))
        legs += [(NODES[b], EDGE_CLASS[(min(a, b), max(a, b))]) for a, b in pairwise(middle)]
        legs.append((t_dock, t_road))
    legs.append((target, DOCK_CLASS))
    points, times = [], []
    for p, road in legs:
        p = (round(p[0], 4), round(p[1], 4))
        if not points:
            points.append(p)
            times.append(0.0)
        elif distance(points[-1], p) > 1e-4:
            times.append(times[-1] + _seconds(points[-1], p, road, speeds))
            points.append(p)
    if len(points) == 1:
        points.append(points[0])
        times.append(0.0)
    return tuple(points), tuple(round(t, 2) for t in times)


def plan(start, target, speeds=None):
    """Schnellster Weg über das Straßennetz: (Punkte [[x, y], …], Sekunden ab Abfahrt je Punkt).

    speeds: Meter pro Sekunde je Straßenklasse (Standard SPEED). Start und Ziel werden über den
    nächsten Punkt auf einer Straße angebunden (Hofeinfahrt)."""
    speeds = SPEED if speeds is None else speeds
    points, times = _plan(tuple(start), tuple(target), tuple(float(speeds[c]) for c in CLASSES))
    return [list(p) for p in points], list(times)


def route(start, target, speeds=None):
    """Schnellster Weg als Punktliste [[x, y], …] von start bis target."""
    return plan(start, target, speeds)[0]


def at_time(points, times, t):
    """Punkt zur Fahrzeit t (Sekunden ab phase_at) und die bis dahin gefahrene Teilstrecke.

    times[i] ist der Zeitpunkt, an dem points[i] erreicht wird. Dazwischen geht es gleichmäßig voran,
    auf langsamen Abschnitten also sichtbar langsamer."""
    walked = [list(points[0])]
    if t <= times[0]:
        return list(points[0]), walked
    for i in range(1, len(points)):
        a, b = points[i - 1], points[i]
        if t < times[i]:
            span = times[i] - times[i - 1]
            share = (t - times[i - 1]) / span if span > 0 else 1
            here = [a[0] + (b[0] - a[0]) * share, a[1] + (b[1] - a[1]) * share]
            walked.append(here)
            return here, walked
        walked.append(list(b))
    return list(points[-1]), walked


def length(points):
    return sum(distance(a, b) for a, b in pairwise(points))


def along(points, share):
    """Punkt nach dem Anteil share (0–1) der Gesamtlänge und die Teilstrecke bis dorthin."""
    total = length(points)
    if total <= 0 or share <= 0:
        return list(points[0]), [list(points[0])]
    remaining = min(1, share) * total
    walked = [list(points[0])]
    for a, b in pairwise(points):
        step = distance(a, b)
        if step >= remaining:
            t = remaining / step if step else 1
            here = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
            walked.append(here)
            return here, walked
        remaining -= step
        walked.append(list(b))
    return list(points[-1]), walked
