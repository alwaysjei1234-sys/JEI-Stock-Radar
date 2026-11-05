"""Local synthetic retry experiment. Never calls an exchange or sends LINE.

Run from the repository root with standard-library Python:
    python docs/research/http-retry-boundary-20261106.py
The comparison wrapper is research only; JEI production code is unchanged.
An actual upstream HTTP 307 is not thereby proven to be a redirect loop.
"""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import hashlib
import json
from pathlib import Path
import sys
from threading import Thread
from unittest.mock import patch
import urllib.error
import urllib.request
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import update_system as jei


class Handler(BaseHTTPRequestHandler):
    counts={}
    def log_message(self,*args):pass
    def do_GET(self):
        self.counts[self.path]=self.counts.get(self.path,0)+1
        n=self.counts[self.path];status=200;location=None
        if self.path=='/loop':status=307;location='/loop'
        elif self.path=='/redirect':status=307;location='/ok'
        elif self.path=='/missing':status=404
        elif self.path=='/unavailable-always':status=503
        elif self.path=='/unavailable'and n==1:status=503
        elif self.path=='/rate'and n==1:status=429
        raw=b'{"synthetic":true}'if status==200 else b''
        self.send_response(status)
        if location:self.send_header('Location',location)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(raw)));self.end_headers()
        self.wfile.write(raw)


def research_wrapper(url):
    # Reuse the exact public-data fetch body once per attempt. This wrapper
    # deliberately explores a different retry decision, not a production fix.
    for attempt in range(3):
        try:return jei.fetch_json(url,tries=1)
        except Exception as error:
            if isinstance(error,urllib.error.HTTPError)and error.code not in (408,429)and not 500<=error.code<600:raise
            if attempt==2:raise
            jei.time.sleep(1.2*(attempt+1))


def run():
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    worker=Thread(target=server.serve_forever,daemon=True);worker.start()
    # A no-proxy opener is used only for this loopback fixture, never upstream.
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    result=[]
    try:
        for path in ('/loop','/missing','/rate','/unavailable','/unavailable-always','/redirect'):
            row={'scenario':path}
            for name,function in [('current_jei',jei.fetch_json),('research_wrapper',research_wrapper)]:
                Handler.counts.clear();waits=[];answer={}
                with patch.object(jei.urllib.request,'urlopen',opener.open),patch.object(jei.time,'sleep',waits.append):
                    try:answer={'outcome':'success','document':function('http://127.0.0.1:'+str(server.server_port)+path)}
                    except urllib.error.HTTPError as error:answer={'outcome':'http_error','http_status':error.code}
                row[name]={**answer,'http_requests':sum(Handler.counts.values()),
                           'backoff_seconds_requested':round(sum(waits),1)}
            a,b=row['current_jei'],row['research_wrapper']
            assert a['outcome']==b['outcome']
            assert a.get('http_status')==b.get('http_status')
            if path in ('/loop','/missing'):
                assert a['http_requests']>b['http_requests']
                assert a['backoff_seconds_requested']==3.6 and b['backoff_seconds_requested']==0
            else:
                assert a==b
            result.append(row)
    finally:
        server.shutdown();server.server_close();worker.join(timeout=2)
    return {'scope':'loopback_synthetic_only','python':sys.version.split()[0],
            'jei_source_sha256':hashlib.sha256((ROOT/'scripts/update_system.py').read_bytes()).hexdigest(),
            'scenarios':result,'all_assertions_passed':True,'product_changed':False,
            'real_market_latency_measured':False,'oos_trades_added':0,
            'limitations':['Real 307 cause and recoverability are unknown.',
                           'Requested waits are recorded with sleep suppressed, not wall-clock latency.',
                           'No price, availability or execution evidence is generated.',
                           'Do not change a registered strategy version on this experiment alone.']}


if __name__=='__main__':print(json.dumps(run(),ensure_ascii=False,indent=2))
