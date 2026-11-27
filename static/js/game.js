let incidentMarkup = '';
let fmeKey = '';
let fmeAcknowledged = false;
let fmeLines = [];
let fmeCloseTimer = 0;
// So lange bleibt das Pop-up nach dem Quittieren mit „✓ Quittiert“ sichtbar (ms).
const FME_CLOSE_DELAY = 1600;

function updateFme(next) {
  const player = next.players.find(player => player.id === me);
  const vehicle = next.vehicles.find(vehicle => vehicle.id === player?.vehicle);
  const incident = vehicle && next.incidents.find(incident =>
    !incident.closed && incident.assigned.includes(vehicle.id) &&
    (vehicle.incident === incident.id || !vehicle.incident)
  );
  const key = incident ? JSON.stringify([vehicle.id, incident.id]) : '';
  if (key === fmeKey) return;
  fmeKey = key;
  fmeAcknowledged = false;
  clearTimeout(fmeCloseTimer);
  // Der Melder ist ein Pop-up: Er erscheint bei jeder neuen Alarmierung über allem anderen.
  $('fmePanel').classList.toggle('hidden', !incident);
  $('fmeAcknowledge').disabled = !incident;
  if (incident) {
    fmeLines = ['Einsatzalarm', vehicle.call, incident.title, incident.address];
    WBFme.alarm(fmeLines);
    $('fmeAcknowledge').focus({preventScroll: true});
  } else {
    fmeLines = [];
    WBFme.clear();
  }
}

$('fmeAcknowledge').onclick = () => {
  if (!fmeKey || fmeAcknowledged) return;
  fmeAcknowledged = true;
  $('fmeAcknowledge').disabled = true;
  WBFme.acknowledge(fmeLines);
  const key = fmeKey;
  fmeCloseTimer = setTimeout(() => {
    if (fmeKey === key) $('fmePanel').classList.add('hidden');
  }, FME_CLOSE_DELAY);
};

// Auswahl im Einsatz: Spielerfahrzeuge immer; unbesetzte (KI-Besatzung) nur, wenn der Server es erlaubt,
// sonst ausgegraut mit Grund (z. B. „Bedarf gedeckt“ oder „erst freie Spielerfahrzeuge alarmieren“).
function vehicleOptions(incident) {
  const free = state.vehicles.filter(v => v.phase === 'wache' && v.status !== 6 && !v.incident);
  const option = v => `<option value="${esc(v.id)}">${esc(v.call)}</option>`;
  const owned = free.filter(v => v.owner), crewless = free.filter(v => !v.owner);
  if (state.ai_mode) return free.map(option).join('');
  let markup = owned.length ? `<optgroup label="Spielerfahrzeuge">${owned.map(option).join('')}</optgroup>` : '';
  if (crewless.length) {
    const block = incident.ai_crew_block;
    const label = block ? `Mit KI-Besatzung – gesperrt: ${block}`
      : `Mit KI-Besatzung – Einsatz braucht ${incident.need} Fahrzeuge`;
    markup += `<optgroup label="${esc(label)}"${block ? ' disabled' : ''}>${crewless.map(option).join('')}</optgroup>`;
  }
  return markup;
}

function updateIncidents(markup) {
  if (markup === incidentMarkup) return;
  const container = $('incidents');
  const selections = new Map(Array.from(
    container.querySelectorAll('select[data-for]'),
    select => [select.dataset.for, select.value]
  ));
  container.innerHTML = markup;
  incidentMarkup = markup;
  for (const select of container.querySelectorAll('select[data-for]')) {
    const vehicle = selections.get(select.dataset.for);
    if (vehicle && Array.from(select.options).some(option => option.value === vehicle)) {
      select.value = vehicle;
    }
  }
}

