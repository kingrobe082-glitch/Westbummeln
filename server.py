from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from threading import RLock
from pathlib import Path
import json, time, secrets, re, os
import accounts
import backup
import discord_bridge as discord
from urllib.parse import parse_qs
from threading import BoundedSemaphore
from collections import deque

auth_slots = BoundedSemaphore(4)
auth_attempts = deque()
ROOT=Path(__file__).parent
lock=RLock(); rooms={}
# Koordinaten beziehen sich auf die vollständige Originalkarte inklusive Legende.
BASE={1:(.235,.55),2:(.466,.51),3:(.565,.215),4:(.827,.46),5:(.548,.80),6:(.276,.15)}
FLEET=[{'id':f'WB-{i}-{kind.replace(" ","")}', 'call':f'Florian WB {i} {kind}', 'unit':i,'kind':kind,'seats':3 if kind=='KdoW' else 9,'base':BASE[i]} for i in range(1,7) for kind in ('HLF 20','KdoW','LF 20')]
# Straßenpositionen wurden anhand der vom Spieler gelieferten Karte bestimmt.
PLACES=[('Hauptstraße',.39,.53),('Marktplatz',.41,.65),('Schulstraße',.59,.38),('Waldstraße',.28,.19),('Dorfstraße',.56,.85),('Nelkenweg',.77,.51),('Mathias-Berg-Straße',.75,.59),('Robin-Hof-Straße',.77,.69),('Werkstraße',.86,.86),('Buchenstraße',.92,.52),('Eichenstraße',.37,.23),('Bachstraße',.34,.84),('Flurstraße',.69,.26),('Tannenweg',.87,.32),('Ahornallee',.91,.39),('Kreuzbergstraße',.82,.20),('Jägerstraße',.215,.36),('Scheunenweg',.51,.25),('Blütenstraße',.35,.29),('Sportplatzring',.32,.39),('Kirchstraße',.56,.58),('Rosenstraße',.49,.65),('Sonnenstraße',.55,.68),('Mozartweg',.91,.69),('Uferstraße',.43,.85),('Mühlenweg',.29,.87),('Gartenweg',.32,.94),('Wiesenstraße',.34,.985),('Bummelbachweg',.51,.93),('Dorflick',.69,.94),('Bürgerstraße',.63,.92),('Forstweg',.38,.09),('Feldweg',.74,.10),('Am Rathauspark',.32,.70),('Erlenstraße',.92,.60)]
# Feuerwachen und Gerätehäuser dürfen keine Einsatzorte sein.
STATIONS=[*BASE.values(),(.38,.16),(.90,.37),(.88,.23),(.27,.84),(.92,.84)]
OFFLINE_TIMEOUT=30

def clean_offline(r,now):
 changed=False
 for pid,p in list(r['players'].items()):
  if now-p['last']<=OFFLINE_TIMEOUT:continue
  if r['dispatcher']==pid:r['dispatcher']=None
  if r['admin']==pid:r['admin']=next((other for other in r['players'] if other!=pid),None)
  if p['vehicle'] and p['vehicle'] in r['vehicles']:
   r['vehicles'][p['vehicle']]['owner']=None
  del r['players'][pid]
  r['voice_messages']=[m for m in r['voice_messages'] if m['from']!=pid and m['to']!=pid]
  emit(r,'System',f'{p["name"]} wegen Verbindungsverlust entfernt (30 Sekunden offline).')
  changed=True
 if changed:r['rev']+=1

def locate(address):
 a=address.lower()
 for name,x,y in PLACES:
  if name.lower() in a:return [x,y]
 raise ValueError('Straße nicht bekannt – bitte einen Ort aus der Karte wählen')

def safe_location(pos):
 return all((pos[0]-x)**2+(pos[1]-y)**2 >= .027**2 for x,y in STATIONS)

