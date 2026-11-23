from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from threading import RLock
from pathlib import Path
import json, time, secrets, re, os

ROOT=Path(__file__).parent
lock=RLock()
rooms={}
FLEET=[{'id':f'WB-{i}-{kind.replace(" ","")}', 'call':f'Florian WB {i} {kind}', 'unit':i,'kind':kind,'seats':3 if kind=='KdoW' else 9} for i in range(1,7) for kind in ('HLF 20','KdoW','LF 20')]
def room(code):
    if code not in rooms:
        rooms[code]={'players':{},'vehicles':{v['id']:{**v,'owner':None,'status':2} for v in FLEET},'incidents':[],'radio':[],'rev':0}
    return rooms[code]
def snapshot(r):
    return {'players':[{'id':p['id'],'name':p['name'],'vehicle':p['vehicle']} for p in r['players'].values()], 'vehicles':list(r['vehicles'].values()),'incidents':r['incidents'][-40:],'radio':r['radio'][-100:],'rev':r['rev']}
def emit(r,author,message):
    r['radio'].append({'time':time.strftime('%H:%M:%S'),'author':author,'message':message[:400]});r['radio']=r['radio'][-100:]
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
    if self.path=='/' or self.path.startswith('/?'):
        b=(ROOT/'index.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    else:self.reply(404,{'error':'Nicht gefunden'})
 def reply(self,status,obj):
    b=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_POST(self):
    try:
        length=int(self.headers.get('Content-Length','0'))
        if length>12000:raise ValueError('Anfrage zu groß')
        data=json.loads(self.rfile.read(length));code=str(data.get('room','WB')).upper().strip()
        if not re.fullmatch(r'[A-Z0-9-]{2,16}',code):raise ValueError('Ungültiger Raumcode')
        action=data.get('action');now=time.time()
        with lock:
            r=room(code)
            if action=='join':
                name=str(data.get('name','Spieler')).strip()[:24] or 'Spieler'
                pid=secrets.token_urlsafe(18);r['players'][pid]={'id':pid,'name':name,'vehicle':None,'last':now};emit(r,'System',f'{name} ist beigetreten.');r['rev']+=1
                self.reply(200,{'id':pid,'state':snapshot(r)});return
            pid=str(data.get('id',''));p=r['players'].get(pid)
            if not p:raise ValueError('Sitzung abgelaufen – bitte neu beitreten')
            p['last']=now
            if action=='state':self.reply(200,{'state':snapshot(r)});return
            if action=='claim':
                vid=str(data.get('vehicle',''));v=r['vehicles'].get(vid)
                if not v:raise ValueError('Fahrzeug nicht gefunden')
                if v['owner'] and v['owner']!=pid:raise ValueError('Dieses Fahrzeug ist bereits besetzt')
                if p['vehicle'] and r['vehicles'][p['vehicle']]['status'] in (3,4):raise ValueError('Fahrzeugwechsel während Einsatz nicht möglich')
                if p['vehicle']:r['vehicles'][p['vehicle']]['owner']=None
                v['owner']=pid;p['vehicle']=vid;emit(r,'System',f'{p["name"]} besetzt {v["call"]}.')
            elif action=='release':
                if p['vehicle']:
                    v=r['vehicles'][p['vehicle']]
                    if v['status'] in (3,4):raise ValueError('Im Einsatz nicht aussteigen')
                    v['owner']=None;p['vehicle']=None;emit(r,'System',f'{p["name"]} hat {v["call"]} verlassen.')
            elif action=='status':
                if not p['vehicle']:raise ValueError('Bitte zuerst Fahrzeug besetzen')
                v=r['vehicles'][p['vehicle']];status=int(data.get('status',0))
                if status not in (1,2,3,4,5,6):raise ValueError('Ungültiger Status')
                v['status']=status;emit(r,v['call'],f'Status {status} gemeldet von {p["name"]}.')
            elif action=='incident':
                title=str(data.get('title','')).strip()[:90];address=str(data.get('address','')).strip()[:120]
                if not title or not address:raise ValueError('Stichwort und Einsatzort erforderlich')
                inc={'id':secrets.token_hex(4),'title':title,'address':address,'creator':p['name'],'created':time.strftime('%H:%M:%S'),'closed':False,'assigned':[]}
                r['incidents'].append(inc);emit(r,'Leitstelle',f'Neuer Einsatz: {title} – {address}.')
            elif action=='dispatch':
                iid=str(data.get('incident',''));vid=str(data.get('vehicle',''));inc=next((x for x in r['incidents'] if x['id']==iid),None);v=r['vehicles'].get(vid)
                if not inc or inc['closed'] or not v:raise ValueError('Einsatz oder Fahrzeug nicht verfügbar')
                if not v['owner']:raise ValueError('Fahrzeug muss durch einen Spieler besetzt sein')
                if v['status'] in (3,4,6):raise ValueError('Fahrzeug ist nicht verfügbar')
                if vid not in inc['assigned']:inc['assigned'].append(vid)
                emit(r,'Leitstelle',f'Alarm für {v["call"]}: {inc["title"]}, {inc["address"]}.')
            elif action=='close':
                inc=next((x for x in r['incidents'] if x['id']==str(data.get('incident',''))),None)
                if not inc:raise ValueError('Einsatz nicht gefunden')
                inc['closed']=True;emit(r,'Leitstelle',f'Einsatz {inc["title"]} abgeschlossen.')
            elif action=='radio':
                msg=str(data.get('message','')).strip()[:400]
                if not msg:raise ValueError('Funkspruch ist leer')
                emit(r,p['name'],msg)
            else:raise ValueError('Unbekannte Aktion')
            r['rev']+=1;self.reply(200,{'state':snapshot(r)})
    except (ValueError,KeyError,TypeError,json.JSONDecodeError) as e:self.reply(400,{'error':str(e)})
    except Exception as e:self.reply(500,{'error':'Serverfehler'})
 def log_message(self,*args):pass
if __name__=='__main__':
 port=int(os.environ.get('PORT','8765'))
 print(f'Westbummeln Multiplayer gestartet auf Port {port}',flush=True)
 ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
