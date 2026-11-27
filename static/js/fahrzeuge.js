'use strict';
// Mini-Fahrzeuge auf der Einsatzkarte: nur das Aussehen der Fahrzeugmarker.
// Grafik je Typ (Seitenansichten: LF/HLF lf20.webp, KdoW kdow-seite.svg; über css/fahrzeuge.css), Namensschild,
// Drehung in Fahrtrichtung und Versatz, wenn mehrere Fahrzeuge an derselben Stelle stehen.
// Position (left/top in %) und Klick-Verhalten kommen aus game.js.
const WBFahrzeuge = (() => {
  const escape = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const PHASES = {anfahrt: 'Anfahrt', vorort: 'an der Einsatzstelle', rueckfahrt: 'Rückfahrt'};
  const TYPES = {HLF: 'hlf', LF: 'lf', KdoW: 'kdow'};
  // Ab dieser Strecke (px) wird die Fahrtrichtung neu aus der Bewegung bestimmt.
  const STEP = 2;
  const seen = new Map();

  const type = v => TYPES[String(v.kind || '').split(' ')[0]] || 'lf';
  // Kurzbezeichnung fürs Namensschild, z. B. „1-HLF“.
  const label = v => `${v.unit}-${String(v.kind || '').split(' ')[0]}`;
  const describe = v => `${v.call} – ${PHASES[v.phase] || v.phase}${v.status ? ` (Status ${v.status})` : ''}`;
  const classes = v => `veh veh-${type(v)} veh-${v.phase}${v.phase === 'anfahrt' ? ' blaulicht' : ''}`;

  // Richtung Start → Ziel (in Kartenanteilen), solange noch keine Bewegung beobachtet wurde.
  function direction(v) {
    // Mit Straßenroute (phase_route, feature/strassen-routen): erster Abschnitt der Fahrt.
    const route = Array.isArray(v.phase_route) && v.phase_route.length > 1 && v.phase !== 'vorort' ? v.phase_route : null;
    if (route) return `${route[1][0] - route[0][0]} ${route[1][1] - route[0][1]}`;
    const from = v.phase === 'vorort' ? v.base : (v.phase_from || v.base);
    const to = v.phase_to || from;
    if (!from || !to) return '';
    return `${to[0] - from[0]} ${to[1] - from[1]}`;
  }

  function inner(v) {
    return `<span class="veh-body" aria-hidden="true"><span class="veh-light"></span></span><span class="veh-label" aria-hidden="true">${escape(label(v))}</span>`;
  }

  // Kompletter Marker als <span>; game.js setzt die Position (left/top in %).
  function marker(v, pos) {
    const text = escape(describe(v));
    return `<span class="pin vehicle ${classes(v)}" data-vehicle-pin="${escape(v.id)}" data-dir="${direction(v)}" role="img" aria-label="${text}" title="${text}" style="left:${pos[0] * 100}%;top:${pos[1] * 100}%">${inner(v)}</span>`;
  }

  function heading(el, x, y, W, H) {
    const id = el.dataset.vehiclePin;
    const phase = el.classList.contains('veh-anfahrt') ? 'anfahrt' : el.classList.contains('veh-rueckfahrt') ? 'rueckfahrt' : 'vorort';
    const last = seen.get(id);
    // Gleiche Fahrt (oder gerade angekommen): Richtung aus der beobachteten Bewegung, folgt also auch Straßenwegen.
    if (last && (last.phase === phase || phase === 'vorort')) {
      const dx = (x - last.x) * W, dy = (y - last.y) * H;
      if (Math.hypot(dx, dy) < STEP) {
        last.phase = phase;
        return last.angle;
      }
      const angle = Math.atan2(dy, dx);
      seen.set(id, {x, y, angle, phase});
      return angle;
    }
    // Neue Fahrt oder erstes Bild: Richtung Start → Ziel.
    const [dx, dy] = (el.dataset.dir || '').split(' ').map(Number);
    const angle = Number.isFinite(dx) && Number.isFinite(dy) && Math.hypot(dx * W, dy * H) > 1
      ? Math.atan2(dy * H, dx * W) : (last ? last.angle : 0);
    seen.set(id, {x, y, angle, phase});
    return angle;
  }

  // Nach jedem Neuzeichnen und in jedem Animationsschritt aufrufen.
  function layout(container) {
    if (!container) return;
    const W = container.clientWidth, H = container.clientHeight;
    if (!W || !H) return;
    const items = Array.from(container.querySelectorAll('.veh[data-vehicle-pin]'), el => {
      const x = parseFloat(el.style.left) / 100, y = parseFloat(el.style.top) / 100;
      let angle = heading(el, x, y, W, H);
      // An der Einsatzstelle stehen die Fahrzeuge waagerecht (ordentliches Raster, Schilder überdecken sich nicht).
      if (el.classList.contains('veh-vorort')) angle = Math.cos(angle) >= 0 ? 0 : Math.PI;
      return {el, id: el.dataset.vehiclePin, x, y, angle};
    }).sort((a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
    // Fahrzeuge, deren Schilder sich berühren würden, zu Gruppen zusammenfassen (auch über Ketten hinweg).
    const small = window.matchMedia('(max-width: 600px)').matches;
    const slotX = small ? 48 : 58, slotY = small ? 28 : 34;
    const groups = [];
    for (const item of items) {
      const near = groups.filter(g => g.some(o => Math.abs(o.x - item.x) * W < slotX && Math.abs(o.y - item.y) * H < slotY));
      const merged = near.flat().concat(item);
      for (const g of near) groups.splice(groups.indexOf(g), 1);
      groups.push(merged);
    }
    for (const group of groups) {
      group.sort((a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
      // Raster um den gemeinsamen Mittelpunkt; an der Einsatzstelle unterhalb des „!“, damit es frei bleibt.
      const site = group.find(item => item.el.classList.contains('veh-vorort'));
      const ax = site ? site.x : group.reduce((sum, item) => sum + item.x, 0) / group.length;
      const ay = site ? site.y : group.reduce((sum, item) => sum + item.y, 0) / group.length;
      const cols = group.length === 1 ? 1 : group.length <= 4 ? 2 : 3;
      const rows = Math.ceil(group.length / cols);
      const placed = group.map((item, i) => {
        const col = i % cols - (cols - 1) / 2;
        const row = Math.floor(i / cols) + (site ? 0.7 : -(rows - 1) / 2);
        const ox = group.length === 1 && !site ? 0 : (ax - item.x) * W + col * slotX;
        const oy = group.length === 1 && !site ? 0 : (ay - item.y) * H + row * slotY;
        return {item, ox, oy, px: item.x * W + ox, py: item.y * H + oy};
      });
      // Ganze Gruppe in die Karte schieben, damit am Rand nichts abgeschnitten wird (Schild hängt unten dran).
      const left = Math.min(...placed.map(p => p.px)) - slotX / 2, right = Math.max(...placed.map(p => p.px)) + slotX / 2;
      const top = Math.min(...placed.map(p => p.py)) - slotY / 2, bottom = Math.max(...placed.map(p => p.py)) + slotY;
      const shiftX = left < 0 ? -left : right > W ? W - right : 0;
      const shiftY = top < 0 ? -top : bottom > H ? H - bottom : 0;
      for (const {item, ox, oy} of placed) {
        const s = item.el.style;
        s.setProperty('--hd', `${(item.angle * 180 / Math.PI).toFixed(1)}deg`);
        s.setProperty('--rs', Math.abs(Math.sin(item.angle)).toFixed(3));
        s.setProperty('--rc', Math.abs(Math.cos(item.angle)).toFixed(3));
        // Die Seitenansichten zeigen nach links: bei Fahrt nach rechts spiegeln statt drehen.
        s.setProperty('--fx', Math.cos(item.angle) > 0.001 ? '-1' : '1');
        s.setProperty('--ox', `${(ox + shiftX).toFixed(1)}px`);
        s.setProperty('--oy', `${(oy + shiftY).toFixed(1)}px`);
      }
    }
  }

  return {type, label, describe, classes, direction, inner, marker, layout};
})();
