// Maßnahmen je Einsatz (game/massnahmen.py): GF-Panel „Meine Einsatzstelle“, Lage in der Einsatzliste,
// Einsatzbilanz. Der Server rechnet alles; hier wird nur angezeigt. Balken und Countdowns laufen über
// data-start/data-ende bzw. data-bis und einen kleinen Ticker, damit die Knöpfe nicht bei jeder Abfrage neu
// gebaut werden (sonst flackert es auf dem Handy und Klicks gehen verloren).
'use strict';

const sceneTrend = {steigt: '▲', sinkt: '▼', gleich: '▶', aus: ''};

function sceneBrand(mn) {
  const lage = mn.lage;
  if (lage.aus) return '🔥 Feuer aus';
  const wert = lage.brand === null ? `? ${lage.brand_grob}` : lage.brand;
  return `🔥 Brand ${wert} ${sceneTrend[lage.trend] || ''}`;
}

// Tank gehört zum Fahrzeug (v.tank in Litern, Größe je Typ in state.tank_voll); er leert sich beim Löschen
// ohne Wasserversorgung, der Hydrant füllt nach, auf der Wache ist er wieder voll.
function tankText(v) {
  const voll = state?.tank_voll?.[v.kind];
  if (!voll || typeof v.tank !== 'number') return 'kein Löschwassertank';
  return `${Math.round(v.tank)} / ${voll} l (${Math.round(v.tank / voll * 100)} %)`;
}

function sceneWasser(mn, vehicleId) {
  const own = vehicleId != null ? mn.lage.tank[vehicleId] : undefined;
  if (mn.lage.wasser) return '💧 Wasserversorgung steht' + (own && own.l < own.voll ? ` · Tank füllt auf ${own.l} l` : '');
  if (own) return `💧 Tank ${own.l} l · ${own.s} s`;
  const loeschend = Object.values(mn.lage.tank).filter(t => t.loescht);
  return loeschend.length ? `💧 Tank ${Math.min(...loeschend.map(t => t.s))} s` : '💧 keine Wasserversorgung';
}

function sceneTankBar(mn, vehicleId) {
  const own = mn.lage.tank[vehicleId];
  return own ? Math.round(own.l / own.voll * 100) : null;
}

function sceneAmpel(mn) {
  return `<span class="ampel" data-stufe="${mn.stufe}">${esc(mn.ampel)} ${esc(mn.ampel_text)}</span>`;
}

function sceneStichwort(mn) {
  return mn.stichwort !== mn.stichwort_start
    ? ` <span class="pill esk">⬆ war ${esc(mn.stichwort_start)}</span>` : '';
}

function sceneWarnings(mn) {
  return mn.warnungen.map(w => `<div class="mn-warn" role="alert">⚠️ ${esc(w.text)}${
    w.bis ? ` <span class="mono" data-bis="${w.bis}"></span>` : ''}</div>`).join('');
}

function sceneNachforderung(mn) {
  if (!mn.nachgefordert) return '';
  if (!mn.nachforderungen.length) return '<div class="mn-nach ok">✔ Nachforderung erfüllt</div>';
  return `<div class="mn-nach">🔴 Nachforderung: ${mn.nachforderungen.map(esc).join(', ')}</div>`;
}

// Kompakte Lage für alle in der Einsatzliste (game.js ruft das je Einsatz auf).
function incidentExtra(i) {
  if (i.closed) return i.bilanz ? bilanzCard(i) : '';
  const mn = i.massnahmen;
  if (!mn) return '';
  const pflicht = mn.massnahmen.filter(m => m.pflicht).length;
  return `<div class="mn-line">${sceneAmpel(mn)}${sceneStichwort(mn)}
    <span>${esc(sceneBrand(mn))}</span><span>${esc(sceneWasser(mn))}</span>
    <span>Maßnahmen ${mn.erledigt}/${mn.massnahmen.length} ✅${mn.variante ? ' · ' + esc(mn.variante) : ''}</span>
    ${pflicht && mn.pflicht_offen.length ? `<span class="small">offen: ${mn.pflicht_offen.map(esc).join(', ')}</span>` : ''}
  </div>${sceneWarnings(mn)}${sceneNachforderung(mn)}`;
}

