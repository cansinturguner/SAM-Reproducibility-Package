#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, hmac, json, os, platform, resource, statistics, sys, time
from pathlib import Path
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature

VERIFIED='VERIFIED'; CONFLICTING='CONFLICTING'; INSUFFICIENT='INSUFFICIENT_EVIDENCE'
ORDER=int('FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551',16)

def key(seed,label):
    n=1+(int.from_bytes(hashlib.sha256(f'{label}:{seed}'.encode()).digest(),'big')%(ORDER-1))
    return ec.derive_private_key(n,ec.SECP256R1())
def raw_sign(k,data):
    r,s=decode_dss_signature(k.sign(data,ec.ECDSA(hashes.SHA256())))
    return r.to_bytes(32,'big')+s.to_bytes(32,'big')
def raw_verify(pub,sig,data):
    if len(sig)!=64:return False
    der=encode_dss_signature(int.from_bytes(sig[:32],'big'),int.from_bytes(sig[32:],'big'))
    try: pub.verify(der,data,ec.ECDSA(hashes.SHA256())); return True
    except InvalidSignature:return False
def fuse(crypto,physical,trust):
    if CONFLICTING in (crypto,physical,trust): return CONFLICTING
    if (crypto,physical,trust)==(VERIFIED,VERIFIED,VERIFIED): return VERIFIED
    return INSUFFICIENT
def peak_mib():
    v=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return v/(1024*1024) if sys.platform=='darwin' else v/1024
def summary(v):
    q=sorted(v)
    def pct(p):
        x=(len(q)-1)*p; a=int(x); b=min(a+1,len(q)-1); return q[a]*(b-x)+q[b]*(x-a)
    return {'n':len(v),'mean':statistics.fmean(v),'median':statistics.median(v),'q05':pct(.05),'q95':pct(.95),'minimum':min(v),'maximum':max(v),'sample_stdev':statistics.stdev(v) if len(v)>1 else 0.0}

def setup(seed):
    ca=key(seed,'ca'); ac=key(seed,'aircraft')
    ac_pub=ac.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.CompressedPoint)
    record=b'SAM-AIRCRAFT-KEY-V1|'+ac_pub; ca_sig=raw_sign(ca,record)
    interval_key=hashlib.sha3_256(f'interval:{seed}'.encode()).digest()[:16]
    b2=b'SAM-B2-V1|'+interval_key; b2_sig=raw_sign(ac,b2)
    message=hashlib.sha256(f'message:{seed}'.encode()).digest()[:14]; seq=7
    tag=hmac.new(interval_key,bytes([seq])+message,hashlib.sha3_256).digest()[:16]
    return {'ca':ca,'ac':ac,'record':record,'ca_sig':ca_sig,'interval_key':interval_key,'b2':b2,'b2_sig':b2_sig,'message':message,'seq':seq,'tag':tag}

def evaluate(name,x):
    msg=x['message']; tag=x['tag']; ik=x['interval_key']; seq=x['seq']; b2=x['b2']; b2sig=x['b2_sig']; record=x['record']; casig=x['ca_sig']
    physical=VERIFIED; cache_present=True; cache_age=450; revoked=False; last_seq=6; disclosure=True
    if name=='modified_message': msg=bytes([msg[0]^1])+msg[1:]
    elif name=='wrong_interval_key': ik=bytes([x['interval_key'][0]^1])+x['interval_key'][1:]
    elif name=='stale_sequence_replay': last_seq=seq
    elif name=='invalid_b2_signature': b2sig=bytes([b2sig[0]^1])+b2sig[1:]
    elif name=='invalid_ca_record_signature': casig=bytes([casig[0]^1])+casig[1:]
    elif name=='revoked_record': revoked=True
    elif name=='expired_cache': cache_age=901
    elif name=='cold_cache': cache_present=False
    elif name=='missing_disclosure': disclosure=False
    elif name=='missing_physical_evidence': physical=INSUFFICIENT
    elif name=='physical_conflict': physical=CONFLICTING
    ca_ok=raw_verify(x['ca'].public_key(),casig,record)
    b2_ok=raw_verify(x['ac'].public_key(),b2sig,b2)
    sequence_ok=seq>last_seq
    hmac_ok=hmac.compare_digest(tag,hmac.new(ik,bytes([seq])+msg,hashlib.sha3_256).digest()[:16])
    if not disclosure: crypto=INSUFFICIENT
    elif not (ca_ok and b2_ok and sequence_ok and hmac_ok): crypto=CONFLICTING
    else: crypto=VERIFIED
    if revoked: trust=CONFLICTING
    elif not ca_ok: trust=CONFLICTING
    elif not cache_present or cache_age>900: trust=INSUFFICIENT
    else: trust=VERIFIED
    return {'crypto':crypto,'physical':physical,'trust':trust,'state':fuse(crypto,physical,trust)}