def room(code):
 if code not in rooms:rooms[code]={'code':code,'players':{},'vehicles':{v['id']:{**v,'owner':None,'status':2,'incident':None,'phase':'wache','phase_at':0} for v in FLEET},'incidents':[],'radio':[],'rev':0,'dispatcher':None,'ai_last':0,'ai_seq':0,'voice_messages':[],'voice_seq':0,'admin':None,'channels':['Leitstelle','Einsatzstelle','Abschnitt 1','Abschnitt 2','Abschnitt 3'],'roles':{'leitstelle':True,'gf':True},'weather_mode':'auto','weather':'Sonnig','weather_at':0,'weather_history':[]}
 return rooms[code]
def emit(r,author,message,kind='auto',call=None):
 entry={'time':time.strftime('%H:%M:%S'),'author':author,'message':message[:400],'kind':kind}
 if call:entry['call']=call
 r['radio'].append(entry);r['radio']=r['radio'][-100:]
 if kind!='discord' and author!='Wetterdienst':discord.post_radio(r.get('code'),entry)
def from_discord(name,text):
 with lock:
  r=room(discord.ROOM);emit(r,name+' (Discord)',text,kind='discord');r['rev']+=1
def ai_mode(r):
 return len(r['players'])==1

def ai_dispatch(r,inc,v,now):
 if v['phase']!='wache' or v['status']==6 or v['incident']:return False
 if v['id'] not in inc['assigned']:inc['assigned'].append(v['id'])
 inc.setdefault('sections',{'Hauptabschnitt':{'leader':'KI-Einsatzleitung','vehicles':[]}})['Hauptabschnitt']['vehicles'].append(v['id'])
 v.update(phase='anfahrt',phase_at=now,status=3,incident=inc['id'])
 emit(r,'KI-Leitstelle',f'Alarm {v["call"]}: {inc["title"]}, {inc["address"]}.')
 return True

def run_ai(r,now):
 if not ai_mode(r):return False
 human=next(iter(r['players'].values()))
 changed=False
 # Ohne menschliche Leitstelle übernimmt die KI die Alarmierung und neue Einsätze.
 if human['role']!='ls':
  if now-r['ai_last']>=45 and len([i for i in r['incidents'] if not i['closed']])<2:
   locations=[(name,x,y) for name,x,y in PLACES if safe_location((x,y))]
   if locations:
    name,x,y=locations[r['ai_seq']%len(locations)]
    title=['F1 · Kleinbrand','TH1 · Verkehrsunfall','F2 · Wohnungsbrand','BMA · Brandmeldeanlage'][r['ai_seq']%4]
    inc={'id':secrets.token_hex(4),'title':title,'address':name,'pos':[x,y],'creator':'KI-Leitstelle','created':time.strftime('%H:%M:%S'),'closed':False,'assigned':[],'working':False,'progress':0,'updated':now,'sections':{'Hauptabschnitt':{'leader':'KI-Einsatzleitung','vehicles':[]}}}
    r['incidents'].append(inc);r['ai_last']=now;r['ai_seq']+=1;emit(r,'KI-Leitstelle',f'Neuer Einsatz: {title} – {name}.');changed=True
  for inc in r['incidents']:
   if inc['closed']:continue
   if not inc['assigned']:
    owned=r['vehicles'].get(human['vehicle']) if human['vehicle'] else None
    if owned and ai_dispatch(r,inc,owned,now):changed=True
    elif not owned:
     v=next((v for v in r['vehicles'].values() if not v['owner'] and v['phase']=='wache' and v['kind']!='KdoW'),None)
     if v and ai_dispatch(r,inc,v,now):changed=True
 # KI-Fahrzeugführer übernehmen Maßnahmen selbst, wenn kein menschlicher GF am Einsatz arbeitet.
 for inc in r['incidents']:
  if inc['closed'] or inc['working']:continue
  ai_on_site=[r['vehicles'][vid] for vid in inc['assigned'] if vid in r['vehicles'] and r['vehicles'][vid]['phase']=='vorort' and not r['vehicles'][vid]['owner']]
  if ai_on_site:
   inc['working']=True;inc['updated']=now;emit(r,'KI-Gruppenführer',f'{inc["title"]}: Mannschaft beginnt Maßnahmen.');changed=True
 return changed

