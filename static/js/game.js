let incidentMarkup = '';
let fmeKey = '';
let fmeAcknowledged = false;

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
  $('fmePanel').classList.toggle('hidden', !incident);
  $('fmeMessage').textContent = incident
    ? [vehicle.call, incident.title, incident.address].join(' · ')
    : '';
  $('fmeAcknowledge').disabled = !incident;
  if (incident) {
    beep(1060, .16, 0, 'sine', .18);
    beep(1400, .16, .20, 'sine', .18);
    beep(1060, .16, .40, 'sine', .18);
    beep(1400, .30, .60, 'sine', .18);
  }
}

$('fmeAcknowledge').onclick = () => {
  if (!fmeKey || fmeAcknowledged) return;
  fmeAcknowledged = true;
  $('fmeAcknowledge').disabled = true;
  $('fmeMessage').textContent += ' · Quittiert';
};

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

let me=null,state=null,room='',busy=false,focusIncident='';let pendingActions=0,stateRevision=0;const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const labels={1:'Frei über Funk',2:'Auf Wache',3:'Anfahrt',4:'Einsatzstelle',5:'Sprechwunsch',6:'Nicht einsatzbereit'};function notice(s){$('notice').textContent=s}async function api(action,data={}){let res=await fetch('/api',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrfToken()},body:JSON.stringify({action,room,id:me,...data})});let obj=await res.json();if(!res.ok){let err=Error(obj.error||'Serverfehler');err.kicked=Boolean(obj.kicked);throw err}return obj}async function send(action,data={}){pendingActions++;stateRevision++;try{let x=await api(action,data);if(x.state){state=x.state;soundsFromState(state);render()}notice('')}catch(e){if(e.kicked)leaveRoom(e.message);else notice(e.message)}finally{pendingActions--}}
// Raum betreten: 'create_room' (Server vergibt den Code) oder 'join' mit eingegebenem Code.
async function enterRoom(action){try{if(action==='join'){room=$('room').value.toUpperCase().trim();if(!room)throw Error('Bitte gib einen Raumcode ein.')}else room='';let x=await api(action);if(x.room)room=x.room;$('room').value=room;me=x.id;state=x.state;soundsFromState(state);$('login').classList.add('hidden');['rolesPanel','dashboard','mapPanel','incidentsPanel','vehiclesPanel','controlPanel','sectionsPanel','radioPanel','voicePanel'].forEach(id=>$(id).classList.remove('hidden'));notice('');setNotice('');render()}catch(e){notice(e.message)}}
$('join').onclick=()=>enterRoom('join');$('createRoom').onclick=()=>enterRoom('create_room');$('room').onkeydown=e=>{if(e.key==='Enter')$('join').click()};
// Zurück zum Startbildschirm (Sitzung abgelaufen, Raum weg oder von der Raumverwaltung entfernt).
function leaveRoom(message){if(typeof voiceStream!=='undefined'&&voiceStream)voiceLeave();me=null;state=null;$('login').classList.remove('hidden');['rolesPanel','dashboard','mapPanel','incidentsPanel','vehiclesPanel','controlPanel','sectionsPanel','radioPanel','voicePanel'].forEach(id=>$(id).classList.add('hidden'));$('fmePanel').classList.add('hidden');fmeKey='';$('connection').textContent='Nicht verbunden';$('connection').style.color='';loadAccount().catch(error=>setNotice(error.message,'error'));notice(message);setNotice(message,'error')}
$('copyCode').onclick=async()=>{try{await navigator.clipboard.writeText(room);notice('Raumcode '+room+' kopiert.')}catch(e){getSelection().selectAllChildren($('roomCode'));notice('Kopieren nicht möglich – der Code ist markiert, kopiere ihn mit Strg+C: '+room)}};
function renderRoomAdmin(){let owner=state.admin===me&&!state.permanent;$('roomCode').textContent=state.code||room;$('roomOwner').textContent=state.permanent?'Öffentlicher Discord-Raum':owner?'Du verwaltest diesen Raum.':'Raumverwaltung: '+(state.owner_name||'–')+(state.admin?'':' (gerade offline)');
$('players').innerHTML=state.players.map(p=>`<div class="item">${esc(p.name)}${p.id===state.admin?' 👑':''} · ${esc(state.vehicles.find(v=>v.id===p.vehicle)?.call||(p.role==='ls'?'Leitstelle':'Keine Rolle'))}${owner&&p.id!==me?`<div class="playerActions"><button data-kick="${esc(p.id)}">Entfernen</button><button class="danger" data-ban="${esc(p.id)}">Entfernen & sperren</button><button data-owner="${esc(p.id)}">Besitz übertragen</button></div>`:''}</div>`).join('');
let banned=owner?state.banned||[]:[];$('bannedList').classList.toggle('hidden',!banned.length);$('bannedList').innerHTML=banned.length?'<h3>🚫 Gesperrt</h3>'+banned.map(b=>`<div class="item">${esc(b.name)} <button data-unban="${esc(b.account)}">Sperre aufheben</button></div>`).join(''):'';
const nameOf=id=>state.players.find(p=>p.id===id)?.name||'';
$('players').querySelectorAll('[data-kick]').forEach(b=>b.onclick=()=>{if(confirm(nameOf(b.dataset.kick)+' aus dem Raum entfernen?'))send('kick',{target:b.dataset.kick})});
$('players').querySelectorAll('[data-ban]').forEach(b=>b.onclick=()=>{if(confirm(nameOf(b.dataset.ban)+' entfernen und für diesen Raum sperren?'))send('kick',{target:b.dataset.ban,ban:true})});
$('players').querySelectorAll('[data-owner]').forEach(b=>b.onclick=()=>{if(confirm('Raumverwaltung an '+nameOf(b.dataset.owner)+' übertragen? Du verlierst die Verwaltungsrechte.'))send('transfer_owner',{target:b.dataset.owner})});
$('bannedList').querySelectorAll('[data-unban]').forEach(b=>b.onclick=()=>send('unban',{account:b.dataset.unban}))}
$('takeLs').onclick=()=>send('take_ls', {
  replace_dispatcher: developerAccount ? state?.dispatcher : null
});$('leaveLs').onclick=()=>send('leave_ls');$('goGf').onclick=()=>{$('vehiclesPanel').scrollIntoView({behavior:'smooth'})};$('create').onclick=()=>send('incident',{title:$('title').value,address:$('address').value});$('send').onclick=()=>{let msg=$('message').value;if(msg.trim())send('radio',{message:msg});$('message').value=''};$('message').onkeydown=e=>{if(e.key==='Enter')$('send').click()};$('release').onclick=()=>send('release');
function position(v){let inc=state.incidents.find(i=>i.id===v.incident);let base=v.base;if(!inc)return base;let d=Math.min(1,(Date.now()/1000-v.phase_at)/12);if(v.phase==='anfahrt')return [base[0]+(inc.pos[0]-base[0])*d,base[1]+(inc.pos[1]-base[1])*d];if(v.phase==='rueckfahrt')return [inc.pos[0]+(base[0]-inc.pos[0])*d,inc.pos[1]+(base[1]-inc.pos[1])*d];return inc.pos}
function renderMap(){let pins=[];for(let i of state.incidents.filter(i=>!i.closed)){pins.push(`<button class="pin ${focusIncident===i.id?'selected':''}" title="${esc(i.title)}" data-pin="${esc(i.id)}" style="left:${i.pos[0]*100}%;top:${i.pos[1]*100}%">!</button>`)}for(let v of state.vehicles.filter(v=>v.phase!=='wache')){let p=position(v);pins.push(`<span class="pin vehicle" title="${esc(v.call)} – ${esc(v.phase)}" style="left:${p[0]*100}%;top:${p[1]*100}%"></span>`)}$('markers').innerHTML=pins.join('');$('markers').querySelectorAll('[data-pin]').forEach(b=>b.onclick=()=>{focusIncident=b.dataset.pin;render();document.getElementById('inc-'+focusIncident)?.scrollIntoView({behavior:'smooth',block:'center'})})}
function render(){if(!state)return;
updateFme(state);
$('countOpen').textContent=state.incidents.filter(i=>!i.closed).length;
$('countFree').textContent=state.vehicles.filter(v=>v.phase==='wache'&&v.status!==6).length;
$('countDrive').textContent=state.vehicles.filter(v=>v.phase==='anfahrt').length;
$('countSite').textContent=state.vehicles.filter(v=>v.phase==='vorort').length;$('connection').textContent=`🟢 ${room} · ${state.players.length} Spieler`;
let p=state.players.find(p=>p.id===me),isLs=p?.role==='ls',isGf=p?.role==='gf',lsOwner=state.players.find(x=>x.id===state.dispatcher);$('roleInfo').textContent=isLs?'Du besetzt die Leitstelle. Nur du kannst Einsätze erstellen, alarmieren und beenden.':isGf?'Du bist Gruppenführer. Fahrzeugstatus und Einsatzmaßnahmen gehören zu deiner Rolle.':lsOwner?'Leitstelle besetzt durch '+lsOwner.name+'. Du kannst ein Fahrzeug übernehmen.':'Leitstelle noch frei. Du kannst die Leitstelle oder ein Fahrzeug übernehmen.';$('takeLs').disabled=isLs||isGf||(!developerAccount&&!!lsOwner);
$('takeLs').textContent=developerAccount&&lsOwner&&!isLs
  ? '📞 Besetzte Leitstelle übernehmen'
  : '📞 Leitstelle übernehmen';$('leaveLs').disabled=!isLs;$('goGf').disabled=isLs;$('incidentsPanel').classList.remove('hidden');$('incidentsPanel').querySelectorAll('.quick, .screen-title, #title, #address, #create').forEach(el=>el.classList.toggle('hidden',!isLs));$('vehiclesPanel').classList.toggle('hidden',isLs);$('controlPanel').classList.toggle('hidden',!isGf);$('dashboard').classList.toggle('hidden',!isLs);$('create').disabled=!isLs;let mine=state.vehicles.find(v=>v.id===p?.vehicle);$('myVehicle').innerHTML=mine?`<b>${esc(mine.call)}</b><p>Status ${mine.status} · ${esc(labels[mine.status])} · ${esc(mine.phase)}</p>`:'Noch kein Fahrzeug besetzt';$('statuses').innerHTML=Object.entries(labels).map(([n,t])=>`<button data-status="${n}" class="${mine?.status==n?'active':''}" ${!mine?'disabled':''}>${n} · ${esc(t)}</button>`).join('');$('statuses').querySelectorAll('button').forEach(b=>b.onclick=()=>send('status',{status:Number(b.dataset.status)}));$('release').disabled=!mine||mine.phase!=='wache';
$('vehicles').innerHTML=state.vehicles.filter(v=>( $('unitFilter').value==='all'||String(v.unit)===$('unitFilter').value )&&v.call.toLowerCase().includes($('vehicleSearch').value.trim().toLowerCase())).map(v=>{let owner=state.players.find(p=>p.id===v.owner);return `<div class="item"><b>${esc(v.call)}</b> <span class="pill">${v.status}</span><div class="small">${owner?'Besetzt: '+esc(owner.name):'GF-/Führungsplatz frei'} · ${v.seats} Plätze · ${esc(v.phase)}</div><button data-vehicle="${esc(v.id)}" ${isLs||(owner&&owner.id!==me)||v.phase!=='wache'?'disabled':''}>${owner?.id===me?'Dein Fahrzeug':'Übernehmen'}</button></div>`}).join('');$('vehicles').querySelectorAll('[data-vehicle]').forEach(b=>b.onclick=()=>send('claim',{vehicle:b.dataset.vehicle}));renderRoomAdmin();
updateIncidents(state.incidents.filter(i=>$('incidentFilter').value==='all'||($('incidentFilter').value==='closed'?i.closed:!i.closed)).slice().reverse().map(i=>{let assigned=i.assigned.map(id=>state.vehicles.find(v=>v.id===id)).filter(Boolean);let arrived=assigned.some(v=>v.phase==='vorort');return `<div class="incident" id="inc-${esc(i.id)}"><b>${esc(i.title)}</b> <span class="pill ${i.closed?'green':''}">${i.closed?'Abgeschlossen':i.working?'In Bearbeitung':'Offen'}</span><div class="small">📍 ${esc(i.address)} · ${esc(i.created)}</div><div class="small">Alarmiert: ${assigned.map(v=>esc(v.call)+' (S'+v.status+')').join(', ')||'Noch keine Fahrzeuge'}</div><div class="progress"><span style="width:${i.progress}%"></span></div><div class="small">Fortschritt: ${Math.round(i.progress)} % ${i.working?'· Mannschaft arbeitet':''}</div>${i.closed?'':`<div class="row" ${!isLs?'style="display:none"':''}><select data-for="${esc(i.id)}" ${!isLs?'disabled':''}><option value="">Fahrzeug wählen</option>${state.vehicles.filter(v=>(v.owner||state.ai_mode)&&v.phase==='wache'&&v.status!==6).map(v=>`<option value="${esc(v.id)}">${esc(v.call)}</option>`).join('')}</select><button data-dispatch="${esc(i.id)}" ${!isLs?'disabled':''}>Alarmieren</button></div><div class="row"><button data-work="${esc(i.id)}" ${!isGf||!mine||!i.assigned.includes(mine.id)||mine.phase!=='vorort'||i.working?'disabled':''}>${i.working?'Arbeiten laufen':'Maßnahmen starten'}</button>${isLs?`<button data-close="${esc(i.id)}">Einsatz beenden</button>`:''}</div>`}</div>`}).join(''));$('incidents').querySelectorAll('[data-dispatch]').forEach(b=>b.onclick=()=>{let id=b.dataset.dispatch,v=$('incidents').querySelector(`select[data-for="${id}"]`).value;if(!v){notice('Bitte zuerst ein verfügbares Fahrzeug auswählen.');return}send('dispatch',{incident:id,vehicle:v})});$('incidents').querySelectorAll('[data-work]').forEach(b=>b.onclick=()=>send('work',{incident:b.dataset.work}));$('incidents').querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>send('close',{incident:b.dataset.close}));let log=$('log'),atBottom=log.scrollTop+log.clientHeight>=log.scrollHeight-35;log.innerHTML=state.radio.filter(x=>{const rf=$('radioFilter').value,talk=x.kind==='funk'||x.kind==='discord';return rf==='all'||(rf==='funk'?talk:!talk)}).map(x=>`<div class="item radio-${esc(x.kind||'auto')}"><span class="small">${esc(x.time)} · ${x.kind==='discord'?'💬 ':x.kind==='funk'?'📻 ':''}${esc(x.author)}${x.call?' · '+esc(x.call):''}</span><div>${esc(x.message)}</div></div>`).join('');if(atBottom)log.scrollTop=log.scrollHeight;renderMap();renderSections()}

