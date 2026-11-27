"""Fahrzeit nach Entfernung und Straßenklasse (game/strassen.py, game/engine.py)."""
import json

import pytest

from game import engine, strassen

NOW = 1_000_000.0


@pytest.fixture
def room():
    r = engine.new_room('WB')
    r['weather_mode'] = 'manual'
    return r


def mid(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def meters_per_second(a, b, speeds=None):
    """Tempo auf der Strecke a → b, wenn beide Punkte auf derselben Straße liegen."""
    points, times = strassen.plan(a, b, speeds)
    return strassen.length(points) * strassen.METERS_PER_UNIT / times[-1]


def test_every_street_has_a_class():
    assert {name for name, _ in strassen.STREETS} == set(strassen.STREET_CLASS)
    assert set(strassen.STREET_CLASS.values()) == set(strassen.CLASSES)
    assert strassen.STREET_CLASS['Forstweg'] == strassen.STREET_CLASS['Feldweg'] == 'weg'
    assert strassen.STREET_CLASS['Bummelbachweg'] == 'weg'
    assert strassen.STREET_CLASS['Hauptstraße'] == 'haupt'


def test_map_scale():
    """Maßstabsleiste: 500 m sind 231 Pixel, die Karte ist 1536 Pixel breit, also gut 3,3 km."""
    assert strassen.distance((0, 0), (1, 0)) * strassen.METERS_PER_UNIT == pytest.approx(3325, abs=5)


def test_main_road_is_faster_than_dirt_track():
    a, b = (.343, .515), (.408, .513)  # Hauptstraße zwischen FW West und Gasse
    c, d = (.733, .105), (.765, .095)  # Feldweg nördlich des Scheunenwegs
    on_main = meters_per_second(mid(a, b, .2), mid(a, b, .8))
    on_track = meters_per_second(mid(c, d, .2), mid(c, d, .8))
    assert on_main == pytest.approx(strassen.SPEED['haupt'], rel=.01)
    assert on_track == pytest.approx(strassen.SPEED['weg'], rel=.01)
    assert on_main > 2 * on_track


def test_travel_time_grows_with_distance(room):
    v = room['vehicles']['WB-2-HLF20']  # FW Altstadt
    places = ('Hauptstraße', 'Kirchstraße', 'Werkstraße')
    near, middle, far = (engine.eta(room, v, engine.locate(name)) for name in places)
    assert engine.DEPARTURE_TIME < near < middle < far


def test_travel_times_are_playable(room):
    """Kurze Fahrt im Ort ~8–12 s, quer über die Karte ~25–35 s."""
    short = engine.eta(room, room['vehicles']['WB-2-HLF20'], engine.locate('Kirchstraße'))
    across = engine.eta(room, room['vehicles']['WB-6-HLF20'], engine.locate('Werkstraße'))
    assert 6 <= short <= 12
    assert 25 <= across <= 35


def real_time(points):
    """Fahrzeit einer festen Punktfolge mit den Standard-Geschwindigkeiten, jedes Stück nach seiner Straße."""
    total = 0
    for i, (a, b) in enumerate(zip(points, points[1:], strict=False)):
        edge = strassen._project(mid(a, b, .5))[1]
        road = strassen.DOCK_CLASS if i in (0, len(points) - 2) else strassen.EDGE_CLASS[edge]
        total += strassen.distance(a, b) * strassen.METERS_PER_UNIT / strassen.SPEED[road]
    return total


def test_fastest_route_takes_detour_over_main_road():
    """Von FW Ost zum Am Rathauspark: Der schnellste Weg ist länger als der kürzeste, aber schneller."""
    start, target = engine.BASE[4], engine.locate('Am Rathauspark')
    equal = {road: 100 for road in strassen.CLASSES}  # alle Straßen gleich schnell = kürzester Weg
    shortest = strassen.route(start, target, equal)
    fastest, times = strassen.plan(start, target)
    assert strassen.length(fastest) > strassen.length(shortest) * 1.1
    assert times[-1] == pytest.approx(real_time(fastest), rel=.01)
    assert times[-1] < real_time(shortest)


def test_weather_slows_down_and_mud_slows_tracks_even_more(room):
    v = room['vehicles']['WB-3-HLF20']  # FW Nord
    target = engine.locate('Feldweg')
    town = engine.locate('Flurstraße')
    sunny = engine.eta(room, v, town) - engine.DEPARTURE_TIME
    sunny_track = strassen.plan(v['base'], target, engine.drive_speeds(room, v))[1][-1]
    room['weather'] = 'Regen'
    rainy = engine.eta(room, v, town) - engine.DEPARTURE_TIME
    rainy_track = strassen.plan(v['base'], target, engine.drive_speeds(room, v))[1][-1]
    assert rainy == pytest.approx(sunny * engine.WEATHER_SLOWDOWN['Regen'], rel=.02)
    assert rainy_track > sunny_track * engine.WEATHER_SLOWDOWN['Regen'] * 1.1  # Feldweg matschig
    room['weather'] = 'Nebel'
    assert engine.eta(room, v, town) - engine.DEPARTURE_TIME > rainy


def test_command_car_is_a_bit_faster(room):
    target = engine.locate('Werkstraße')
    hlf = engine.eta(room, room['vehicles']['WB-1-HLF20'], target)
    kdow = engine.eta(room, room['vehicles']['WB-1-KdoW'], target)
    assert kdow < hlf < kdow * 1.25


def test_vehicle_is_slower_on_the_track(room):
    """Auf dem Feldweg braucht das Fahrzeug je Meter sichtbar länger als auf der Hauptstraße."""
    v = room['vehicles']['WB-3-HLF20']
    route, times = engine.plan_trip(room, v, v['base'], engine.locate('Feldweg'))
    steps = [(strassen.distance(a, b) / (t2 - t1), strassen._project(mid(a, b, .5))[1])
             for a, b, t1, t2 in zip(route, route[1:], times, times[1:], strict=False) if t2 > t1]
    track = [pace for pace, edge in steps if strassen.EDGE_CLASS[edge] == 'weg']
    fast = [pace for pace, edge in steps if strassen.EDGE_CLASS[edge] in ('haupt', 'neben')]
    assert track and fast
    assert max(track) < min(fast)


def test_alarm_fixes_route_and_timetable(room):
    ls = engine.handle(room, {'action': 'join'}, 1, 'Anna', False, NOW)['id']
    engine.handle(room, {'action': 'take_ls', 'id': ls}, 1, 'Anna', False, NOW)
    engine.handle(room, {'action': 'incident', 'id': ls, 'title': 'F1 · Kleinbrand', 'address': 'Werkstraße 3'},
                  1, 'Anna', False, NOW)
    inc = room['incidents'][-1]
    snap = engine.snapshot(room, NOW)['incidents'][-1]
    v = room['vehicles']['WB-4-HLF20']
    assert snap['eta']['WB-4-HLF20'] == round(engine.eta(room, v, inc['pos']))
    engine.handle(room, {'action': 'dispatch', 'id': ls, 'incident': inc['id'], 'vehicle': v['id']},
                  1, 'Anna', False, NOW)
    assert v['phase_times'][0] == engine.DEPARTURE_TIME
    assert v['phase_until'] - NOW == pytest.approx(v['phase_times'][-1])
    assert abs(v['phase_until'] - NOW - snap['eta'][v['id']]) <= .5
    assert 'WB-4-HLF20' not in engine.snapshot(room, NOW)['incidents'][-1]['eta']  # nicht mehr frei
    # Während der Ausrückzeit steht das Fahrzeug noch an der Wache.
    assert engine.vehicle_position(v, NOW + engine.DEPARTURE_TIME - .1) == list(v['base'])
    # Kein Sprung bei der Ankunft: kurz davor fast am Ziel, danach genau dort, Status 4.
    before = engine.vehicle_position(v, v['phase_until'] - .05)
    assert strassen.distance(before, inc['pos']) < .01
    engine.update(room, v['phase_until'] - .01)
    assert v['phase'] == 'anfahrt'
    engine.update(room, v['phase_until'])
    assert v['phase'] == 'vorort' and v['status'] == 4 and 'phase_times' not in v
    assert engine.vehicle_position(v, NOW + 999) == inc['pos']


def test_timetable_is_json_serializable(room):
    v = room['vehicles']['WB-1-HLF20']
    inc = engine.new_incident('F1', 'Marktplatz', engine.locate('Marktplatz'), 'Anna', NOW)
    room['incidents'].append(inc)
    engine.alarm(room, inc, v, NOW)
    copy = json.loads(json.dumps(v))
    assert copy['phase_times'] == v['phase_times'] and copy['phase_route'] == v['phase_route']
    for t in (NOW + 1, NOW + 5, NOW + 9):
        assert engine.vehicle_position(copy, t) == pytest.approx(engine.vehicle_position(v, t))


def test_speeds_come_from_settings(settings):
    assert strassen.SPEED == settings.DRIVE_SPEED
    assert engine.DEPARTURE_TIME == settings.DRIVE_DEPARTURE_TIME


def test_player_vehicle_has_no_extra_departure_time(room):
    """Spielerfahrzeuge rücken mit Status 3 des GF aus; die Ausrückzeit zählt nur für KI-Besatzungen."""
    v = room['vehicles']['WB-2-HLF20']
    target = engine.locate('Werkstraße')
    crewless = engine.eta(room, v, target)
    v['owner'] = 'spieler'
    assert engine.departure_time(v) == 0
    assert engine.eta(room, v, target) == pytest.approx(crewless - engine.DEPARTURE_TIME)