function mmss(sekunden) {
  if (sekunden === null || sekunden === undefined) return '–';
  const s = Math.max(0, Math.round(sekunden));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

const stufenText = {0: '🟢 keine Eskalation', 1: '🟡 Lage verschärft', 2: '🟠 Stichworterhöhung', 3: '🔴 Schaden'};

function bilanzCard(i) {
  const b = i.bilanz, d = b.dauer;
  const sterne = b.abgebrochen ? 'abgebrochen' : '★'.repeat(b.sterne) + '☆'.repeat(3 - b.sterne) + ` ${b.punkte} Punkte`;
  const stichwort = b.stichwort + (b.stichwort_ende !== b.stichwort ? ' → ' + b.stichwort_ende : '');
  return `<details class="bilanz" data-bilanz="${esc(i.id)}"><summary>📋 Einsatzbilanz ${esc(stichwort)} · ${esc(sterne)}</summary>
    <dl>
      <dt>⏱ Notruf → Alarm</dt><dd>${mmss(d.alarm)}</dd>
      <dt>⏱ Alarm → Eintreffen</dt><dd>${mmss(d.anfahrt)}</dd>
      <dt>⏱ Eintreffen → Feuer aus</dt><dd>${mmss(d.loeschen)}</dd>
      <dt>⏱ Gesamt</dt><dd>${mmss(d.gesamt)}</dd>
      <dt>Höchste Stufe</dt><dd>${stufenText[b.stufe_max] || ''}</dd>
      <dt>💧 Wasser aus</dt><dd>${b.wasser_aus}×</dd>
      <dt>Lage</dt><dd>${esc(b.variante)}</dd>
    </dl>${b.tipp ? `<p class="small">💡 ${esc(b.tipp)}</p>` : ''}</details>`;
}

// ------------------------------------------------------------------ GF-Panel

function sceneIncident() {
  const player = state.players.find(p => p.id === me);
  if (player?.role !== 'gf') return null;
  const vehicle = state.vehicles.find(v => v.id === player.vehicle);
  if (!vehicle?.incident) return null;
  const incident = state.incidents.find(i => i.id === vehicle.incident && !i.closed && i.massnahmen);
  return incident ? {vehicle, incident} : null;
}

function sceneSlots(mn, vehicle) {
  const mine = mn.laufend.filter(l => l.fz === vehicle.id);
  const info = mn.fahrzeuge[vehicle.id];
  const trupps = info ? info.trupps : 0;
  return {
    mine,
    fuehrungFrei: !mine.some(l => l.platz === 'fuehrung'),
    truppsFrei: trupps - mine.filter(l => l.platz === 'trupp').length,
    trupps,
    info,
  };
}

// Für jeden Knopf: Gruppe (verfuegbar/gesperrt/erledigt/aus) und Unterzeile aus Sicht des eigenen Fahrzeugs.
function sceneButton(m, mn, vehicle, slots) {
  const ort = m.platz === 'fuehrung' ? '🧭 Führung' : '👥 Trupp';
  const sub = [`${m.dauer} s`, ort];
  if (m.fertig) return {group: 'erledigt'};
  if (m.entfaellt) return {group: 'entfaellt'};
  if (m.laufend >= m.max) return {group: 'laeuft'};
  let lock = '';
  if (vehicle.phase !== 'vorort') lock = 'erst nach Eintreffen';
  else if (vehicle.status !== 4) lock = 'erst Status 4 geben';
  else if (!slots.info || !m.braucht.every(f => slots.info.faehigkeiten.includes(f))) lock = 'Nur ' + m.typen.join(' oder ');
  else if (m.hart.length) lock = m.hart[0];
  else if (m.platz === 'fuehrung' ? !slots.fuehrungFrei : slots.truppsFrei <= 0) {
    lock = m.platz === 'fuehrung' ? 'Führung beschäftigt' : 'Kein freier Trupp';
  }
  if (lock) return {group: 'gesperrt', sub: [...sub, '🔒 ' + lock]};
  return {group: 'verfuegbar', sub: [...sub, ...m.weich.map(w => '⚠️ ' + w)], warn: m.weich.length > 0};
}

function sceneLaufend(l, vehicle) {
  const own = l.fz === vehicle.id;
  const wer = `${l.platz === 'fuehrung' ? 'Führung' : 'Trupp ' + l.trupp}${own ? '' : ' · ' + l.call}${l.ki ? ' · KI' : ''}`;
  const zustand = l.status === 'loescht' ? '<span class="mn-state ok">löscht</span>'
    : l.status === 'wartet' ? '<span class="mn-state bad">wartet auf Wasser</span>'
      : `<div class="progress mn-bar"><span data-start="${l.start}" data-ende="${l.ende}"></span></div>`;
  return `<div class="mn-run"><div><b>${esc(l.icon)} ${esc(l.name)}</b> <span class="small">${esc(wer)}</span></div>${zustand}
    ${own ? `<button type="button" class="mn-stop" data-mnstop="${esc(l.key)}">Abbrechen</button>` : ''}</div>`;
}

let sceneMarkup = '';

function renderScene() {
  const panel = $('scenePanel');
  if (!panel) return;
  const found = state && sceneIncident();
  panel.classList.toggle('hidden', !found);
  if (!found) {
    sceneMarkup = '';
    return;
  }
  const {vehicle, incident} = found;
  const mn = incident.massnahmen;
  const slots = sceneSlots(mn, vehicle);
  const groups = {verfuegbar: [], gesperrt: [], erledigt: []};
  for (const m of mn.massnahmen) {
    const b = sceneButton(m, mn, vehicle, slots);
    if (b.group === 'erledigt') groups.erledigt.push(`<li>✅ ${esc(m.name)}</li>`);
    if (b.group !== 'verfuegbar' && b.group !== 'gesperrt') continue;
    groups[b.group].push(`<button type="button" class="mn-btn${b.warn ? ' warn' : ''}" data-mn="${esc(m.key)}"
      ${b.group === 'gesperrt' ? 'disabled' : ''} title="${esc(m.info)}"><span class="mn-name">${esc(m.icon)} ${esc(m.name)}${
      m.pflicht ? ' <span class="small">Pflicht</span>' : ''}</span><span class="mn-sub">${b.sub.map(esc).join(' · ')}</span></button>`);
  }
  const crew = slots.info
    ? `🧭 ${slots.fuehrungFrei ? 'frei' : 'beschäftigt'} · 👥 ${Math.max(0, slots.truppsFrei)} von ${slots.trupps} Trupps frei`
    : 'Anfahrt – Maßnahmen ab Eintreffen';
  const markup = `
    <div class="scene-head"><b>🧯 Meine Einsatzstelle</b>
      <span>${esc(incident.title)} – ${esc(incident.address)}${sceneStichwort(mn)}</span></div>
    <div class="scene-lage">${sceneAmpel(mn)}<span data-scene="brand"></span><span data-scene="wasser"></span>
      <div class="tankbar" data-scene="tankbar" role="img"><span></span></div></div>
    <div class="small">Mein ${esc(vehicle.kind)}: ${crew}${mn.variante ? ' · Lage: ' + esc(mn.variante) : ''}</div>
    ${sceneWarnings(mn)}${sceneNachforderung(mn)}
    ${mn.laufend.length ? `<h3>⏳ Läuft</h3>${mn.laufend.map(l => sceneLaufend(l, vehicle)).join('')}` : ''}
    <h3>▶ Verfügbar</h3>${groups.verfuegbar.join('') || '<p class="small">Gerade nichts – warte auf laufende Maßnahmen.</p>'}
    ${groups.gesperrt.length ? `<details class="mn-group"><summary>🔒 Gesperrt (${groups.gesperrt.length})</summary>${groups.gesperrt.join('')}</details>` : ''}
    ${groups.erledigt.length ? `<details class="mn-group"><summary>✅ Erledigt (${groups.erledigt.length})</summary><ul>${groups.erledigt.join('')}</ul></details>` : ''}
    <details class="mn-group"><summary>ⓘ Erklärungen</summary><ul class="small">${
      mn.massnahmen.map(m => `<li><b>${esc(m.name)}:</b> ${esc(m.info)}</li>`).join('')}</ul></details>`;
  if (markup !== sceneMarkup) {
    const open = new Set(Array.from(panel.querySelectorAll('details[open] > summary'), s => s.textContent.replace(/\(\d+\)/, '')));
    panel.innerHTML = markup;
    sceneMarkup = markup;
    panel.querySelectorAll('details > summary').forEach(s => {
      if (open.has(s.textContent.replace(/\(\d+\)/, ''))) s.parentElement.open = true;
    });
  }
  panel.dataset.incident = incident.id;
  panel.dataset.stufe = mn.stufe;
  const setText = (key, text) => {
    const el = panel.querySelector(`[data-scene="${key}"]`);
    if (el && el.textContent !== text) el.textContent = text;
  };
  setText('brand', sceneBrand(mn));
  setText('wasser', sceneWasser(mn, vehicle.id));
  const bar = panel.querySelector('[data-scene="tankbar"]');
  const fill = sceneTankBar(mn, vehicle.id);
  if (bar) {
    bar.classList.toggle('hidden', fill === null);
    bar.dataset.low = String(fill !== null && fill <= 33);
    bar.firstElementChild.style.width = `${fill ?? 0}%`;
    bar.setAttribute('aria-label', fill === null ? '' : `Tank ${fill} Prozent`);
  }
  tickScene();
}

// Klicks über das Panel verteilen: Die Knöpfe werden bei Änderungen neu gebaut.
$('scenePanel')?.addEventListener('click', event => {
  const incident = $('scenePanel').dataset.incident;
  const start = event.target.closest('[data-mn]');
  if (start && !start.disabled) {
    send('massnahme', {incident, key: start.dataset.mn});
    return;
  }
  const stop = event.target.closest('[data-mnstop]');
  if (stop && confirm('Maßnahme abbrechen? Der Trupp wird frei, der Fortschritt geht verloren.')) {
    send('massnahme_stop', {incident, key: stop.dataset.mnstop});
  }
});

function tickScene() {
  if (!state) return;
  const now = serverNow();
  for (const bar of document.querySelectorAll('[data-start][data-ende]')) {
    const start = Number(bar.dataset.start), ende = Number(bar.dataset.ende);
    const share = ende > start ? Math.min(1, Math.max(0, (now - start) / (ende - start))) : 1;
    bar.style.width = `${Math.round(share * 100)}%`;
  }
  for (const el of document.querySelectorAll('[data-bis]')) {
    const text = `noch ca. ${Math.max(0, Math.ceil(Number(el.dataset.bis) - now))} s`;
    if (el.textContent !== text) el.textContent = text;
  }
}
setInterval(tickScene, 250);