function renderSections(){
 const own=state.players.find(p=>p.id===me),isLs=own?.role==='ls';
 $('sectionsPanel').classList.remove('hidden'); const overlay=$('weatherOverlay');if(overlay)overlay.className=({Regen:'rain',Nebel:'fog',Windig:'wind'})[state.weather]||'';
 $('aiInfo').textContent=state.ai_mode?(isLs?'🤖 KI-Gruppenführer aktiv: Unbesetzte Fahrzeuge können alarmiert werden und arbeiten selbstständig.':'🤖 KI-Leitstelle aktiv: Sie erstellt Einsätze und alarmiert Fahrzeuge automatisch.'):'👥 Multiplayer: KI-Automatik pausiert, solange mehrere Spieler online sind.';
 $('aiInfo').textContent += ` · 🌦 ${state.weather} · Fahrzeit ca. ${state.travel_time||12}s · Arbeitsfaktor ${Math.round((state.work_factor||1)*100)}%`; $('sectionsList').innerHTML=state.incidents.filter(i=>!i.closed).map(i=>{
 const sections=i.sections||{'Hauptabschnitt':{leader:'KI-Einsatzleitung',vehicles:[]}};
 const opts=Object.keys(sections).map(n=>`<option value="${esc(n)}">${esc(n)}</option>`).join('');
 const vehicles=i.assigned.map(id=>state.vehicles.find(v=>v.id===id)).filter(Boolean);
 const rows=Object.entries(sections).map(([name,sec])=>`<div class="item"><b>${esc(name)}</b> · Leitung: ${esc(sec.leader)} · ${Math.round(sec.progress||0)} %<div class="progress"><span style="width:${Math.round(sec.progress||0)}%"></span></div><div class="small">Fahrzeuge: ${sec.vehicles.map(id=>esc(state.vehicles.find(v=>v.id===id)?.call||id)).join(', ')||'Keine'}</div>${isLs?`<div class="row"><select data-leader="${esc(i.id)}" data-section="${esc(name)}"><option value="KI-Abschnittsleitung">KI-Abschnittsleitung</option>${state.players.filter(p=>p.role==='gf').map(p=>`<option value="${esc(p.name)}" ${p.name===sec.leader?'selected':''}>${esc(p.name)}</option>`).join('')}</select><button data-setleader="${esc(i.id)}" data-section="${esc(name)}">Leitung zuweisen</button></div>`:''}</div>`).join('');
 return `<div class="incident"><b>${esc(i.title)} – ${esc(i.address)}</b>${rows}${isLs?`<div class="row"><input data-newsection="${esc(i.id)}" placeholder="Neuer Abschnitt, z. B. Brandbekämpfung"><button data-addsection="${esc(i.id)}">Abschnitt erstellen</button></div><div class="row"><select data-secvehicle="${esc(i.id)}"><option value="">Alarmiertes Fahrzeug wählen</option>${vehicles.map(v=>`<option value="${esc(v.id)}">${esc(v.call)}</option>`).join('')}</select><select data-secname="${esc(i.id)}">${opts}</select><button data-assignsection="${esc(i.id)}">Zuweisen</button></div>`:''}</div>`;
 }).join('')||'<p class="small">Noch keine offenen Einsätze.</p>';
 $('sectionsList').querySelectorAll('[data-addsection]').forEach(b=>b.onclick=()=>send('section_add',{incident:b.dataset.addsection,section:$('sectionsList').querySelector(`[data-newsection="${b.dataset.addsection}"]`).value}));
 $('sectionsList').querySelectorAll('[data-assignsection]').forEach(b=>b.onclick=()=>{let id=b.dataset.assignsection;send('section_assign',{incident:id,vehicle:$('sectionsList').querySelector(`[data-secvehicle="${id}"]`).value,section:$('sectionsList').querySelector(`[data-secname="${id}"]`).value})});
 $('sectionsList').querySelectorAll('[data-setleader]').forEach(b=>b.onclick=()=>{let id=b.dataset.setleader,section=b.dataset.section;let sel=Array.from($('sectionsList').querySelectorAll('[data-leader]')).find(e=>e.dataset.leader===id&&e.dataset.section===section);send('section_leader',{incident:id,section,leader:sel.value})});
}
$('quickKeywords').querySelectorAll('button').forEach(b=>b.onclick=()=>{$('title').value=b.dataset.keyword;$('address').focus()});
['vehicleSearch','unitFilter','incidentFilter'].forEach(id=>$(id).addEventListener(id==='vehicleSearch'?'input':'change',()=>render()));
$('refreshList').onclick=()=>render();
setInterval(async()=>{if(!me||busy||pendingActions)return;busy=true;const revision=stateRevision;try{let x=await api('state');if(revision!==stateRevision)return;state=x.state;soundsFromState(state);render();$('connection').style.color='#a5e7b5'}catch(e){$('connection').textContent='Verbindung unterbrochen';$('connection').style.color='#ffb2a2';if(e.kicked||/Sitzung abgelaufen|Raum nicht gefunden/.test(String(e.message)))leaveRoom(e.message)}finally{busy=false}},1500);