let me=null,state=null,room='',busy=false,focusIncident='';let pendingActions=0,stateRevision=0;const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const labels={1:'Frei über Funk',2:'Auf Wache',3:'Anfahrt',4:'Einsatzstelle',5:'Sprechwunsch',6:'Nicht einsatzbereit'};function notice(s){$('notice').textContent=s}// Während eines Deploys ist der Server kurz weg (Netzfehler, 502/503/504 von Caddy, keine JSON-Antwort). Dann bleibt das Spiel im Raum und fragt weiter ab; die Räume werden beim Neustart wiederhergestellt (game/persistence.py).
const RESTARTING='Server startet neu … gleich geht es im selben Raum weiter.';let serverDown=false;function restartError(){let err=Error(RESTARTING);err.restarting=true;return err}async function api(action,data={}){let res;try{res=await fetch('/api',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrfToken()},body:JSON.stringify({action,room,id:me,...data})})}catch(e){throw restartError()}let obj;try{obj=await res.json()}catch(e){obj=null}if(!obj||typeof obj!=='object'||[502,503,504].includes(res.status)&&!obj.error)throw restartError();if(!res.ok){let err=Error(obj.error||'Serverfehler');err.kicked=Boolean(obj.kicked);throw err}return obj}async function send(action,data={}){pendingActions++;stateRevision++;try{let x=await api(action,data);if(x.state){setState(x.state);soundsFromState(state);render()}notice('')}catch(e){if(e.kicked)leaveRoom(e.message);else notice(e.message)}finally{pendingActions--}}
// Raum betreten: 'create_room' (Server vergibt den Code) oder 'join' mit eingegebenem Code.
async function enterRoom(action){try{if(action==='join'){room=$('room').value.toUpperCase().trim();if(!room)throw Error('Bitte gib einen Raumcode ein.')}else room='';let x=await api(action);if(x.room)room=x.room;$('room').value=room;me=x.id;setState(x.state);soundsFromState(state);$('login').classList.add('hidden');['rolesPanel','dashboard','mapPanel','incidentsPanel','vehiclesPanel','controlPanel','sectionsPanel','radioPanel','voicePanel'].forEach(id=>$(id).classList.remove('hidden'));notice('');setNotice('');render()}catch(e){notice(e.message)}}
$('join').onclick=()=>enterRoom('join');$('publicRoom').onclick=()=>{$('room').value=publicRoomCode;enterRoom('join')};$('createRoom').onclick=()=>enterRoom('create_room');$('room').onkeydown=e=>{if(e.key==='Enter')$('join').click()};
// Zurück zum Startbildschirm (Sitzung abgelaufen, Raum weg oder von der Raumverwaltung entfernt).
function leaveRoom(message){if(typeof voiceStream!=='undefined'&&voiceStream)voiceLeave();me=null;state=null;WBLayout.apply(null);$('login').classList.remove('hidden');['rolesPanel','dashboard','mapPanel','incidentsPanel','vehiclesPanel','controlPanel','sectionsPanel','radioPanel','voicePanel'].forEach(id=>$(id).classList.add('hidden'));$('fmePanel').classList.add('hidden');fmeKey='';$('connection').textContent='Nicht verbunden';$('connection').dataset.state='off';loadAccount().catch(error=>setNotice(error.message,'error'));notice(message);setNotice(message,'error')}
$('copyCode').onclick=async()=>{try{await navigator.clipboard.writeText(room);notice('Raumcode '+room+' kopiert.')}catch(e){getSelection().selectAllChildren($('roomCode'));notice('Kopieren nicht möglich – der Code ist markiert, kopiere ihn mit Strg+C: '+room)}};
function renderRoomAdmin(){let owner=state.admin===me&&!state.permanent;$('roomCode').textContent=state.code||room;$('roomOwner').textContent=state.permanent?'Öffentlicher Discord-Raum':owner?'Du verwaltest diesen Raum.':'Raumverwaltung: '+(state.owner_name||'–')+(state.admin?'':' (gerade offline)');
$('players').innerHTML=state.players.map(p=>`<div class="item">${esc(p.name)}${p.id===state.admin?' (Raumverwaltung)':''} · ${esc(state.vehicles.find(v=>v.id===p.vehicle)?.call||(p.role==='ls'?'Leitstelle':'Keine Rolle'))}${owner&&p.id!==me?`<div class="playerActions"><button data-kick="${esc(p.id)}">Entfernen</button><button class="danger" data-ban="${esc(p.id)}">Entfernen & sperren</button><button data-owner="${esc(p.id)}">Besitz übertragen</button></div>`:''}</div>`).join('');
let banned=owner?state.banned||[]:[];$('bannedList').classList.toggle('hidden',!banned.length);$('bannedList').innerHTML=banned.length?'<h3>Gesperrt</h3>'+banned.map(b=>`<div class="item">${esc(b.name)} <button data-unban="${esc(b.account)}">Sperre aufheben</button></div>`).join(''):'';
const nameOf=id=>state.players.find(p=>p.id===id)?.name||'';
$('players').querySelectorAll('[data-kick]').forEach(b=>b.onclick=()=>{if(confirm(nameOf(b.dataset.kick)+' aus dem Raum entfernen?'))send('kick',{target:b.dataset.kick})});
$('players').querySelectorAll('[data-ban]').forEach(b=>b.onclick=()=>{if(confirm(nameOf(b.dataset.ban)+' entfernen und für diesen Raum sperren?'))send('kick',{target:b.dataset.ban,ban:true})});
$('players').querySelectorAll('[data-owner]').forEach(b=>b.onclick=()=>{if(confirm('Raumverwaltung an '+nameOf(b.dataset.owner)+' übertragen? Du verlierst die Verwaltungsrechte.'))send('transfer_owner',{target:b.dataset.owner})});
$('bannedList').querySelectorAll('[data-unban]').forEach(b=>b.onclick=()=>send('unban',{account:b.dataset.unban}))}
$('takeLs').onclick=()=>send('take_ls', {
  replace_dispatcher: developerAccount ? state?.dispatcher : null
});$('leaveLs').onclick=()=>send('leave_ls');$('goGf').onclick=()=>{$('vehiclesPanel').scrollIntoView({behavior:'smooth'})};$('send').onclick=()=>{let msg=$('message').value;if(msg.trim())send('radio',{message:msg});$('message').value=''};$('message').onkeydown=e=>{if(e.key==='Enter')$('send').click()};$('release').onclick=()=>send('release');
// Abstand Server-Uhr minus Browser-Uhr in Sekunden. Fahrzeugpositionen werden in Server-Zeit berechnet,
// damit eine falsch gehende Browser-Uhr die Animation nicht verschiebt.
let clockOffset = 0;

