// WebRTC-Sprachfunk: Audio nur nach Zustimmung und nur bei gedrückter Sprechtaste.
let voiceStream=null,voicePeers=new Map(),voiceRemoteChannels=new Map(),voiceSeq=0,voiceBusy=false,voiceChannel='leitstelle';
const voiceStatus=t=>{document.getElementById('voiceStatus').textContent=t};
async function voiceSignal(to,signal){try{await api('voice_signal',{to,signal})}catch(e){voiceStatus('Funkverbindung: '+e.message)}}
function voiceDrop(id){let entry=voicePeers.get(id);if(!entry)return;entry.pc.close();entry.audio.remove();voicePeers.delete(id)}
async function voiceConnect(id,offerer){if(voicePeers.has(id)||!voiceStream)return;
 const pc=new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});
 const audio=document.createElement('audio');audio.autoplay=true;audio.playsInline=true;document.getElementById('voiceAudio').appendChild(audio);
 voicePeers.set(id,{pc,audio,channel:voiceRemoteChannels.get(id)||null});
 for(const track of voiceStream.getTracks())pc.addTrack(track,voiceStream);
 pc.ontrack=e=>{audio.srcObject=e.streams[0];audio.muted=voicePeers.get(id)?.channel!==voiceChannel};
 pc.onicecandidate=e=>{if(e.candidate)voiceSignal(id,{type:'candidate',candidate:e.candidate.toJSON()})};
 pc.onconnectionstatechange=()=>{if(['failed','closed','disconnected'].includes(pc.connectionState)){voiceDrop(id)}};
 await voiceSignal(id,{type:'channel',channel:voiceChannel});
 if(offerer){let offer=await pc.createOffer();await pc.setLocalDescription(offer);await voiceSignal(id,{type:'offer',sdp:pc.localDescription.toJSON()})}
}
async function voiceHandle(m){let {from,signal}=m;if(!voiceStream)return;
 try{
 if(signal.type==='bye'){voiceDrop(from);return}
 if(signal.type==='channel'){voiceRemoteChannels.set(from,signal.channel);let e=voicePeers.get(from);if(e){e.channel=signal.channel;e.audio.muted=e.channel!==voiceChannel}return}
 if(signal.type==='offer'){voiceDrop(from);await voiceConnect(from,false);let pc=voicePeers.get(from).pc;await pc.setRemoteDescription(signal.sdp);let answer=await pc.createAnswer();await pc.setLocalDescription(answer);await voiceSignal(from,{type:'answer',sdp:pc.localDescription.toJSON()})}
 else if(signal.type==='answer'){let e=voicePeers.get(from);if(e)await e.pc.setRemoteDescription(signal.sdp)}
 else if(signal.type==='candidate'){let e=voicePeers.get(from);if(e){if(e.pc.remoteDescription)await e.pc.addIceCandidate(signal.candidate);else (e.pending??=[]).push(signal.candidate)}}
 let e=voicePeers.get(from);if(e?.pc.remoteDescription&&e.pending?.length){for(let c of e.pending.splice(0))await e.pc.addIceCandidate(c)}
 }catch(e){voiceStatus('Funkfehler: '+e.message)}
}
function voicePtt(on){if(!voiceStream)return;voiceStream.getAudioTracks().forEach(t=>t.enabled=on);let b=$('voicePtt');b.textContent=on?'🔴 SENDET – loslassen zum Beenden':'🎙️ Zum Sprechen gedrückt halten';b.style.background=on?'#a52732':''}
$('voiceJoin').onclick=async()=>{if(!me)return voiceStatus('Bitte zuerst dem Spiel beitreten');if(!window.isSecureContext)return voiceStatus('Für Mikrofonfunk HTTPS oder localhost erforderlich.');try{
 voiceStream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});voicePtt(false);$('voiceJoin').disabled=true;$('voiceLeave').disabled=false;$('voicePtt').disabled=false;voiceSeq=0;voiceStatus('Verbunden · Kanal '+$('voiceChannel').selectedOptions[0].text+' · Sprechtaste halten');
 }catch(e){voiceStatus('Mikrofon nicht verfügbar: '+e.message)}};
async function voiceLeave(){voicePtt(false);voiceRemoteChannels.clear();for(let id of voicePeers.keys())voiceSignal(id,{type:'bye'});for(let id of [...voicePeers.keys()])voiceDrop(id);voiceStream?.getTracks().forEach(t=>t.stop());voiceStream=null;$('voiceJoin').disabled=false;$('voiceLeave').disabled=true;$('voicePtt').disabled=true;voiceStatus('Sprachfunk aus')}
$('voiceLeave').onclick=voiceLeave;
$('voiceChannel').onchange=()=>{voiceChannel=$('voiceChannel').value;for(let [id,e] of voicePeers){e.audio.muted=e.channel!==voiceChannel;voiceSignal(id,{type:'channel',channel:voiceChannel})}voiceStatus('Kanal '+$('voiceChannel').selectedOptions[0].text+' ausgewählt')};
const ptt=$('voicePtt');ptt.addEventListener('pointerdown',e=>{e.preventDefault();ptt.setPointerCapture(e.pointerId);voicePtt(true)});for(let event of ['pointerup','pointercancel','lostpointercapture'])ptt.addEventListener(event,()=>voicePtt(false));window.addEventListener('blur',()=>voicePtt(false));
setInterval(async()=>{if(!me||!voiceStream||voiceBusy)return;voiceBusy=true;try{
 let x=await api('voice_poll',{since:voiceSeq});voiceSeq=x.seq;
 for(let m of x.messages)await voiceHandle(m);
 let live=new Set(x.players.filter(p=>p.id!==me).map(p=>p.id));for(let id of [...voicePeers.keys()])if(!live.has(id))voiceDrop(id);
 // Connect in stable ID order to prevent double offers.
 for(let id of live)if(me<id&&!voicePeers.has(id))await voiceConnect(id,true);
 $('voicePeers').textContent=voicePeers.size+' weitere Funkverbindung(en)';
 }catch(e){voiceStatus('Verbindung gestört: '+e.message)}finally{voiceBusy=false}},1700);
