from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from threading import RLock
from pathlib import Path
import json, time, secrets, re, os
ROOT=Path(__file__).parent
lock=RLock(); rooms={}
BASE={1:(.245,.54),2:(.47,.51),3:(.55,.21),4:(.82,.46),5:(.54,.79),6:(.26,.15)}
FLEET=[{'id':f'WB-{i}-{kind.replace(" ","")}', 'call':f'Florian WB {i} {kind}', 'unit':i,'kind':kind,'seats':3 if kind=='KdoW' else 9,'base':BASE[i]} for i in range(1,7) for kind in ('HLF 20','KdoW','LF 20')]
PLACES=[('Hauptstraße',.37,.52),('Marktplatz',.39,.62),('Schulstraße',.58,.37),('Waldstraße',.30,.19),('Dorfstraße',.55,.81),('Nelkenweg',.77,.49),('Mathias-Berg-Straße',.74,.57),('Robin-Hof-Straße',.77,.66),('Werkstraße',.87,.82),('Buchenstraße',.92,.49),('Eichenstraße',.39,.22),('Bachstraße',.35,.82)]
def locate(address):
 a=address.lower()
 for name,x,y in PLACES:
  if name.lower() in a:return [x,y]
 return [.49,.46]
def room(code):
 if code not in rooms:rooms[code]={'players':{},'vehicles':{v['id']:{**v,'owner':None,'status':2,'incident':None,'phase':'wache','phase_at':0} for v in FLEET},'incidents':[],'radio':[],'rev':0,'dispatcher':None}
 return rooms[code]
def emit(r,author,message):
 r['radio'].append({'time':time.strftime('%H:%M:%S'),'author':author,'message':message[:400]});r['radio']=r['radio'][-100:]
def update(r):
 now=time.time(); changed=False
 for v in r['vehicles'].values():
  phase=v['phase'];elapsed=now-v['phase_at'];inc=next((i for i in r['incidents'] if i['id']==v['incident']),None)
  if phase=='anfahrt' and elapsed>=12:
   v.update(phase='vorort',phase_at=now,status=4);emit(r,v['call'],'Status 4 – Einsatzstelle erreicht.');changed=True
  elif phase=='rueckfahrt' and elapsed>=12:
   v.update(phase='wache',phase_at=now,status=2,incident=None);emit(r,v['call'],'Status 2 – wieder einsatzbereit auf Wache.');changed=True
 for inc in r['incidents']:
  if inc['closed']:continue
  if inc['working']:
   active=[r['vehicles'][vid] for vid in inc['assigned'] if vid in r['vehicles'] and r['vehicles'][vid]['phase']=='vorort']
   if active:
    inc['progress']=min(100,inc['progress']+(now-inc.get('updated',now))*min(3.5,1.2+len(active)*.55));changed=True
   inc['updated']=now
   if inc['progress']>=100:
    inc['closed']=True;inc['progress']=100;emit(r,'Leitstelle',f'Einsatz {inc["title"]} abgearbeitet – Rückfahrt eingeleitet.')
    for vid in inc['assigned']:
     v=r['vehicles'].get(vid)
     if v and v['incident']==inc['id']:v.update(phase='rueckfahrt',phase_at=now,status=1)
    changed=True
 if changed:r['rev']+=1

def snapshot(r):
 return {'players':[{'id':p['id'],'name':p['name'],'vehicle':p['vehicle'],'role':p['role']} for p in r['players'].values()],'vehicles':list(r['vehicles'].values()),'incidents':r['incidents'][-40:],'radio':r['radio'][-100:],'rev':r['rev'],'dispatcher':r['dispatcher']}
