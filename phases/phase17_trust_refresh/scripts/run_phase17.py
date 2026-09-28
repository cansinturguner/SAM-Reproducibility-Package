#!/usr/bin/env python3
from __future__ import annotations
import argparse, base64, csv, gzip, hashlib, hmac, json, math, os, platform, socket, socketserver, statistics, sys, threading, time
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature
import phase14_core as core

ORDER=int('FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551',16)

def material(seed):
    ca_s=1+(int.from_bytes(hashlib.sha256(f'ca:{seed}'.encode()).digest(),'big')%(ORDER-1))
    ac_s=1+(int.from_bytes(hashlib.sha256(f'ac:{seed}'.encode()).digest(),'big')%(ORDER-1))
    ca=ec.derive_private_key(ca_s,ec.SECP256R1()); ac=ec.derive_private_key(ac_s,ec.SECP256R1())
    pub=ac.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.CompressedPoint)
    record=b'SAM-AIRCRAFT-KEY-V1|'+pub; sig=ca.sign(record,ec.ECDSA(hashes.SHA256()))
    return ca.public_key(), record, sig, hashlib.sha256(pub).digest()

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        for line in self.rfile:
            q=json.loads(line)
            if self.server.outage_at is not None and float(q['sim_time'])>=self.server.outage_at:
                out={'available':False}
            else:
                time.sleep(self.server.delay_ms/1000.0)
                out={'available':True,'record':base64.b64encode(self.server.record).decode(),'signature':base64.b64encode(self.server.signature).decode()}
            self.wfile.write((json.dumps(out,separators=(',',':'))+'\n').encode()); self.wfile.flush()

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address=True
    daemon_threads=True

def lookup(f, sim_time, ca_pub):
    f.write((json.dumps({'aircraft':'prototype','sim_time':sim_time},separators=(',',':'))+'\n').encode()); f.flush()
    x=json.loads(f.readline())
    if not x['available']: return False
    record=base64.b64decode(x['record']); sig=base64.b64decode(x['signature'])
    try: ca_pub.verify(sig,record,ec.ECDSA(hashes.SHA256()))
    except InvalidSignature: return False
    return True

def run_once(a, delay_ms, outage_at):
    if not a.skip_hash_check and core.sha256_file(a.selected)!=a.expected_selected_sha256: raise SystemExit('selected hash mismatch')
    sensors=core.load_sensors(a.sensors); biases=core.load_biases(a.calibration); modeled=set(sensors)&set(biases)
    ca_pub,record,sig,root=material(a.seed)
    srv=Server(('127.0.0.1',0),Handler); srv.delay_ms=delay_ms; srv.outage_at=outage_at; srv.record=record; srv.signature=sig
    thread=threading.Thread(target=srv.serve_forever,daemon=True); thread.start()
    sock=socket.create_connection(srv.server_address); f=sock.makefile('rwb')
    counts={'eligible_rows':0,'physical_supported':0,'hmac_verified':0,'trust_verified':0,'trust_insufficient':0,'VERIFIED':0,'INSUFFICIENT_EVIDENCE':0,'CONFLICTING':0,'refresh_attempts':0,'refresh_successes':0,'refresh_failures':0}
    cache_time=None; next_retry_time=-math.inf; measured_wall=None; start=time.perf_counter()
    try:
      with gzip.open(a.selected,'rt',newline='',encoding='utf-8') as z:
       for row in csv.DictReader(z):
        if row['split'].strip().lower()!='test' or not core.truthy(row['eligible_ge4']): continue
        counts['eligible_rows']+=1; sim=float(row.get('timeAtServer') or 0.0)
        cache_valid=cache_time is not None and sim-cache_time<=a.cache_ttl_seconds
        if not cache_valid and sim>=next_retry_time:
            counts['refresh_attempts']+=1
            if lookup(f,sim,ca_pub):
                cache_time=sim; next_retry_time=-math.inf; counts['refresh_successes']+=1
            else:
                next_retry_time=sim+a.retry_interval_seconds; counts['refresh_failures']+=1
        trust='VERIFIED' if cache_time is not None and sim-cache_time<=a.cache_ttl_seconds else 'INSUFFICIENT_EVIDENCE'
        counts['trust_verified' if trust=='VERIFIED' else 'trust_insufficient']+=1
        msg=core.canonical_message(row); interval=int(sim)
        key=hmac.new(root,b'interval:'+interval.to_bytes(8,'big',signed=False),hashlib.sha3_256).digest()[:16]
        tag=hmac.new(key,msg,hashlib.sha3_256).digest()[:16]
        crypto='VERIFIED' if hmac.compare_digest(tag,hmac.new(key,msg,hashlib.sha3_256).digest()[:16]) else 'CONFLICTING'
        if crypto=='VERIFIED': counts['hmac_verified']+=1
        lat,lon=core.finite(row['latitude']),core.finite(row['longitude']); alt=core.finite(row['geoAltitude']) or core.finite(row['baroAltitude'])
        physical='INSUFFICIENT_EVIDENCE'
        if None not in (lat,lon,alt):
            try: ms=core.measurements(row['goodMeasurements'],modeled)
            except Exception: ms=[]
            if len(ms)>=4 and core.rank3([sensors[sid] for sid,_ in ms]): physical='VERIFIED'; counts['physical_supported']+=1
        state=core.fuse(crypto,physical,trust); counts[state]+=1
      measured_wall=time.perf_counter()-start
    finally:
      f.close(); sock.close(); srv.shutdown(); srv.server_close(); thread.join()
    return {'counts':counts,'wall_seconds':measured_wall}

