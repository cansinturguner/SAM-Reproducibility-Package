#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, hmac, json, os, platform, random, resource, statistics, sys, time
from pathlib import Path
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature

ORDER=int('FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551',16)
def ec_key(seed):
    n=1+(int.from_bytes(hashlib.sha256(f'ecdsa:{seed}'.encode()).digest(),'big')%(ORDER-1))
    return ec.derive_private_key(n,ec.SECP256R1())
def raw_sign(k,m):
    r,s=decode_dss_signature(k.sign(m,ec.ECDSA(hashes.SHA256())))
    return r.to_bytes(32,'big')+s.to_bytes(32,'big')
def raw_verify(pub,sig,m):
    try:
        der=encode_dss_signature(int.from_bytes(sig[:32],'big'),int.from_bytes(sig[32:],'big'))
        pub.verify(der,m,ec.ECDSA(hashes.SHA256()));return True
    except (InvalidSignature,ValueError):return False
def fuse(c,p,t):
    if 'CONFLICTING' in (c,p,t):return 'CONFLICTING'
    if (c,p,t)==('VERIFIED','VERIFIED','VERIFIED'):return 'VERIFIED'
    return 'INSUFFICIENT_EVIDENCE'
def peak_mib():
    x=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return x/(1024*1024) if sys.platform=='darwin' else x/1024
def stats(v):
    q=sorted(v)
    def pct(p):
        z=(len(q)-1)*p;a=int(z);b=min(a+1,len(q)-1);return q[a]*(b-z)+q[b]*(z-a)
    return {'n':len(v),'mean':statistics.fmean(v),'median':statistics.median(v),'q05':pct(.05),'q95':pct(.95),'minimum':min(v),'maximum':max(v),'sample_stdev':statistics.stdev(v) if len(v)>1 else 0.0,'values':v}

def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--seed',type=int,default=1103);p.add_argument('--message-count',type=int,default=10000);p.add_argument('--repetitions',type=int,default=10);p.add_argument('--message-rate',type=float,default=6.2);a=p.parse_args()
    if a.message_count<1000 or a.repetitions<5 or a.message_rate<=0:p.error('use >=1000 messages, >=5 repetitions and positive rate')
    rng=random.Random(a.seed);messages=[rng.randbytes(14) for _ in range(a.message_count)]
    modified=bytes([messages[0][0]^1])+messages[0][1:]
    hkey=hashlib.sha3_256(f'hmac:{a.seed}'.encode()).digest()[:16]
    htags=[hmac.new(hkey,m,hashlib.sha3_256).digest()[:16] for m in messages]
    priv=ec_key(a.seed);pub=priv.public_key();sigs=[raw_sign(priv,m) for m in messages]
    methods=[]
    def bench(name,fn,logical,delay,valid,modified_rejected,scope):
        vals=[];accepted=0
        for _ in range(a.repetitions):
            t=time.perf_counter_ns();accepted=fn();vals.append((time.perf_counter_ns()-t)/a.message_count/1000)
        methods.append({'method':name,'scope':scope,'valid_messages_accepted':accepted,'valid_acceptance_fraction':accepted/a.message_count,'modified_message_rejected':modified_rejected,'microseconds_per_message':stats(vals),'logical_security_bytes_per_message':logical,'protocol_authentication_delay_seconds':delay})
    def legacy():
        s=0
        for m in messages:s^=m[0]
        return len(messages)
    def hv():
        return sum(hmac.compare_digest(t,hmac.new(hkey,m,hashlib.sha3_256).digest()[:16]) for m,t in zip(messages,htags))
    def ev():return sum(raw_verify(pub,s,m) for m,s in zip(messages,sigs))
    def tesla():
        # Timed after disclosure: verify the same HMAC tags using the disclosed interval key.
        return hv()
    def sam():
        n=0;trust='VERIFIED';physical='VERIFIED'
        for m,t in zip(messages,htags):
            crypto='VERIFIED' if hmac.compare_digest(t,hmac.new(hkey,m,hashlib.sha3_256).digest()[:16]) else 'CONFLICTING'
            if fuse(crypto,physical,trust)=='VERIFIED':n+=1
        return n
    hmod=not hmac.compare_digest(htags[0],hmac.new(hkey,modified,hashlib.sha3_256).digest()[:16])
    emod=not raw_verify(pub,sigs[0],modified)
    interval=1.0;b2period=60.0
    bench('Legacy unauthenticated',legacy,0.0,None,True,False,'message handling only; no authentication claim')
    bench('Pre-shared HMAC',hv,16.0,0.0,True,hmod,'per-message HMAC; key-distribution traffic excluded')
    bench('ECDSA per message',ev,64.0,0.0,True,emod,'per-message P-256 signature; certificate traffic excluded')
    bench('TESLA-style post-disclosure HMAC',tesla,17.0+16.0/(a.message_rate*interval),interval,True,hmod,'post-disclosure verification; B1 key amortized')
    bench('SAM crypto-trust-fusion stage',sam,17.0+16.0/(a.message_rate*interval)+80.0/(a.message_rate*b2period),interval,True,hmod,'post-disclosure HMAC + valid cached trust + controlled physical state + fusion; TDoA excluded')
    report={'schema':'sam.phase19a.authentication-baselines.v1','scope':{'implemented':'same-workload authentication microbenchmark and logical authenticator-size comparison','not_implemented':['complete CABBA reproduction','direct TDoA cost in the SAM row','RF framing, FEC, BER or channel occupancy','certificate or trust-network traffic','certified hardware']},'platform':{'system':platform.system(),'release':platform.release(),'machine':platform.machine(),'processor':platform.processor(),'python':platform.python_version(),'logical_cpu_count':os.cpu_count()},'configuration':{'seed':a.seed,'message_count':a.message_count,'synthetic_message_bytes':14,'repetitions':a.repetitions,'message_rate_per_second':a.message_rate,'tesla_interval_seconds':interval,'b2_period_seconds':b2period,'hmac':'HMAC-SHA3-256/128','ecdsa':'P-256/SHA-256 fixed-width r||s'},'methods':methods,'correctness':{'all_claiming_methods_accept_all_valid':all(x['valid_acceptance_fraction']==1.0 for x in methods),'all_authentication_methods_reject_modified':all(x['modified_message_rejected'] for x in methods if x['method']!='Legacy unauthenticated'),'legacy_has_no_modified_message_rejection':methods[0]['modified_message_rejected'] is False},'peak_rss_mib':peak_mib(),'interpretation_limits':['This is a cryptographic message-processing microbenchmark, not a complete system comparison.','TESLA timing is measured after key disclosure; the one-second schedule delay is reported separately.','The SAM row excludes direct-TDoA computation and online trust refresh.','Logical byte counts are not RF-channel occupancy.','Legacy acceptance of a modified message reflects absence of authentication, not a detection metric.']}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()

