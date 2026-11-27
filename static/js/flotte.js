'use strict';
// Echte Flotte der FF Westbummeln im Frontend (Daten aus game/flotte.py, mit der Seite ausgeliefert):
// - feste Fahrzeugdaten zwischenspeichern; der Server schickt sie nur, wenn sie sich geändert haben (fleet_rev),
// - eigene Standort-Schilder (Löschzug + Fachgebiet) über den anders beschrifteten gedruckten Kartenlabels,
// - Fahrzeugliste nach Einheit gruppiert, zum Auf- und Zuklappen.
const WBFlotte = (() => {
  const escape = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const DATA = JSON.parse(document.getElementById('flotte-daten')?.textContent || '{"einheiten":[],"freie_wachen":[]}');
  const UNITS = new Map(DATA.einheiten.map(e => [e.id, e]));
  const STATIC = ['call', 'unit', 'kind', 'kategorie', 'grafik', 'seats', 'base'];
  // Felder, die der Server weglässt, wenn sie leer sind.
  const EMPTY = {owner: null, incident: null, towing: null, towed_by: null};
  const OPEN_KEY = 'wb.fahrzeuggruppen.offen';
  let fixed = new Map();
  let fleetRev = null;
  let open = new Set();
  try { open = new Set(JSON.parse(localStorage.getItem(OPEN_KEY) || '[]')); } catch { /* ohne Speicher alles zu */ }

  // Snapshot vom Server → vollständige Fahrzeuge (feste + veränderliche Felder), wie sie der Rest des Frontends kennt.
  function merge(next) {
    if (!next || !Array.isArray(next.vehicles)) return next;
    if (next.fleet_full) {
      fixed = new Map(next.vehicles.map(v => [v.id, Object.fromEntries(STATIC.filter(k => k in v).map(k => [k, v[k]]))]));
    }
    let complete = true;
    next.vehicles = next.vehicles.map(v => {
      const base = fixed.get(v.id);
      if (!base) complete = false;
      return {...EMPTY, ...base, ...v};
    });
    // Fehlt etwas (z. B. nach einem Raumwechsel), beim nächsten Abruf alles neu anfordern.
    fleetRev = complete ? next.fleet_rev : null;
    return next;
  }

  const unitName = id => UNITS.get(id)?.name || String(id ?? '');
  const isKfz = v => (v.kategorie || 'kfz') === 'kfz';
  const short = v => String(v.call || '').replace(/^Florian Westbummeln /, '');

  // Standort-Schilder über die gedruckten Labels legen (einmal beim Laden).
  function drawBadges() {
    const map = document.getElementById('map');
    if (!map || document.getElementById('stationBadges')) return;
    const layer = document.createElement('div');
    layer.id = 'stationBadges';
    layer.setAttribute('aria-hidden', 'true');
    const ftz = UNITS.get('FTZ');
    const badges = DATA.einheiten.filter(e => e.schild).map(e => {
      const extra = ftz && e.id !== 'FTZ' && String(ftz.pos) === String(e.pos) ? `<span class="badge-extra">+ ${escape(ftz.name)}</span>` : '';
      return `<div class="station-badge" style="left:${e.schild[0] * 100}%;top:${e.schild[1] * 100}%"><b>${escape(e.name)}</b><span>${escape(e.fachgebiet || '')}</span>${extra}</div>`;
    });
    for (const w of DATA.freie_wachen) {
      badges.push(`<div class="station-badge free" style="left:${w.schild[0] * 100}%;top:${w.schild[1] * 100}%"><b>${escape(w.name)}</b><span>ohne Einheit</span></div>`);
    }
    // Legende „Löschzüge (Standorte)“ der gedruckten Karte durch die gültige Zuordnung ersetzen.
    const rows = DATA.einheiten.filter(e => e.id.startsWith('LZ') || e.id === 'FTZ')
      .map(e => `<li><b>${escape(e.id === 'FTZ' ? 'FTZ' : e.id.replace('LZ', 'LZ '))}</b> ${escape(e.name.replace(/^LZ \d /, ''))}${e.fachgebiet ? ` · ${escape(e.fachgebiet)}` : ''}</li>`).join('');
    badges.push(`<div class="station-legend"><b>Löschzüge (Standorte)</b><ul>${rows}</ul></div>`);
    layer.innerHTML = badges.join('');
    map.insertBefore(layer, document.getElementById('markers'));
  }

  function fillFilter(select) {
    if (!select || select.dataset.filled) return;
    select.dataset.filled = '1';
    select.innerHTML = '<option value="all">Alle Einheiten</option>' + DATA.einheiten
      .map(e => `<option value="${escape(e.id)}">${escape(e.name)}${e.fachgebiet ? ' · ' + escape(e.fachgebiet) : ''}</option>`).join('');
  }

  function saveOpen() {
    try { localStorage.setItem(OPEN_KEY, JSON.stringify([...open])); } catch { /* nur bis zum Neuladen */ }
  }

  function setOpen(unit, value) {
    if (value) open.add(unit); else open.delete(unit);
    saveOpen();
  }

  // Fahrzeugliste: eine Gruppe je Einheit. Bei Suche oder Einheitenfilter sind die passenden Gruppen offen.
  // item(v) liefert das bisherige Listenelement eines Fahrzeugs (game.js).
  function listMarkup(vehicles, {query, unit, item, flash}) {
    const q = query.trim().toLowerCase();
    const groups = new Map();
    for (const v of vehicles) {
      if (unit !== 'all' && String(v.unit) !== unit) continue;
      if (q && !`${v.call} ${v.kind} ${unitName(v.unit)}`.toLowerCase().includes(q)) continue;
      if (!groups.has(v.unit)) groups.set(v.unit, []);
      groups.get(v.unit).push(v);
    }
    if (!groups.size) return '<p class="small">Kein Fahrzeug gefunden.</p>';
    return [...groups].map(([id, list]) => {
      const expanded = Boolean(q) || unit !== 'all' || open.has(String(id)) || list.some(v => v.id === flash);
      const info = UNITS.get(id);
      const free = list.filter(v => isKfz(v) && v.phase === 'wache' && v.status !== 6).length;
      const kfz = list.filter(isKfz).length;
      return `<div class="vehicle-group" data-unit="${escape(id)}"><button type="button" class="group-head" data-group="${escape(id)}" aria-expanded="${expanded}">`
        + `<span class="arrow" aria-hidden="true">▸</span><b>${escape(unitName(id))}</b>`
        + `<span class="small">${escape(info?.fachgebiet || '')}</span><span class="group-count small">${free}/${kfz} frei</span></button>`
        + (expanded ? `<div class="group-body">${list.map(item).join('')}</div>` : '') + '</div>';
    }).join('');
  }

  // Klicks auf Gruppenköpfe (einmal einrichten; die Liste wird bei jedem render() neu geschrieben).
  function bindList(container, rerender) {
    container.addEventListener('click', event => {
      const head = event.target.closest('[data-group]');
      if (!head) return;
      setOpen(head.dataset.group, head.getAttribute('aria-expanded') !== 'true');
      rerender();
      container.querySelector(`[data-group="${CSS.escape(head.dataset.group)}"]`)?.focus();
    });
  }

  return {
    merge, rev: () => fleetRev, unitName, isKfz, short, drawBadges, fillFilter, listMarkup, bindList,
    openGroup: unit => setOpen(String(unit), true),
  };
})();