function setState(next) {
  state = next;
  if (typeof next?.server_time === 'number') clockOffset = next.server_time - Date.now() / 1000;
}

function serverNow() {
  return Date.now() / 1000 + clockOffset;
}

// Seitenverhältnis der Karte (1536 × 1024), damit Strecken wie auf dem Server (game/strassen.py) zählen.
const MAP_ASPECT = 1.5;

function mapDistance(a, b) {
  return Math.hypot((a[0] - b[0]) * MAP_ASPECT, a[1] - b[1]);
}

// Punkt nach dem Anteil share der Gesamtlänge einer Route [[x, y], …].
function routePoint(route, share) {
  const total = route.slice(1).reduce((sum, point, i) => sum + mapDistance(route[i], point), 0);
  let remaining = Math.min(1, Math.max(0, share)) * total;
  for (let i = 1; i < route.length; i++) {
    const a = route[i - 1], b = route[i], step = mapDistance(a, b);
    if (step >= remaining) {
      const t = step ? remaining / step : 1;
      return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
    }
    remaining -= step;
  }
  return route[route.length - 1];
}

// Der Server legt beim Phasenwechsel Weg (phase_route) und Ankunftszeit (phase_until) fest.
// Hier wird nur noch dazwischen interpoliert: (jetzt − phase_at) / (phase_until − phase_at).
// Fahrten aus älteren Räumen ohne Route laufen weiter gerade von phase_from nach phase_to.
function position(v) {
  const span = (v.phase_until ?? v.phase_at) - v.phase_at;
  const share = span > 0 ? Math.min(1, Math.max(0, (serverNow() - v.phase_at) / span)) : 1;
  if (Array.isArray(v.phase_route) && v.phase_route.length > 1) return routePoint(v.phase_route, share);
  const from = v.phase_from || v.base;
  const to = v.phase_to || from;
  return [from[0] + (to[0] - from[0]) * share, from[1] + (to[1] - from[1]) * share];
}

