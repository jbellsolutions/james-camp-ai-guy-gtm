#!/usr/bin/env python3
"""Authenticated internal normalized intake on localhost."""
import argparse,hmac,json,os
from http.server import BaseHTTPRequestHandler,HTTPServer
from workflow import connect,ingest

def handler(db,token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            if self.path!='/events':self.send_error(404);return
            if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):self.send_error(401);return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if size<=0 or size>262144:self.send_error(413);return
                e=json.loads(self.rfile.read(size));c=connect(db)
                try:result=ingest(c,e)
                finally:c.close()
            except (ValueError,UnicodeError):self.send_error(400,'Invalid envelope');return
            body=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    return Handler

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--port',type=int,default=8765);a=p.parse_args();token=os.environ.get('GTM_INGRESS_TOKEN','')
    if len(token)<32:raise SystemExit('Private GTM_INGRESS_TOKEN of at least 32 characters required')
    HTTPServer(('127.0.0.1',a.port),handler(a.db,token)).serve_forever()
