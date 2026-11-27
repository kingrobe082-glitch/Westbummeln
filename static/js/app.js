const $=id=>document.getElementById(id);
// Django-CSRF: Jeder POST schickt das Token aus dem Cookie csrftoken mit.
// Es wird bei jeder Anfrage neu gelesen, weil Django es nach dem Anmelden erneuert.
function csrfToken(){const m=document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);return m?decodeURIComponent(m[1]):''}
// Lokale WebAudio-Signale: Jeder Spieler aktiviert den Ton selbst.
let soundOn=false,audioCtx=null,previousSnapshot=null;
const soundButton=()=>document.getElementById('soundToggle');
// Die Wahl „Ton an/aus“ merkt sich der Browser (localStorage wb_sound). Browser erlauben Ton erst nach
// einem Klick: War der Ton an, schaltet ihn deshalb der erste Klick oder Tastendruck auf der Seite wieder ein.
const SOUND_KEY='wb_sound';
function rememberSound(on){try{localStorage.setItem(SOUND_KEY,on?'1':'0')}catch(e){/* Speicher gesperrt */}}
function soundWanted(){try{return localStorage.getItem(SOUND_KEY)!=='0'}catch(e){return true}}
function initAudio(silent){try{audioCtx=audioCtx||new (window.AudioContext||window.webkitAudioContext)();audioCtx.resume();soundOn=true;rememberSound(true);soundButton().textContent='Ton: an';soundButton().setAttribute('aria-pressed','true');if(!silent)tone('ready');document.dispatchEvent(new Event('wb:sound-on'))}catch(e){document.getElementById('notice').textContent='Audio wird von diesem Browser nicht unterstützt.'}}
soundButton().onclick=()=>{if(soundOn){soundOn=false;rememberSound(false);soundButton().textContent='Ton: aus';soundButton().setAttribute('aria-pressed','false')}else initAudio()};
if(soundWanted()){soundButton().textContent='Ton: an (Klick)';const wake=e=>{if(e.target?.closest?.('#soundToggle'))return;removeEventListener('pointerdown',wake,true);removeEventListener('keydown',wake,true);if(!soundOn&&soundWanted())initAudio(true)};addEventListener('pointerdown',wake,true);addEventListener('keydown',wake,true)}
function beep(freq,duration,offset=0,type='sine',level=.15){if(!soundOn||!audioCtx)return;let now=audioCtx.currentTime+offset,osc=audioCtx.createOscillator(),gain=audioCtx.createGain(),vol=Number(document.getElementById('volume').value)/100;osc.type=type;osc.frequency.setValueAtTime(freq,now);gain.gain.setValueAtTime(.0001,now);gain.gain.exponentialRampToValueAtTime(Math.max(.0002,level*vol),now+.012);gain.gain.exponentialRampToValueAtTime(.0001,now+duration);osc.connect(gain);gain.connect(audioCtx.destination);osc.start(now);osc.stop(now+duration+.02)}
function tone(kind){if(kind==='ready'){beep(660,.10);beep(880,.13,.14)}else if(kind==='alarm'){beep(780,.22,0,'square',.085);beep(520,.22,.25,'square',.085);beep(780,.22,.5,'square',.085);beep(520,.28,.75,'square',.085)}else if(kind==='radio'){beep(1250,.07);beep(960,.09,.1)}else if(kind==='status'){beep(880,.08);beep(1180,.10,.11)}else if(kind==='arrival'){beep(580,.11);beep(760,.14,.14)}else if(kind==='done'){beep(523,.12);beep(659,.12,.14);beep(784,.2,.29)}}
function soundsFromState(next){if(!next)return;if(previousSnapshot&&soundOn){let old=previousSnapshot;
const oldInc=new Map(old.incidents.map(i=>[i.id,i]));const oldVeh=new Map(old.vehicles.map(v=>[v.id,v]));
if(next.incidents.some(i=>!oldInc.has(i.id)))tone('alarm');
else if(next.incidents.some(i=>oldInc.has(i.id)&&!oldInc.get(i.id).closed&&i.closed))tone('done');
else if(next.vehicles.some(v=>oldVeh.has(v.id)&&oldVeh.get(v.id).phase!==v.phase&&v.phase==='vorort'))tone('arrival');
else if(next.vehicles.some(v=>oldVeh.has(v.id)&&oldVeh.get(v.id).status!==v.status))tone('status');
else if(next.radio.length>old.radio.length)tone('radio');}
previousSnapshot=JSON.parse(JSON.stringify(next));}