// Zwischen zwei Abfragen (1,5 s) nur die Fahrzeug-Pins verschieben, damit die Fahrt flüssig läuft.
function animateVehicles() {
  if (state) {
    for (const pin of document.querySelectorAll('#markers .pin.vehicle[data-vehicle-pin]')) {
      const vehicle = state.vehicles.find(v => v.id === pin.dataset.vehiclePin);
      if (!vehicle || (vehicle.phase !== 'anfahrt' && vehicle.phase !== 'rueckfahrt')) continue;
      const [x, y] = position(vehicle);
      pin.style.left = `${x * 100}%`;
      pin.style.top = `${y * 100}%`;
    }
    WBFahrzeuge.layout($('markers'));
  }
  requestAnimationFrame(animateVehicles);
}
requestAnimationFrame(animateVehicles);

// Karte: Einsatz- und Fahrzeugpunkte. Die Buttons bleiben zwischen den Abfragen (alle 1,5 s) bestehen,
// nur Lage und Beschriftung werden angepasst – so bleiben Tastaturfokus und offene Fahrzeug-Info erhalten.
const phaseLabels = {anfahrt: 'Anfahrt', vorort: 'Vor Ort', rueckfahrt: 'Rückfahrt'};
const mapPins = new Map();
let mapVehicle = '';
let flashVehicle = '';
let flashUntil = 0;

function showIncident(id) {
  focusIncident = id;
  if ($('incidentFilter').value === 'closed') $('incidentFilter').value = 'all';
  render();
  document.getElementById('inc-' + id)?.scrollIntoView({behavior: 'smooth', block: 'center'});
}

function showVehicleInList(id) {
  WBLayout.openList();
  const find = () => $('vehicles').querySelector(`[data-vehicle-item="${CSS.escape(id)}"]`);
  if (!find()) {
    $('vehicleSearch').value = '';
    $('unitFilter').value = 'all';
  }
  flashVehicle = id;
  flashUntil = Date.now() + 2500;
  render();
  find()?.scrollIntoView({behavior: 'smooth', block: 'center'});
  setTimeout(() => { if (Date.now() >= flashUntil) render(); }, 2600);
}

function mapPin(key, create) {
  let pin = mapPins.get(key);
  if (!pin) {
    pin = document.createElement('button');
    pin.type = 'button';
    create(pin);
    mapPins.set(key, pin);
    $('markers').appendChild(pin);
  }
  return pin;
}

function renderMap() {
  const shown = new Set();
  for (const incident of state.incidents) {
    if (incident.closed) continue;
    const pin = mapPin('i:' + incident.id, pin => {
      pin.className = 'pin';
      pin.textContent = '!';
      pin.dataset.pin = incident.id;
      pin.addEventListener('click', () => showIncident(pin.dataset.pin));
    });
    pin.classList.toggle('selected', focusIncident === incident.id);
    pin.title = incident.title;
    pin.setAttribute('aria-label', `Einsatz ${incident.title}, ${incident.address}`);
    pin.style.left = `${incident.pos[0] * 100}%`;
    pin.style.top = `${incident.pos[1] * 100}%`;
    shown.add('i:' + incident.id);
  }
  // Fahrzeuge als Mini-Fahrzeug (Aussehen, Drehung und Versatz bei mehreren: WBFahrzeuge in fahrzeuge.js).
  for (const vehicle of state.vehicles) {
    const phase = phaseLabels[vehicle.phase];
    if (!phase) continue;
    const pin = mapPin('v:' + vehicle.id, pin => {
      pin.dataset.vehiclePin = vehicle.id;
      pin.innerHTML = WBFahrzeuge.inner(vehicle);  // Grafik + Namensschild, je Fahrzeug unveränderlich
      pin.setAttribute('aria-haspopup', 'dialog');
      pin.setAttribute('aria-controls', 'vehicleInfo');
      pin.addEventListener('click', () => toggleVehicleInfo(pin.dataset.vehiclePin));
    });
    const className = `pin vehicle ${WBFahrzeuge.classes(vehicle)}${mapVehicle === vehicle.id ? ' selected' : ''}`;
    if (pin.className !== className) pin.className = className;
    pin.dataset.dir = WBFahrzeuge.direction(vehicle);
    pin.title = WBFahrzeuge.describe(vehicle);
    pin.setAttribute('aria-label', `${vehicle.call}, Status ${vehicle.status} ${labels[vehicle.status] || ''}, ${phase}`);
    pin.setAttribute('aria-expanded', String(mapVehicle === vehicle.id));
    const [x, y] = position(vehicle);
    pin.style.left = `${x * 100}%`;
    pin.style.top = `${y * 100}%`;
    shown.add('v:' + vehicle.id);
  }
  for (const [key, pin] of mapPins) {
    if (!shown.has(key)) {
      pin.remove();
      mapPins.delete(key);
    }
  }
  WBFahrzeuge.layout($('markers'));
  updateVehicleInfo();
}