EXPECTED={
 'valid_all_evidence':VERIFIED,'modified_message':CONFLICTING,'wrong_interval_key':CONFLICTING,
 'stale_sequence_replay':CONFLICTING,'invalid_b2_signature':CONFLICTING,'invalid_ca_record_signature':CONFLICTING,
 'revoked_record':CONFLICTING,'expired_cache':INSUFFICIENT,'cold_cache':INSUFFICIENT,
 'missing_disclosure':INSUFFICIENT,'missing_physical_evidence':INSUFFICIENT,'physical_conflict':CONFLICTING}

def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--seed',type=int,default=1103);p.add_argument('--iterations',type=int,default=10000);p.add_argument('--repetitions',type=int,default=5);a=p.parse_args()
    if a.iterations<100 or a.repetitions<5:p.error('use at least 100 iterations and 5 repetitions')
    x=setup(a.seed); cases=[]
    for name,expected in EXPECTED.items():
        times=[]; actual=None; branch=None
        for _ in range(a.repetitions):
            t=time.perf_counter_ns()
            for __ in range(a.iterations): branch=evaluate(name,x)
            times.append((time.perf_counter_ns()-t)/a.iterations/1000); actual=branch['state']
        cases.append({'case':name,'expected':expected,'actual':actual,'branches':{k:branch[k] for k in ('crypto','physical','trust')},'passed':actual==expected,'unexpected_verified':actual==VERIFIED and expected!=VERIFIED,'microseconds_per_case':summary(times)})
    report={'schema':'sam.phase18.protocol-conformance.v1','scope':{'implemented':'integrated cryptographic, freshness, trust, physical-state and fusion conformance vectors','not_implemented':['attack/anomaly classifier','RF waveform or framing','operational PKI','certified hardware'],'security_label':'Controlled protocol vectors; no attack/anomaly dataset.'},'platform':{'system':platform.system(),'release':platform.release(),'machine':platform.machine(),'processor':platform.processor(),'python':platform.python_version(),'logical_cpu_count':os.cpu_count()},'configuration':{'seed':a.seed,'iterations_per_repetition':a.iterations,'repetitions':a.repetitions,'hmac':'HMAC-SHA3-256/128','signature':'ECDSA P-256/SHA-256 fixed-width r||s','cache_ttl_seconds':900,'fusion_rule':'conflict dominates; VERIFIED requires all three branches'},'cases':cases,'summary':{'case_count':len(cases),'passed_count':sum(c['passed'] for c in cases),'pass_fraction':sum(c['passed'] for c in cases)/len(cases),'unexpected_verified_count':sum(c['unexpected_verified'] for c in cases)},'peak_rss_mib':peak_mib(),'interpretation_limits':['Cases establish deterministic protocol conformance, not real-world attack prevalence or detection accuracy.','Physical evidence is a controlled branch state; no new LocaRDS claim is made.','Timings include Python cryptographic and rule evaluation on the recorded platform.','No precision, recall, F1, false-positive or false-negative result is produced.']}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()

