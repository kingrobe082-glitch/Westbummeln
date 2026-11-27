"""Das Straßennetz folgt der Karte: keine Abkürzungen durch den Bummelsbach (Lars: „fährt bei GH4 über den Bach“)."""
from itertools import pairwise, product

from game import engine, strassen


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def crossing(p, q, r, s):
    """Schneiden sich die Strecken p–q und r–s?"""
    d1, d2 = _cross(r, s, p), _cross(r, s, q)
    d3, d4 = _cross(p, q, r), _cross(p, q, s)
    return d1 * d2 < 0 and d3 * d4 < 0


def river_crossings(a, b):
    """Stellen, an denen die Strecke a–b den Bach quert (Mitte des geschnittenen Bachstücks)."""
    return [((r[0] + s[0]) / 2, (r[1] + s[1]) / 2)
            for r, s in pairwise(strassen.BUMMELSBACH) if crossing(a, b, r, s)]


def on_bridge(point):
    return any(strassen.distance(point, bridge) < .02 for bridge in strassen.BRIDGES)


def distance_to_river(p):
    best = 1
    for a, b in pairwise(strassen.BUMMELSBACH):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
        best = min(best, strassen.distance(p, (a[0] + dx * t, a[1] + dy * t)))
    return best


def test_streets_cross_the_river_only_on_bridges():
    wrong = []
    for a, b in strassen.EDGES:
        for point in river_crossings(strassen.NODES[a], strassen.NODES[b]):
            if not on_bridge(point):
                wrong.append((strassen.NODES[a], strassen.NODES[b]))
    assert not wrong


def test_the_bridge_is_used():
    """Die Brücke der Bürgerstraße ist eine echte Querung, sonst prüfte der Test oben nichts."""
    assert any(river_crossings(strassen.NODES[a], strassen.NODES[b]) for a, b in strassen.EDGES)


def test_no_route_leaves_the_streets_over_the_river():
    """Auch die Anbindung von Wache und Einsatzort (Hofeinfahrt) führt nicht durchs Wasser."""
    for base, (name, x, y) in product(engine.BASE.values(), engine.PLACES):
        route = strassen.route(base, (x, y))
        for a, b in pairwise(route):
            assert all(on_bridge(p) for p in river_crossings(a, b)), (name, a, b)


def test_no_place_lies_in_the_river():
    for name, x, y in engine.PLACES:
        assert distance_to_river((x, y)) > .015, name


def test_south_west_is_reached_over_the_bridge():
    """Mühlenweg und Gartenweg liegen südlich des Bachs: Von FW West geht es über die Bürgerstraße."""
    route = strassen.route(engine.BASE[1], engine.locate('Gartenweg'))
    assert any(on_bridge(p) for a, b in pairwise(route) for p in river_crossings(a, b))
    assert list(strassen.JUNCTIONS['buerger_bach']) in route