class Handler(BaseHTTPRequestHandler):
 def reply(self,status,obj):
  b=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_GET(self):
  file='index.html' if self.path in ('/','/index.html') or self.path.startswith('/?') else 'karte.webp' if self.path=='/karte.webp' else None
  if not file:return self.reply(404,{'error':'Nicht gefunden'})
  b=(ROOT/file).read_bytes();self.send_response(200);self.send_header('Content-Type','image/webp' if file.endswith('.webp') else 'text/html; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_POST(self):
  try:
   size=int(self.headers.get('Content-Length','0'))
   if size>12000:raise ValueError('Anfrage zu groß')
   data=json.loads(self.rfile.read(size));code=str(data.get('room','WB')).upper().strip()
   if not re.fullmatch(r'[A-Z0-9-]{2,16}',code):raise ValueError('Ungültiger Raumcode')
   action=data.get('action');now=time.time()
   with lock:
    r=room(code);update(r)
    if action=='join':
     name=str(data.get('name','Spieler')).strip()[:24] or 'Spieler';pid=secrets.token_urlsafe(18)
     r['players'][pid]={'id':pid,'name':name,'vehicle':None,'role':'none','last':now};emit(r,'System',f'{name} ist beigetreten.');r['rev']+=1
     return self.reply(200,{'id':pid,'state':snapshot(r)})
    pid=str(data.get('id',''));p=r['players'].get(pid)
    if not p:raise ValueError('Sitzung abgelaufen – bitte neu beitreten')
    p['last']=now
    if action=='state':return self.reply(200,{'state':snapshot(r)})
    if action=='take_ls':
     if p['role']=='gf':raise ValueError('Bitte zuerst das Fahrzeug verlassen')
     if r['dispatcher'] and r['dispatcher']!=pid:raise ValueError('Leitstelle ist bereits besetzt')
     r['dispatcher']=pid;p['role']='ls';emit(r,'System',f'{p["name"]} übernimmt die Leitstelle.')
    elif action=='leave_ls':
     if r['dispatcher']!=pid:raise ValueError('Du besetzt die Leitstelle nicht')
     r['dispatcher']=None;p['role']='none';emit(r,'System',f'{p["name"]} verlässt die Leitstelle.')
    elif action=='claim':
     if p['role']=='ls':raise ValueError('Leitstelle zuerst verlassen')
     v=r['vehicles'].get(str(data.get('vehicle','')))
     if not v:raise ValueError('Fahrzeug fehlt')
     if v['owner'] and v['owner']!=pid:raise ValueError('Fahrzeug ist bereits besetzt')
     if p['vehicle'] and r['vehicles'][p['vehicle']]['phase']!='wache':raise ValueError('Wechsel nur auf Wache möglich')
     if v['phase']!='wache':raise ValueError('Fahrzeug ist unterwegs')
     if p['vehicle']:r['vehicles'][p['vehicle']]['owner']=None
     v['owner']=pid;p['vehicle']=v['id'];p['role']='gf';emit(r,'System',f'{p["name"]} besetzt {v["call"]}.')
    elif action=='release':
     if p['vehicle']:
      v=r['vehicles'][p['vehicle']]
      if v['phase']!='wache':raise ValueError('Im Einsatz nicht aussteigen')
      v['owner']=None;p['vehicle']=None;p['role']='none';emit(r,'System',f'{p["name"]} verlässt {v["call"]}.')
    elif action=='status':
     if p['role']!='gf' or not p['vehicle']:raise ValueError('Bitte Fahrzeug übernehmen')
     v=r['vehicles'][p['vehicle']];status=int(data.get('status',0))
     if status not in range(1,7):raise ValueError('Ungültiger Status')
     if v['phase']!='wache' and status in (2,6):raise ValueError('Status während Einsatz gesperrt')
     if v['phase']=='wache' and status in (3,4):raise ValueError('Status 3/4 erfolgt durch Einsatzfahrt')
     v['status']=status;emit(r,v['call'],f'Status {status} – {p["name"]}.')
    elif action=='incident':
     if r['dispatcher']!=pid:raise ValueError('Nur die besetzte Leitstelle darf diese Aktion ausführen')
     title=str(data.get('title','')).strip()[:90];address=str(data.get('address','')).strip()[:120]
     if not title or not address:raise ValueError('Stichwort und Einsatzort erforderlich')
     inc={'id':secrets.token_hex(4),'title':title,'address':address,'pos':locate(address),'creator':p['name'],'created':time.strftime('%H:%M:%S'),'closed':False,'assigned':[],'working':False,'progress':0,'updated':now}
     r['incidents'].append(inc);emit(r,'Leitstelle',f'Neuer Einsatz: {title} – {address}.')
    elif action=='dispatch':
     if r['dispatcher']!=pid:raise ValueError('Nur die besetzte Leitstelle darf diese Aktion ausführen')
     inc=next((x for x in r['incidents'] if x['id']==str(data.get('incident',''))),None);v=r['vehicles'].get(str(data.get('vehicle','')))
     if not inc or inc['closed'] or not v:raise ValueError('Einsatz oder Fahrzeug nicht verfügbar')
     if not v['owner']:raise ValueError('Fahrzeug muss von einem Spieler besetzt sein')
     if v['phase']!='wache' or v['status']==6 or v['incident']:raise ValueError('Fahrzeug ist nicht frei')
     if v['id'] not in inc['assigned']:inc['assigned'].append(v['id'])
     v.update(phase='anfahrt',phase_at=now,status=3,incident=inc['id']);emit(r,'Leitstelle',f'Alarm {v["call"]}: {inc["title"]}, {inc["address"]}.')
    elif action=='work':
     if p['role']!='gf' or not p['vehicle']:raise ValueError('Nur ein GF am Einsatzort kann Maßnahmen starten')
     inc=next((x for x in r['incidents'] if x['id']==str(data.get('incident',''))),None)
     if not inc or inc['closed']:raise ValueError('Einsatz nicht verfügbar')
     if p['vehicle'] not in inc['assigned'] or r['vehicles'][p['vehicle']]['phase']!='vorort':raise ValueError('Zuerst muss ein Fahrzeug die Einsatzstelle erreichen')
     inc['working']=True;inc['updated']=now;emit(r,'Einsatzleitung',f'{inc["title"]}: Maßnahmen eingeleitet.')
    elif action=='close':
     if r['dispatcher']!=pid:raise ValueError('Nur die besetzte Leitstelle darf diese Aktion ausführen')
     inc=next((x for x in r['incidents'] if x['id']==str(data.get('incident',''))),None)
     if not inc:raise ValueError('Einsatz nicht gefunden')
     inc.update(closed=True,progress=100)
     for vid in inc['assigned']:
      v=r['vehicles'].get(vid)
      if v and v['incident']==inc['id']:v.update(phase='rueckfahrt',phase_at=now,status=1)
     emit(r,'Leitstelle',f'Einsatz {inc["title"]} beendet, Rückfahrt.')
    elif action=='radio':
     msg=str(data.get('message','')).strip()[:400]
     if not msg:raise ValueError('Funkspruch leer')
     emit(r,p['name'],msg)
    else:raise ValueError('Unbekannte Aktion')
    r['rev']+=1;self.reply(200,{'state':snapshot(r)})
  except (ValueError,KeyError,TypeError,json.JSONDecodeError) as e:self.reply(400,{'error':str(e)})
  except Exception:self.reply(500,{'error':'Serverfehler'})
 def log_message(self,*args):pass
if __name__=='__main__':
 port=int(os.environ.get('PORT','8765'));print('Westbummeln auf Port',port,flush=True);ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
