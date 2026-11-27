// Alarmierung nach AAO (game/aao.py): Stichwort wählen → Vorschlag vom Server → übernehmen, abwählen,
// ergänzen → mit einem Klick alarmieren. „Stichwort ändern“ an einem laufenden Einsatz schlägt nur die
// Differenz vor (Hoch-/Herabstufung). Nutzt $, api, state, me, esc, notice, setState, render aus game.js.
(() => {
  const AAO = JSON.parse($('aaoData').textContent);
  const byKey = new Map(AAO.map(s => [s.key, s]));
  const STATUS = {neu: 'AAO', ersatz: 'Ersatz', alarmiert: 'am Einsatz', zusatz: 'ergänzt'};
  let mode = null;  // null = neuer Einsatz, sonst ID des Einsatzes, dessen Stichwort sich ändert
  let current = null;  // letzter Vorschlag vom Server
  let extra = [];  // von Hand ergänzte Fahrzeuge
  let seq = 0;

  const groups = new Map();
  for (const s of AAO) {
    if (!groups.has(s.gruppe)) groups.set(s.gruppe, []);
    groups.get(s.gruppe).push(s);
  }
  $('stichwort').insertAdjacentHTML('beforeend', [...groups].map(([gruppe, list]) =>
    `<optgroup label="${esc(gruppe)}">${list.map(s =>
      `<option value="${esc(s.key)}">${esc(s.key)} – ${esc(s.name)}</option>`).join('')}</optgroup>`).join(''));

  const kurz = e => /^LZ\d$/.test(e) ? `LZ ${e.slice(2)}` : e;

  function showInfo() {
    const s = byKey.get($('stichwort').value);
    $('aaoInfo').textContent = s ? [s.name, s.beschreibung, s.hinweis, s.basis && `baut auf ${s.basis} auf`]
      .filter(Boolean).join(' · ') : '';
  }

  async function load() {
    showInfo();
    const stichwort = $('stichwort').value;
    const address = $('address').value;
    const mine = ++seq;
    if (!stichwort || (!mode && !address)) {
      current = null;
      draw();
      return;
    }
    try {
      const x = await api('aao', mode ? {stichwort, incident: mode} : {stichwort, address});
      if (mine !== seq) return;
      current = x.vorschlag;
      extra = [];
      notice('');
    } catch (e) {
      if (mine !== seq) return;
      current = null;
      notice(e.message);
    }
    draw();
  }

  function row(x) {
    const status = x.status || 'zusatz';
    const am = status === 'alarmiert';
    const checked = am || (!x.optional && status !== 'zusatz') || status === 'zusatz';
    const note = x.hinweis || (x.optional ? `nur bei Bedarf: ${x.bedingung}` : '');
    return `<label class="aaoRow" data-status="${esc(status)}"${x.optional ? ' data-optional' : ''}>` +
      `<input type="checkbox" value="${esc(x.id)}"${checked ? ' checked' : ''}${am ? ' disabled' : ''}>` +
      `<span class="aaoName"><b>${esc(kurz(x.einheit))} ${esc(x.typ)}</b> <span class="small mono">${esc(x.call)}</span></span>` +
      `<span class="pill">${esc(STATUS[status])}</span>` +
      (note ? `<span class="small aaoNote">${esc(note)}</span>` : '') + '</label>';
  }

  function chosen() {
    return [...$('aaoVorschlag').querySelectorAll('input[type=checkbox]:checked:not(:disabled)')].map(c => c.value);
  }

  function updateButton() {
    const n = current ? chosen().length : 0;
    $('create').textContent = mode
      ? `Stichwort ändern${n ? ` und ${n} nachalarmieren` : ''}`
      : `Einsatz anlegen und ${n} alarmieren`;
  }

  function fehlt(list) {
    const counts = new Map();
    for (const f of list) {
      const text = `${f.regel} (${f.hinweis})${f.optional ? ', nur bei Bedarf' : ''}`;
      counts.set(text, (counts.get(text) || 0) + 1);
    }
    return [...counts].map(([text, n]) => esc((n > 1 ? `${n}× ` : '') + text)).join(', ');
  }

  function draw() {
    const box = $('aaoVorschlag');
    box.classList.toggle('hidden', !current);
    if (!current) {
      box.innerHTML = '';
      updateButton();
      return;
    }
    const listed = new Set(current.fahrzeuge.map(x => x.id).concat(extra));
    const free = (state?.vehicles || []).filter(v => v.phase === 'wache' && v.status !== 6 && !v.incident &&
      !listed.has(v.id));
    const extras = extra.map(id => state?.vehicles.find(v => v.id === id)).filter(Boolean).map(v =>
      ({id: v.id, call: v.call, typ: v.typ || v.kind, einheit: v.einheit || `LZ${v.unit}`, status: 'zusatz'}));
    const pflicht = current.fahrzeuge.filter(x => !x.optional);
    const optional = current.fahrzeuge.filter(x => x.optional);
    box.innerHTML =
      `<div class="small aaoHead">Zuständig: <b>${esc(kurz(current.zustaendig))}</b> · Nachbar: ${esc(kurz(current.nachbar))}` +
      `${current.hinweis ? ' · ' + esc(current.hinweis) : ''}</div>` +
      [...pflicht, ...extras].map(row).join('') +
      (optional.length ? `<div class="small aaoSub">Bei Bedarf</div>${optional.map(row).join('')}` : '') +
      (current.fehlt.length ? `<div class="aaoFehlt small"><b>Nicht verfügbar:</b> ${fehlt(current.fehlt)}</div>` : '') +
      (current.meldungen.length ? `<div class="aaoMeldung small"><b>Über die Leitstelle (ohne Fahrzeug):</b> ${
        current.meldungen.map(esc).join(', ')}</div>` : '') +
      `<div class="row"><select id="aaoExtra" aria-label="Fahrzeug ergänzen"><option value="">Fahrzeug ergänzen …</option>${
        free.map(v => `<option value="${esc(v.id)}">${esc(v.call)}${v.owner ? ' (Spieler)' : ''}</option>`).join('')}</select></div>`;
    box.querySelectorAll('input[type=checkbox]').forEach(c => c.onchange = updateButton);
    $('aaoExtra').onchange = e => {
      if (e.target.value) extra.push(e.target.value);
      draw();
    };
    updateButton();
  }

  function reset() {
    mode = null;
    current = null;
    extra = [];
    seq++;
    $('aaoModeTitle').textContent = 'Neuer Einsatz nach AAO';
    $('stichwort').value = '';
    $('title').value = '';
    $('address').classList.remove('hidden');
    $('title').classList.remove('hidden');
    $('aaoCancel').classList.add('hidden');
    showInfo();
    draw();
  }

  function openStufe(id) {
    const inc = state?.incidents.find(i => i.id === id);
    if (!inc) return;
    mode = id;
    $('aaoModeTitle').textContent = `Stichwort ändern: ${inc.title} – ${inc.address}`;
    $('stichwort').value = byKey.has(inc.stichwort) ? inc.stichwort : '';
    $('address').classList.add('hidden');
    $('title').classList.add('hidden');
    $('aaoCancel').classList.remove('hidden');
    $('aaoForm').scrollIntoView({behavior: 'smooth', block: 'start'});
    $('stichwort').focus();
    load();
  }

  $('stichwort').onchange = load;
  $('address').onchange = load;
  $('aaoCancel').onclick = reset;
  $('incidents').addEventListener('click', e => {
    const b = e.target.closest('[data-stufe]');
    if (b) openStufe(b.dataset.stufe);
  });
  $('create').onclick = async () => {
    const stichwort = $('stichwort').value;
    if (!stichwort) return notice('Bitte ein Stichwort aus der AAO wählen.');
    if (!mode && !$('address').value) return notice('Bitte den Einsatzort wählen.');
    const vehicles = current ? chosen() : [];
    const data = mode
      ? {incident: mode, stichwort, vehicles}
      : {title: `${stichwort} · ${$('title').value.trim() || byKey.get(stichwort).name}`,
        address: $('address').value, vehicles};
    $('create').disabled = true;
    try {
      const x = await api(mode ? 'stufe' : 'incident', data);
      setState(x.state);
      soundsFromState(state);
      render();
      notice('');
      reset();
    } catch (e) {
      notice(e.message);
    } finally {
      $('create').disabled = false;
    }
  };
  reset();
})();