// Info-Karte zu einem Fahrzeugpunkt. Sie wird beim Neuzeichnen nur aktualisiert, nicht neu aufgebaut.
function toggleVehicleInfo(id) {
  if (mapVehicle === id) {
    closeVehicleInfo(true);
    return;
  }
  mapVehicle = id;
  const card = $('vehicleInfo');
  const pin = mapPins.get('v:' + id);
  const map = $('map').getBoundingClientRect(), at = (pin?.querySelector('.veh-body') || pin)?.getBoundingClientRect();
  // In die Ecke gegenüber dem Punkt, damit die Info-Karte den Punkt nicht verdeckt.
  const left = !at || at.left - map.left > map.width / 2;
  const top = !at || at.top - map.top > map.height / 2;
  card.classList.toggle('at-left', left);
  card.classList.toggle('at-right', !left);
  card.classList.toggle('at-top', top);
  card.classList.toggle('at-bottom', !top);
  card.classList.remove('hidden');
  renderMap();
  card.focus({preventScroll: true});
}

function closeVehicleInfo(returnFocus) {
  const card = $('vehicleInfo');
  const pin = mapPins.get('v:' + mapVehicle);
  const hadFocus = card.contains(document.activeElement);
  mapVehicle = '';
  card.classList.add('hidden');
  if (pin) {
    pin.classList.remove('selected');
    pin.setAttribute('aria-expanded', 'false');
    if (returnFocus || hadFocus) pin.focus({preventScroll: true});
  }
}

function setInfoText(id, text) {
  if ($(id).textContent !== text) $(id).textContent = text;
}

function updateVehicleInfo() {
  if (!mapVehicle) return;
  const vehicle = state.vehicles.find(v => v.id === mapVehicle);
  if (!vehicle || !phaseLabels[vehicle.phase]) {
    closeVehicleInfo(false);
    return;
  }
  const incident = state.incidents.find(i => i.id === vehicle.incident);
  const owner = state.players.find(p => p.id === vehicle.owner);
  setInfoText('vehicleInfoTitle', vehicle.call);
  setInfoText('vehicleInfoStatus', `${vehicle.status} · ${labels[vehicle.status] || ''}`);
  $('vehicleInfoStatus').dataset.fms = vehicle.status;
  setInfoText('vehicleInfoPhase', phaseLabels[vehicle.phase]);
  setInfoText('vehicleInfoIncident', incident
    ? `${incident.title} · ${incident.address}${incident.closed ? ' (abgeschlossen)' : ''}`
    : '–');
  setInfoText('vehicleInfoCrew', owner ? owner.name + (owner.id === me ? ' (du)' : '') : 'KI-Besatzung');
  $('vehicleInfoIncidentBtn').classList.toggle('hidden', !incident || incident.closed);
  $('vehicleInfoListBtn').classList.toggle('hidden', $('vehiclesPanel').classList.contains('hidden'));
}

