'use strict';
// FMS-Status im Browser. Der GF gibt jeden Status selbst; Status 5 ist ein Sprechwunsch,
// den die Leitstelle mit einer Sprechaufforderung (J) beantwortet. Die Regeln selbst prüft der
// Server (game/engine.py, _status/_speak); hier nur Tasten sperren, Hinweise und Sprechwünsche zeigen.
const WBFms = (() => {
  const escape = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  // So lange zeigt der GF die Sprechaufforderung an (s).
  const SPEAK_SHOWN = 45;
  let lastSpeakOk = 0, knownRequests = new Set(), firstRender = true;

  // Warum ein Status gerade nicht geht ('' = erlaubt). Spiegelbild von _status in engine.py.
  function blocked(v, n) {
    if (!v) return 'Kein Fahrzeug besetzt';
    const alarmed = v.phase === 'wache' && v.incident;
    if (n === 5) return v.speak ? 'Sprechwunsch läuft schon' : '';
    if (n === 3) return v.incident && (v.phase === 'wache' || v.phase === 'anfahrt') ? '' : 'Erst nach einer Alarmierung';
    if (n === 4) return v.phase === 'vorort' ? '' : 'Erst an der Einsatzstelle';
    if (n === 2 || n === 6) return v.phase === 'wache' && !v.incident ? '' : 'Nur auf der Wache ohne Einsatz';
    if (n === 1) return v.phase === 'anfahrt' || alarmed ? 'Nicht während der Anfahrt' : '';
    return '';
  }

  // Welcher Status jetzt fällig ist (0 = keiner).
  function next(v) {
    if (!v) return 0;
    if (v.phase === 'wache' && v.incident) return 3;
    if (v.phase === 'vorort' && v.status !== 4) return 4;
    if (v.phase === 'rueckfahrt' && v.status !== 1) return 1;
    if (v.phase === 'wache' && ![1, 2, 6].includes(v.status)) return 2;
    return 0;
  }

  const NEXT_HINT = {
    3: '🚨 Alarmiert – gib Status 3, um auszurücken.',
    4: '📍 An der Einsatzstelle – gib Status 4.',
    1: '↩️ Rückfahrt – gib Status 1 (frei über Funk).',
    2: '🏠 Zurück auf der Wache – gib Status 2.',
  };

  // Was der GF als Nächstes tun sollte.
  function hint(v, now) {
    if (!v) return '';
    if (v.speak_ok && now - v.speak_ok < SPEAK_SHOWN) return '🎙️ Sprechaufforderung von der Leitstelle – bitte jetzt sprechen.';
    if (v.speak) return '⏳ Sprechwunsch (5) gesendet – warte auf die Leitstelle.';
    return NEXT_HINT[next(v)] || '';
  }

  function buttons(v, labels) {
    const due = next(v);
    return Object.entries(labels).map(([n, text]) => {
      const reason = blocked(v, Number(n));
      const active = v && (v.status == n || (n === '5' && v.speak));
      const wanted = !reason && due === Number(n);
      const label = n === '5' && v?.speak ? `${n} ${escape(text)} (wartet)` : `${n} ${escape(text)}`;
      return `<button data-status="${n}" class="${active ? 'active' : ''}${wanted ? ' wanted' : ''}"` +
        `${reason ? ` disabled title="${escape(reason)}"` : ''}>${label}</button>`;
    }).join('');
  }

  // Liste der offenen Sprechwünsche für die Leitstelle.
  function requests(state) {
    const open = state.vehicles.filter(v => v.speak).sort((a, b) => a.speak - b.speak);
    if (!open.length) return '';
    return '<h3>Sprechwünsche (Status 5)</h3>' + open.map(v => {
      const owner = state.players.find(p => p.id === v.owner);
      return `<div class="speakItem"><span class="fms" data-fms="5">5</span> <b>${escape(v.call)}</b>` +
        `${owner ? ` <span class="small">${escape(owner.name)}</span>` : ''}` +
        `<button type="button" data-speak="${escape(v.id)}">J · Sprechaufforderung</button></div>`;
    }).join('');
  }

  // Töne/Hinweise bei neuen Ereignissen (nicht beim ersten Laden des Raums).
  function signals(state, me, isLs) {
    const mine = state.vehicles.find(v => v.owner === me);
    const requestIds = new Set(state.vehicles.filter(v => v.speak).map(v => `${v.id}:${v.speak}`));
    if (!firstRender) {
      if (mine?.speak_ok && mine.speak_ok > lastSpeakOk && typeof tone === 'function') tone('radio');
      if (isLs && [...requestIds].some(id => !knownRequests.has(id)) && typeof tone === 'function') tone('status');
    }
    if (mine?.speak_ok) lastSpeakOk = Math.max(lastSpeakOk, mine.speak_ok);
    knownRequests = requestIds;
    firstRender = false;
  }

  return {blocked, hint, buttons, requests, signals};
})();
