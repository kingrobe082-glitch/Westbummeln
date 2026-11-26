"""Straßennetz der Einsatzkarte und kürzeste Wege darauf.

Koordinaten wie überall im Spiel: Anteile (0–1) der vollständigen Karte static/karte.webp
(1536 × 1024 Pixel, inklusive Legende). Die Straßen wurden von der Karte abgelesen; jede Straße ist
eine Punktfolge, gemeinsame Kreuzungen stehen in JUNCTIONS und werden über ihren Namen verbunden.

Für Abstände wird x mit dem Seitenverhältnis der Karte gestreckt, damit eine Strecke in x-Richtung
genauso lang zählt wie eine gleich lange Strecke in y-Richtung.
"""
import heapq
from functools import lru_cache
from itertools import pairwise

ASPECT = 1536 / 1024

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
    'mozart_o': (.937, .660),        # Mozartweg / Gewerbepark / Randstraße
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
    'ufer_muehle': (.362, .793),     # Uferstraße / Brücke zum Mühlenweg
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
    ('Mozartweg', ['mozart_w', (.856, .623), (.895, .637), 'mozart_o']),
    ('Gewerbepark', ['mozart_o', (.900, .670), (.865, .689), (.824, .712), (.781, .738), 'werk_gewerbe']),
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
    ('Bummelbachweg', [(.405, .957), (.414, .933), (.427, .913), (.460, .903), (.538, .884),
                       (.586, .882), 'buerger_bach']),
    ('Mühlenweg', ['ufer_muehle', (.335, .842), (.300, .840), (.278, .840), (.258, .855),
                   (.248, .884), 'muehle_garten']),
    ('Mühlenweg', ['muehle_garten', (.229, .938), (.216, .962)]),
    ('Gartenweg', ['muehle_garten', (.278, .899), (.310, .896), (.349, .896), (.362, .913),
                   (.367, .943), 'garten_wiese']),
    ('Wiesenstraße', ['garten_wiese', (.330, .957), (.287, .956)]),
]


def _point(p):
    return JUNCTIONS[p] if isinstance(p, str) else p


def distance(a, b):
    return (((a[0] - b[0]) * ASPECT) ** 2 + (a[1] - b[1]) ** 2) ** .5


def _build():
    nodes = []
    index = {}
    edges = set()
    for _, points in STREETS:
        ids = []
        for p in points:
            xy = tuple(_point(p))
            if xy not in index:
                index[xy] = len(nodes)
                nodes.append(xy)
            ids.append(index[xy])
        for a, b in pairwise(ids):
            if a != b:
                edges.add((min(a, b), max(a, b)))
    neighbours = {i: [] for i in range(len(nodes))}
    for a, b in edges:
        length = distance(nodes[a], nodes[b])
        neighbours[a].append((b, length))
        neighbours[b].append((a, length))
    return nodes, sorted(edges), neighbours


NODES, EDGES, NEIGHBOURS = _build()


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


def _dijkstra(sources):
    """sources: {Knoten: Startabstand}. Liefert Abstände und Vorgänger."""
    dist = dict(sources)
    prev = {}
    queue = [(d, n) for n, d in sources.items()]
    heapq.heapify(queue)
    while queue:
        d, n = heapq.heappop(queue)
        if d > dist.get(n, float('inf')):
            continue
        for m, length in NEIGHBOURS[n]:
            nd = d + length
            if nd < dist.get(m, float('inf')):
                dist[m] = nd
                prev[m] = n
                heapq.heappush(queue, (nd, m))
    return dist, prev


@lru_cache(maxsize=1024)
def _route(start, target):
    _, (sa, sb), s_dock = _project(start)
    _, (ta, tb), t_dock = _project(target)
    middle = []
    if {sa, sb} != {ta, tb}:
        dist, prev = _dijkstra({sa: distance(s_dock, NODES[sa]), sb: distance(s_dock, NODES[sb])})
        end = min((ta, tb), key=lambda n: dist.get(n, float('inf')) + distance(NODES[n], t_dock))
        if end in dist:
            n = end
            middle = [n]
            while n in prev:
                n = prev[n]
                middle.append(n)
            middle.reverse()
    points = [start, s_dock, *(NODES[n] for n in middle), t_dock, target]
    route = []
    for p in points:
        p = [round(p[0], 4), round(p[1], 4)]
        if not route or distance(route[-1], p) > 1e-4:
            route.append(p)
    if len(route) == 1:
        route.append(list(route[0]))
    return route


def route(start, target):
    """Kürzester Weg über das Straßennetz als Punktliste [[x, y], …] von start bis target.

    Start und Ziel werden über den nächsten Punkt auf einer Straße angebunden (Hofeinfahrt)."""
    return [list(p) for p in _route(tuple(start), tuple(target))]


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