$('vehicleInfoClose').addEventListener('click', () => closeVehicleInfo(true));
$('vehicleInfoIncidentBtn').addEventListener('click', () => {
  const vehicle = state?.vehicles.find(v => v.id === mapVehicle);
  if (vehicle?.incident) showIncident(vehicle.incident);
});
$('vehicleInfoListBtn').addEventListener('click', () => {
  if (mapVehicle) showVehicleInList(mapVehicle);
});
document.addEventListener('click', event => {
  if (mapVehicle && !event.target.closest('#vehicleInfo, [data-vehicle-pin]')) closeVehicleInfo(false);
});
document.addEventListener('keydown', event => {
  if (mapVehicle && event.key === 'Escape') closeVehicleInfo(true);
});
function render(){if(!state)return;
updateFme(state);
$('countOpen').textContent=state.incidents.filter(i=>!i.closed).length;
$('countFree').textContent=state.vehicles.filter(v=>v.phase==='wache'&&[1,2].includes(v.status)&&!v.incident).length;
$('countDrive').textContent=state.vehicles.filter(v=>v.phase==='anfahrt').length;
$('countSite').textContent=state.vehicles.filter(v=>v.phase==='vorort').length;$('connection').textContent=`${room} · ${state.players.length} Spieler`;$('connection').dataset.state='ok';
let p=state.players.find(p=>p.id===me),isLs=p?.role==='ls',isGf=p?.role==='gf',lsOwner=state.players.find(x=>x.id===state.dispatcher);$('roleInfo').textContent=isLs?'Du besetzt die Leitstelle. Nur du kannst Einsätze erstellen, alarmieren und beenden.':isGf?'Du bist Gruppenführer. Fahrzeugstatus und Einsatzmaßnahmen gehören zu deiner Rolle.':lsOwner?'Leitstelle besetzt durch '+lsOwner.name+'. Du kannst ein Fahrzeug übernehmen.':'Leitstelle noch frei. Du kannst die Leitstelle oder ein Fahrzeug übernehmen.';$('takeLs').disabled=isLs||isGf||(!developerAccount&&!!lsOwner);
$('takeLs').textContent=developerAccount&&lsOwner&&!isLs
  ? 'Besetzte Leitstelle übernehmen'
  : 'Leitstelle übernehmen';$('leaveLs').disabled=!isLs;$('goGf').disabled=isLs;$('incidentsPanel').classList.remove('hidden');$('aaoForm').classList.toggle('hidden',!isLs);$('vehiclesPanel').classList.toggle('hidden',isLs);$('controlPanel').classList.toggle('hidden',!isGf);$('dashboard').classList.toggle('hidden',!isLs);$('create').disabled=!isLs;let mine=state.vehicles.find(v=>v.id===p?.vehicle);$('myVehicle').innerHTML=mine?`<b>${esc(mine.call)}</b><p><span class="fms" data-fms="${mine.status}">${mine.status}</span> ${esc(labels[mine.status])}${phaseLabel(mine.phase)===labels[mine.status]?'':' · '+esc(phaseLabel(mine.phase))}</p>`:'Noch kein Fahrzeug besetzt';$('statuses').innerHTML=WBFms.buttons(mine,labels);$('fmsHint').textContent=WBFms.hint(mine,serverNow());$('fmsHint').classList.toggle('hidden',!$('fmsHint').textContent);$('speakRequests').innerHTML=isLs?WBFms.requests(state):'';$('speakRequests').querySelectorAll('[data-speak]').forEach(b=>b.onclick=()=>send('speak',{vehicle:b.dataset.speak}));WBFms.signals(state,me,isLs);$('statuses').querySelectorAll('button').forEach(b=>b.onclick=()=>send('status',{status:Number(b.dataset.status)}));$('release').disabled=!mine||mine.phase!=='wache'||!!mine.incident;
WBLayout.apply(isGf&&mine?mine:null,labels);
$('vehicles').innerHTML=state.vehicles.filter(v=>( $('unitFilter').value==='all'||String(v.unit)===$('unitFilter').value )&&v.call.toLowerCase().includes($('vehicleSearch').value.trim().toLowerCase())).map(v=>{let owner=state.players.find(p=>p.id===v.owner);return `<div class="item${flashVehicle===v.id&&Date.now()<flashUntil?' vehicle-flash':''}" data-vehicle-item="${esc(v.id)}"><b>${esc(v.call)}</b> <span class="fms" data-fms="${v.status}">${v.status}</span><div class="small">${owner?'GF: '+esc(owner.name):'GF frei'} · ${v.seats} Plätze · ${esc(phaseLabel(v.phase))}</div><button data-vehicle="${esc(v.id)}" ${isLs||(owner&&owner.id!==me)||v.phase!=='wache'?'disabled':''}>${owner?.id===me?'Dein Fahrzeug':'Übernehmen'}</button></div>`}).join('');$('vehicles').querySelectorAll('[data-vehicle]').forEach(b=>b.onclick=()=>send('claim',{vehicle:b.dataset.vehicle}));renderRoomAdmin();
updateIncidents(state.incidents.filter(i=>$('incidentFilter').value==='all'||($('incidentFilter').value==='closed'?i.closed:!i.closed)).slice().reverse().map(i=>{let assigned=i.assigned.map(id=>state.vehicles.find(v=>v.id===id)).filter(Boolean);let arrived=assigned.some(v=>v.phase==='vorort');return `<div class="incident" id="inc-${esc(i.id)}" data-state="${i.closed?'closed':i.working?'working':'open'}"><b>${esc(i.title)}</b> <span class="pill ${i.closed?'green':''}">${i.closed?'Abgeschlossen':i.working?'In Bearbeitung':'Offen'}</span><div class="small">${esc(i.address)} · <span class="mono">${esc(i.created)}</span></div><div class="small">Alarmiert: ${assigned.map(v=>esc(v.call)+` <span class="fms" data-fms="${v.status}">${v.status}</span>`).join(', ')||'noch keine'}</div><div class="progress"><span style="width:${i.progress}%"></span></div><div class="small">Fortschritt: ${Math.round(i.progress)} % ${i.working?'· Mannschaft arbeitet':''}</div>${i.closed?'':`<div class="row" ${!isLs?'style="display:none"':''}><select data-for="${esc(i.id)}" ${!isLs?'disabled':''}><option value="">Fahrzeug wählen</option>${vehicleOptions(i)}</select><button data-dispatch="${esc(i.id)}" ${!isLs?'disabled':''}>Alarmieren</button></div><div class="row"><button data-work="${esc(i.id)}" ${!isGf||!mine||!i.assigned.includes(mine.id)||mine.phase!=='vorort'||i.working?'disabled':''}>${i.working?'Arbeiten laufen':'Maßnahmen starten'}</button>${isLs?`<button data-stufe="${esc(i.id)}">Stichwort ändern</button><button data-close="${esc(i.id)}">Einsatz beenden</button>`:''}</div>`}</div>`}).join(''));$('incidents').querySelectorAll('[data-dispatch]').forEach(b=>b.onclick=()=>{let id=b.dataset.dispatch,v=$('incidents').querySelector(`select[data-for="${id}"]`).value;if(!v){notice('Bitte zuerst ein verfügbares Fahrzeug auswählen.');return}send('dispatch',{incident:id,vehicle:v})});$('incidents').querySelectorAll('[data-work]').forEach(b=>b.onclick=()=>send('work',{incident:b.dataset.work}));$('incidents').querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>send('close',{incident:b.dataset.close}));let log=$('log'),atBottom=log.scrollTop+log.clientHeight>=log.scrollHeight-35;log.innerHTML=state.radio.filter(x=>{const rf=$('radioFilter').value,talk=x.kind==='funk'||x.kind==='discord';return rf==='all'||(rf==='funk'?talk:!talk)}).map(x=>`<div class="item radio-${esc(x.kind||'auto')}"><span class="small">${esc(x.time)} · ${x.kind==='discord'?'Discord · ':''}${esc(x.author)}${x.call?' · '+esc(x.call):''}</span><div>${esc(x.message)}</div></div>`).join('');if(atBottom)log.scrollTop=log.scrollHeight;renderMap();renderSections()}