def travel_time(r):
 return {'Sonnig':12,'Bewölkt':13,'Regen':17,'Nebel':20,'Windig':15}.get(r['weather'],12)

def weather_work_factor(r):
 return {'Sonnig':1,'Bewölkt':1,'Regen':.85,'Nebel':.8,'Windig':.9}.get(r['weather'],1)

def update(r):
 now=time.time(); changed=run_ai(r,now)
 if r['weather_mode']=='auto' and now-r['weather_at']>150:
  choices=['Sonnig','Bewölkt','Regen','Nebel','Windig'];r['weather']=choices[int(now//150)%len(choices)];r['weather_at']=now;emit(r,'Wetterdienst',f'Wetterwechsel: {r["weather"]}.');changed=True
 for v in r['vehicles'].values():
  phase=v['phase'];elapsed=now-v['phase_at'];inc=next((i for i in r['incidents'] if i['id']==v['incident']),None)
  if phase=='anfahrt' and elapsed>=travel_time(r):
   v.update(phase='vorort',phase_at=now,status=4);emit(r,v['call'],'Status 4 – Einsatzstelle erreicht.');changed=True
  elif phase=='rueckfahrt' and elapsed>=travel_time(r):
   v.update(phase='wache',phase_at=now,status=2,incident=None);emit(r,v['call'],'Status 2 – wieder einsatzbereit auf Wache.');changed=True
 for inc in r['incidents']:
  if inc['closed']:continue
  if inc['working']:
   active=[r['vehicles'][vid] for vid in inc['assigned'] if vid in r['vehicles'] and r['vehicles'][vid]['phase']=='vorort']
   if active:
    inc['progress']=min(100,inc['progress']+(now-inc.get('updated',now))*min(3.5,1.2+len(active)*.55)*weather_work_factor(r));changed=True
    for section in inc.get('sections',{}).values():
     present=sum(1 for vid in section['vehicles'] if vid in r['vehicles'] and r['vehicles'][vid]['phase']=='vorort')
     if present:
      section['progress']=min(100,section.get('progress',0)+(now-inc.get('updated',now))*min(3,0.8+present*.55)*weather_work_factor(r))
   inc['updated']=now
   if inc['progress']>=100:
    inc['closed']=True;inc['progress']=100;emit(r,'Leitstelle',f'Einsatz {inc["title"]} abgearbeitet – Rückfahrt eingeleitet.')
    for vid in inc['assigned']:
     v=r['vehicles'].get(vid)
     if v and v['incident']==inc['id']:v.update(phase='rueckfahrt',phase_at=now,status=1)
    changed=True
 if changed:r['rev']+=1

def snapshot(r):
 return {'players':[{'id':p['id'],'name':p['name'],'vehicle':p['vehicle'],'role':p['role']} for p in r['players'].values()],'vehicles':list(r['vehicles'].values()),'incidents':r['incidents'][-40:],'radio':r['radio'][-100:],'rev':r['rev'],'dispatcher':r['dispatcher'],'ai_mode':ai_mode(r),'admin':r['admin'],'channels':r['channels'],'roles':r['roles'],'weather':r['weather'],'weather_mode':r['weather_mode'],'travel_time':travel_time(r),'work_factor':weather_work_factor(r)}
class Handler(BaseHTTPRequestHandler):
 def reply(self,status,obj,cookies=()):
  b=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)))
  for cookie in cookies:self.send_header('Set-Cookie',cookie)
  self.end_headers();self.wfile.write(b)
 def do_GET(self):
  path=self.path.split('?',1)[0]
  if path=='/account':
   account=accounts.current_account(self.headers.get('Cookie'))
   name=account[1] if account else None
   nonce=secrets.token_urlsafe(24) if accounts.GOOGLE_CLIENT_ID and not name else ''
   cookies=[accounts.make_cookie('wb_google_nonce',nonce,600,self.secure_request())] if nonce else []
   return self.reply(200,{'name':name,'googleClientId':accounts.GOOGLE_CLIENT_ID,'nonce':nonce,'developer':bool(account and account[2]),**discord.public_config(bool(name))},cookies)
  if path=='/auth/discord':return self.discord_start()
  if path=='/auth/discord/callback':return self.discord_callback(parse_qs(self.path.partition('?')[2]))
  if path=='/developer':
   account=accounts.current_account(self.headers.get('Cookie'))
   if not account or not account[2]:
    return self.reply(403,{'error':'Entwicklerzugang erforderlich.'})
   with lock:
    now=time.time()
    active_rooms=0
    active_players=0
    for current_room in rooms.values():
     active=sum(now-player['last']<=30 for player in current_room['players'].values())
     active_rooms+=bool(active)
     active_players+=active
   return self.reply(200,{'rooms':active_rooms,'players':active_players})
  assets={
   '/':'text/html; charset=utf-8',
   '/index.html':'text/html; charset=utf-8',
   '/karte.webp':'image/webp',
   '/manifest.webmanifest':'application/manifest+json',
   '/sw.js':'text/javascript; charset=utf-8',
   '/icon-192.png':'image/png',
   '/icon-512.png':'image/png',
  }
  mime=assets.get(path)
  if not mime:return self.reply(404,{'error':'Nicht gefunden'})
  file='index.html' if path=='/' else path[1:]
  try:content=(ROOT/file).read_bytes()
  except FileNotFoundError:return self.reply(404,{'error':'Nicht gefunden'})
  self.send_response(200)
  self.send_header('Content-Type',mime)
  self.send_header('Cache-Control','no-cache')
  self.send_header('Content-Length',str(len(content)))
  self.end_headers()
  self.wfile.write(content)
 def redirect(self,url,cookies=()):
  self.send_response(302);self.send_header('Location',url);self.send_header('Cache-Control','no-store');self.send_header('Content-Length','0')
  for cookie in cookies:self.send_header('Set-Cookie',cookie)
  self.end_headers()
 def discord_start(self):
  if not discord.login_enabled():return self.redirect('/?login_error=off')
  state=secrets.token_urlsafe(24)
  target=discord.authorize_url(state,discord.redirect_uri(self.headers.get('Host','localhost'),self.secure_request()))
  return self.redirect(target,[accounts.make_cookie(discord.STATE_COOKIE,state,600,self.secure_request())])
 def discord_callback(self,query):
  secure=self.secure_request();clear=accounts.make_cookie(discord.STATE_COOKIE,'',0,secure)
  def back(code):return self.redirect('/?login_error='+code,[clear])
  if not discord.login_enabled():return back('off')
  code=(query.get('code') or [''])[0];state=(query.get('state') or [''])[0]
  if 'error' in query and not code:return back('cancel')
  expected=accounts.cookie_value(self.headers.get('Cookie'),discord.STATE_COOKIE)
  if not code or not state or not expected or not secrets.compare_digest(state,expected):return back('state')
  now=time.monotonic()
  with lock:
   while auth_attempts and now-auth_attempts[0]>=60:auth_attempts.popleft()
   if len(auth_attempts)>=90:return back('failed')
   auth_attempts.append(now)
  try:user=discord.complete_login(code,discord.redirect_uri(self.headers.get('Host','localhost'),secure))
  except discord.LoginError as error:return back(error.code)
  try:name,token=accounts.login_discord(user,self.headers.get('Cookie'))
  except ValueError:return back('failed')
  backup.mark_dirty()
  return self.redirect('/',[accounts.make_cookie(accounts.COOKIE,token,accounts.LIFETIME,secure),clear])
 def secure_request(self):
  return self.headers.get('X-Forwarded-Proto','').split(',')[0].strip()=='https' or bool(os.environ.get('RENDER'))

 def account_request(self):
  if self.headers.get_content_type()!='application/json':
   return self.reply(415,{'error':'JSON erforderlich'})
  size=int(self.headers.get('Content-Length','0'))
  if not 0<size<=12000:raise ValueError('Ungültige Anfragegröße')
  data=json.loads(self.rfile.read(size))
  action=data.get('action')
  if action not in ('register','login','google','logout'):raise ValueError('Unbekannte Kontoaktion')
  if action!='logout':
   now=time.monotonic()
   with lock:
    while auth_attempts and now-auth_attempts[0]>=60:auth_attempts.popleft()
    if len(auth_attempts)>=90:
     return self.reply(429,{'error':'Zu viele Anmeldeversuche. Bitte warte kurz.'})
    auth_attempts.append(now)
  if not auth_slots.acquire(blocking=False):
   return self.reply(429,{'error':'Bitte versuche es gleich erneut.'})
  try:
   name,token=accounts.authenticate(action,data,self.headers.get('Cookie'))
  finally:
   auth_slots.release()
  secure=self.secure_request()
  cookies=[accounts.make_cookie(accounts.COOKIE,token,accounts.LIFETIME if token else 0,secure)]
  if action=='google':cookies.append(accounts.make_cookie('wb_google_nonce','',0,secure))
  if action in ('register','google'):backup.mark_dirty()
  return self.reply(200,{'name':name},cookies)

 def do_POST(self):
  try:
   if self.path=='/account':return self.account_request()
   if self.path!='/api':return self.reply(404,{'error':'Nicht gefunden'})
   if self.headers.get_content_type()!='application/json':
    return self.reply(415,{'error':'JSON erforderlich'})
   size=int(self.headers.get('Content-Length','0'))
   if not 0<size<=12000:raise ValueError('Anfrage zu groß')
   data=json.loads(self.rfile.read(size));code=str(data.get('room','WB')).upper().strip()
   if not re.fullmatch(r'[A-Z0-9-]{2,16}',code):raise ValueError('Ungültiger Raumcode')
   action=data.get('action');now=time.time()
   account=accounts.current_account(self.headers.get('Cookie'))
   if not account:
    return self.reply(401,{'error':'Sitzung abgelaufen – bitte anmelden.'})
   account_id,account_name,is_developer=account
   with lock:
    r=room(code);clean_offline(r,now);update(r)
    if action=='join':
     name=account_name;pid=secrets.token_urlsafe(18)
     if not r['admin']:r['admin']=pid
     r['players'][pid]={'id':pid,'account':account_id,'name':name,'vehicle':None,'role':'none','last':now};emit(r,'System',f'{name} ist beigetreten.');r['rev']+=1
     return self.reply(200,{'id':pid,'state':snapshot(r)})
    pid=str(data.get('id',''));p=r['players'].get(pid)
    if not p or p['account']!=account_id:raise ValueError('Sitzung abgelaufen – bitte neu beitreten')
    p['last']=now
    if action=='state':return self.reply(200,{'state':snapshot(r)})
    if action=='settings':
     if pid!=r['admin']:raise ValueError('Nur die Raumverwaltung darf Einstellungen ändern')
     kind=str(data.get('kind',''))
     if kind=='vehicle':
      v=r['vehicles'].get(str(data.get('vehicle','')))
      if not v:raise ValueError('Fahrzeug fehlt')
      call=str(data.get('call','')).strip()[:55];seats=int(data.get('seats',9))
      if not call or not 1<=seats<=12:raise ValueError('Ungültige Fahrzeugdaten')
      v['call']=call;v['seats']=seats
     elif kind=='channels':
      channels=data.get('channels')
      if not isinstance(channels,list) or not 1<=len(channels)<=8:raise ValueError('1–8 Kanäle erforderlich')
      channels=[str(c).strip()[:35] for c in channels]
      if not all(channels) or len(set(channels))!=len(channels):raise ValueError('Kanalnamen ungültig')
      r['channels']=channels
     elif kind=='roles':
      role=str(data.get('role',''));enabled=data.get('enabled')
      if role not in r['roles'] or not isinstance(enabled,bool):raise ValueError('Rolle ungültig')
      r['roles'][role]=enabled
     elif kind=='weather':
      mode=str(data.get('mode',''));weather=str(data.get('weather',''))
      if mode not in ('auto','manual') or weather not in ('Sonnig','Bewölkt','Regen','Nebel','Windig'):raise ValueError('Wetter ungültig')
      r['weather_mode']=mode;r['weather']=weather;r['weather_at']=now
     else:raise ValueError('Unbekannte Einstellung')
     emit(r,'System','Raumeinstellungen aktualisiert.');r['rev']+=1
     return self.reply(200,{'state':snapshot(r)})
    if action=='voice_signal':
     target=str(data.get('to',''))
     payload=data.get('signal')
     if target not in r['players'] or target==pid:raise ValueError('Empfänger nicht online')
     if not isinstance(payload,dict) or payload.get('type') not in ('offer','answer','candidate','bye','channel'):raise ValueError('Ungültiges Funksignal')
     if len(json.dumps(payload))>9000:raise ValueError('Signal zu groß')
     r['voice_seq']+=1
     r['voice_messages'].append({'seq':r['voice_seq'],'from':pid,'to':target,'signal':payload})
     r['voice_messages']=r['voice_messages'][-350:]
     return self.reply(200,{'ok':True})
    if action=='voice_poll':
     since=max(0,int(data.get('since',0)))
     messages=[m for m in r['voice_messages'] if m['to']==pid and m['seq']>since]
     return self.reply(200,{'messages':messages,'seq':r['voice_seq'],'players':snapshot(r)['players']})
    if action=='take_ls':
     if not r['roles']['leitstelle']:raise ValueError('Leitstellenrolle gesperrt')
     if p['role']=='gf':raise ValueError('Bitte zuerst das Fahrzeug verlassen')
     previous_id=r['dispatcher']
     if previous_id==pid:return self.reply(200,{'state':snapshot(r)})
     if previous_id:
      if not is_developer or data.get('replace_dispatcher')!=previous_id:
       raise ValueError('Leitstelle ist bereits besetzt')
      previous=r['players'][previous_id]
      previous['role']='none'
      message=f'{p["name"]} übernimmt die Leitstelle von {previous["name"]}.'
     else:
      message=f'{p["name"]} übernimmt die Leitstelle.'
     r['dispatcher']=pid;p['role']='ls';emit(r,'System',message)
    elif action=='leave_ls':
     if r['dispatcher']!=pid:raise ValueError('Du besetzt die Leitstelle nicht')
     r['dispatcher']=None;p['role']='none';emit(r,'System',f'{p["name"]} verlässt die Leitstelle.')
    elif action=='claim':
     if not r['roles']['gf']:raise ValueError('GF-Rolle gesperrt')
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
     pos=locate(address)
     if not safe_location(pos):raise ValueError('An dieser Stelle liegt eine Feuerwache oder ein Gerätehaus – anderen Einsatzort wählen')
     inc={'id':secrets.token_hex(4),'title':title,'address':address,'pos':pos,'creator':p['name'],'created':time.strftime('%H:%M:%S'),'closed':False,'assigned':[],'working':False,'progress':0,'updated':now,'sections':{'Hauptabschnitt':{'leader':'KI-Einsatzleitung','vehicles':[]}}}
     r['incidents'].append(inc);emit(r,'Leitstelle',f'Neuer Einsatz: {title} – {address}.')
    elif action=='dispatch':
     if r['dispatcher']!=pid:raise ValueError('Nur die besetzte Leitstelle darf diese Aktion ausführen')
     inc=next((x for x in r['incidents'] if x['id']==str(data.get('incident',''))),None);v=r['vehicles'].get(str(data.get('vehicle','')))
     if not inc or inc['closed'] or not v:raise ValueError('Einsatz oder Fahrzeug nicht verfügbar')
     if not v['owner'] and not ai_mode(r):raise ValueError('Fahrzeug muss von einem Spieler besetzt sein (oder KI-Modus aktiv)')
     if v['phase']!='wache' or v['status']==6 or v['incident']:raise ValueError('Fahrzeug ist nicht frei')
     if v['id'] not in inc['assigned']:inc['assigned'].append(v['id'])
     inc.setdefault('sections',{'Hauptabschnitt':{'leader':'KI-Einsatzleitung','vehicles':[]}})['Hauptabschnitt']['vehicles'].append(v['id'])
     v.update(phase='anfahrt',phase_at=now,status=3,incident=inc['id']);emit(r,'Leitstelle',f'Alarm {v["call"]}: {inc["title"]}, {inc["address"]}.')
    elif action=='section_add':
     if r['dispatcher']!=pid:raise ValueError('Nur die Leitstelle kann Einsatzabschnitte anlegen')
     inc=next((x for x in r['incidents'] if x['id']==str(data.get('incident',''))),None)
     if not inc or inc['closed']:raise ValueError('Einsatz nicht verfügbar')
     name=str(data.get('section','')).strip()[:35]
     if not name:raise ValueError('Abschnittsname fehlt')
     sections=inc.setdefault('sections',{'Hauptabschnitt':{'leader':'KI-Einsatzleitung','vehicles':[]}})
     if name in sections or len(sections)>=6:raise ValueError('Abschnitt existiert bereits oder Maximum erreicht')
     sections[name]={'leader':'KI-Abschnittsleitung','vehicles':[],'progress':0};emit(r,'Einsatzleitung',f'{inc["title"]}: Abschnitt {name} eingerichtet.')
    elif action=='section_assign':
     if r['dispatcher']!=pid:raise ValueError('Nur die Leitstelle kann Fahrzeuge zuweisen')
     inc=next((x for x in r['incidents'] if x['id']==str(data.get('incident',''))),None)
     if not inc or inc['closed']:raise ValueError('Einsatz nicht verfügbar')
     vid=str(data.get('vehicle',''));name=str(data.get('section',''))
     sections=inc.setdefault('sections',{'Hauptabschnitt':{'leader':'KI-Einsatzleitung','vehicles':[]}})
     if name not in sections or vid not in inc['assigned']:raise ValueError('Abschnitt oder Fahrzeug nicht verfügbar')
     for section in sections.values():
      if vid in section['vehicles']:section['vehicles'].remove(vid)
     sections[name]['vehicles'].append(vid)
     emit(r,'Einsatzleitung',f'{r["vehicles"][vid]["call"]} Abschnitt {name} zugewiesen.')
    elif action=='section_leader':
     if r['dispatcher']!=pid:raise ValueError('Nur die Leitstelle darf Abschnittsleiter bestimmen')
     inc=next((x for x in r['incidents'] if x['id']==str(data.get('incident',''))),None)
     if not inc or inc['closed']:raise ValueError('Einsatz nicht verfügbar')
     sections=inc.setdefault('sections',{'Hauptabschnitt':{'leader':'KI-Einsatzleitung','vehicles':[]}})
     name=str(data.get('section',''));leader=str(data.get('leader',''))
     if name not in sections:raise ValueError('Abschnitt nicht vorhanden')
     if leader!='KI-Abschnittsleitung' and not any(p['name']==leader and p['role']=='gf' for p in r['players'].values()):raise ValueError('Nur aktive Gruppenführer können Abschnittsleiter sein')
     sections[name]['leader']=leader;emit(r,'Einsatzleitung',f'Abschnitt {name}: Leitung {leader}.')
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
     sent=p.setdefault('radio_times',deque())
     while sent and now-sent[0]>10:sent.popleft()
     if len(sent)>=5:raise ValueError('Bitte warte kurz, bevor du den nächsten Funkspruch sendest.')
     sent.append(now)
     vehicle=r['vehicles'].get(p['vehicle']) if p['vehicle'] else None
     emit(r,p['name'],msg,kind='funk',call=vehicle['call'] if vehicle else None)
    else:raise ValueError('Unbekannte Aktion')
    r['rev']+=1;self.reply(200,{'state':snapshot(r)})
  except (ValueError,KeyError,TypeError,json.JSONDecodeError) as e:self.reply(400,{'error':str(e)})
  except Exception:self.reply(500,{'error':'Serverfehler'})
 def log_message(self,*args):pass
if __name__=='__main__':
 backup.start()
 discord.start(from_discord)
 accounts.provision_developer()
 accounts.provision_test_account()
 backup.mark_dirty()
 port=int(os.environ.get('PORT','8765'));print('Westbummeln auf Port',port,flush=True);ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