def summary(v): return {'n':len(v),'mean':statistics.fmean(v),'median':statistics.median(v),'minimum':min(v),'maximum':max(v),'sample_stdev':statistics.stdev(v) if len(v)>1 else 0.0}

def main():
    p=argparse.ArgumentParser(); p.add_argument('--selected',type=Path,required=True); p.add_argument('--sensors',type=Path,required=True); p.add_argument('--calibration',type=Path,required=True); p.add_argument('--report',type=Path,required=True)
    p.add_argument('--seed',type=int,default=1103); p.add_argument('--repetitions',type=int,default=5); p.add_argument('--cache-ttl-seconds',type=float,default=900); p.add_argument('--retry-interval-seconds',type=float,default=60); p.add_argument('--expected-selected-sha256',default=core.EXPECTED_SELECTED_SHA256); p.add_argument('--skip-hash-check',action='store_true'); a=p.parse_args()
    scenarios=[('online_0ms',0,None),('online_50ms',50,None),('online_250ms',250,None),('outage_at_1800s',50,1800.0)]
    output=[]
    for name,delay,outage in scenarios:
        runs=[run_once(a,delay,outage) for _ in range(a.repetitions)]; base=runs[0]['counts']
        if any(x['counts']!=base for x in runs): raise SystemExit('non-deterministic counts')
        output.append({'name':name,'added_delay_ms':delay,'outage_at_seconds':outage,'counts':base,'wall_seconds':summary([x['wall_seconds'] for x in runs])})
    report={'schema':'sam.phase17.integrated-trust-refresh.v2','scope':{'implemented':'real LocaRDS physical path + deterministic HMAC + TCP signed trust refresh + cache + fusion','not_implemented':['authenticator captured from RF','TLS or X.509','global aviation PKI','ledger consensus','operational WAN','certified hardware','attack/anomaly classifier']},'platform':{'system':platform.system(),'release':platform.release(),'machine':platform.machine(),'python':platform.python_version(),'logical_cpu_count':os.cpu_count()},'configuration':{'seed':a.seed,'repetitions':a.repetitions,'cache_ttl_seconds':a.cache_ttl_seconds,'retry_interval_seconds':a.retry_interval_seconds,'refresh_rule':'refresh when cache is unavailable or older than TTL; back off after failure','service_delay':'controlled application delay over loopback','timing_boundary':'ends before server shutdown and thread-join cleanup'},'scenarios':output,'correctness':{'all_online_hmac_verified':all(x['counts']['hmac_verified']==x['counts']['eligible_rows'] for x in output[:3]),'frozen_eligible_count':output[0]['counts']['eligible_rows']==82986,'frozen_physical_count':output[0]['counts']['physical_supported']==78358,'outage_retry_backoff_active':output[3]['counts']['refresh_failures']<100},'interpretation_limits':['Trust delay is controlled over loopback, not operational WAN latency.','Authenticator is deterministic and synthetic but bound to each real observation.','Outage is a scheduled availability stress case, not an attack label.','Wall time excludes server shutdown and thread-join cleanup.','No precision, recall, F1, false-positive or false-negative result is produced.']}
    a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(report,indent=2))
if __name__=='__main__': main()