const phaseLabel=p=>p==='wache'?'Auf Wache':phaseLabels[p]||p;

function renderSections(){
 const own=state.players.find(p=>p.id===me),isLs=own?.role==='ls';
 $('sectionsPanel').classList.remove('hidden'); const overlay=$('weatherOverlay');if(overlay)overlay.className=({Regen:'rain',Nebel:'fog',Windig:'wind'})[state.weather]||'';
 $('aiInfo').textContent=state.ai_dispatcher?'KI-Leitstelle aktiv: Sie erstellt Einsätze und alarmiert Fahrzeuge automatisch, bis jemand die Leitstelle übernimmt.':state.ai_mode?'KI-Gruppenführer aktiv: Unbesetzte Fahrzeuge können alarmiert werden und arbeiten selbstständig.':'Mehrspieler: Die Leitstelle alarmiert nach AAO, auch unbesetzte Fahrzeuge mit KI-Besatzung. Einzeln nachalarmierte unbesetzte Fahrzeuge nur, solange der Bedarf laut AAO offen ist und kein Spielerfahrzeug mehr frei ist.';
 $('aiInfo').textContent += ` · Wetter: ${state.weather} · Fahrzeit ca. ${state.travel_time||12}s · Arbeitsfaktor ${Math.round((state.work_factor||1)*100)}%`; $('sectionsList').innerHTML=state.incidents.filter(i=>!i.closed).map(i=>{
 const sections=i.sections||{'Hauptabschnitt':{leader:'KI-Einsatzleitung',vehicles:[]}};
 const opts=Object.keys(sections).map(n=>`<option value="${esc(n)}">${esc(n)}</option>`).join('');
 const vehicles=i.assigned.map(id=>state.vehicles.find(v=>v.id===id)).filter(Boolean);
 const rows=Object.entries(sections).map(([name,sec])=>`<div class="item"><b>${esc(name)}</b> · Leitung: ${esc(sec.leader)} · ${Math.round(sec.progress||0)} %<div class="progress"><span style="width:${Math.round(sec.progress||0)}%"></span></div><div class="small">Fahrzeuge: ${sec.vehicles.map(id=>esc(state.vehicles.find(v=>v.id===id)?.call||id)).join(', ')||'Keine'}</div>${isLs?`<div class="row"><select data-leader="${esc(i.id)}" data-section="${esc(name)}"><option value="KI-Abschnittsleitung">KI-Abschnittsleitung</option>${state.players.filter(p=>p.role==='gf').map(p=>`<option value="${esc(p.name)}" ${p.name===sec.leader?'selected':''}>${esc(p.name)}</option>`).join('')}</select><button data-setleader="${esc(i.id)}" data-section="${esc(name)}">Leitung zuweisen</button></div>`:''}</div>`).join('');
 return `<div class="incident"><b>${esc(i.title)} – ${esc(i.address)}</b>${rows}${isLs?`<div class="row"><input data-newsection="${esc(i.id)}" placeholder="Neuer Abschnitt, z. B. Brandbekämpfung"><button data-addsection="${esc(i.id)}">Abschnitt erstellen</button></div><div class="row"><select data-secvehicle="${esc(i.id)}"><option value="">Alarmiertes Fahrzeug wählen</option>${vehicles.map(v=>`<option value="${esc(v.id)}">${esc(v.call)}</option>`).join('')}</select><select data-secname="${esc(i.id)}">${opts}</select><button data-assignsection="${esc(i.id)}">Zuweisen</button></div>`:''}</div>`;
 }).join('')||'<p class="small">Noch keine offenen Einsätze.</p>';
 $('sectionsList').querySelectorAll('[data-addsection]').forEach(b=>b.onclick=()=>send('section_add',{incident:b.dataset.addsection,section:$('sectionsList').querySelector(`[data-newsection="${b.dataset.addsection}"]`).value}));
 $('sectionsList').querySelectorAll('[data-assignsection]').forEach(b=>b.onclick=()=>{let id=b.dataset.assignsection;send('section_assign',{incident:id,vehicle:$('sectionsList').querySelector(`[data-secvehicle="${id}"]`).value,section:$('sectionsList').querySelector(`[data-secname="${id}"]`).value})});
 $('sectionsList').querySelectorAll('[data-setleader]').forEach(b=>b.onclick=()=>{let id=b.dataset.setleader,section=b.dataset.section;let sel=Array.from($('sectionsList').querySelectorAll('[data-leader]')).find(e=>e.dataset.leader===id&&e.dataset.section===section);send('section_leader',{incident:id,section,leader:sel.value})});
}
['vehicleSearch','unitFilter','incidentFilter'].forEach(id=>$(id).addEventListener(id==='vehicleSearch'?'input':'change',()=>render()));
$('refreshList').onclick=()=>render();
setInterval(async()=>{if(!me||busy||pendingActions)return;busy=true;const revision=stateRevision;try{let x=await api('state');if(serverDown){serverDown=false;notice('')}if(revision!==stateRevision)return;setState(x.state);soundsFromState(state);render()}catch(e){if(e.restarting){serverDown=true;$('connection').textContent='Server startet neu …';$('connection').dataset.state='error';notice(RESTARTING);return}$('connection').textContent='Verbindung unterbrochen';$('connection').dataset.state='error';if(e.kicked||/Sitzung abgelaufen|Raum nicht gefunden/.test(String(e.message)))leaveRoom(e.message)}finally{busy=false}},1500);
