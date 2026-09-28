#!/usr/bin/env python3
"""Run the integrated SAM per-observation software pipeline."""

from __future__ import annotations
import argparse, csv, gzip, hashlib, hmac, json, math, os, platform, resource
import statistics, subprocess, sys, time
from pathlib import Path
import numpy as np
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature

C=299_792_458.0
WGS84_A=6378137.0
WGS84_E2=6.69437999014e-3
EXPECTED_SELECTED_SHA256="1a4cf881073ec0d4450b76026b6d4e2ecbb9765482382ce7989aa515f8cdadb5"

def sha256_file(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def finite(v):
    try: x=float(v)
    except (TypeError,ValueError): return None
    return x if math.isfinite(x) else None

def truthy(v): return str(v).strip().lower() in {'true','1','yes'}

def ecef(lat_deg,lon_deg,h):
    lat,lon=math.radians(lat_deg),math.radians(lon_deg)
    sl,cl=math.sin(lat),math.cos(lat)
    n=WGS84_A/math.sqrt(1-WGS84_E2*sl*sl)
    return np.array([(n+h)*cl*math.cos(lon),(n+h)*cl*math.sin(lon),(n*(1-WGS84_E2)+h)*sl])

def load_sensors(path):
    out={}
    with path.open(newline='',encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            if not truthy(row.get('good')): continue
            sid=str(row.get('serial','')).strip(); vals=[finite(row.get(k)) for k in ('latitude','longitude','height')]
            if sid and all(v is not None for v in vals): out[sid]=ecef(*vals)
    return out

def load_biases(path):
    d=json.loads(path.read_text(encoding='utf-8'))
    if d.get('selected_model')!='bias_only': raise SystemExit('Phase 14 requires frozen bias_only calibration')
    return {str(x['sensor']):float(x['bias_ns_at_time_center']) for x in d['receiver_parameters']}

def measurements(raw,modeled):
    dedup={}
    for item in json.loads(raw):
        if isinstance(item,list) and len(item)>=2:
            sid=str(item[0]).strip(); ts=finite(item[1])
            if sid in modeled and ts is not None: dedup.setdefault(sid,ts)
    return sorted(dedup.items())

def rank3(points):
    x=np.vstack(points); s=np.linalg.svd(x-x.mean(axis=0),compute_uv=False)
    tol=s[0]*max(x.shape)*np.finfo(float).eps
    return int(np.sum(s>tol))==3

def canonical_message(row):
    fields=(row.get('id',''),row.get('timeAtServer',''),row.get('aircraft',''),row.get('latitude',''),
            row.get('longitude',''),row.get('baroAltitude',''),row.get('geoAltitude',''))
    return hashlib.sha256('|'.join(str(x).strip() for x in fields).encode()).digest()[:14]

def trust_bootstrap(seed):
    # Deterministic EC private-key derivation is limited to this reproducible prototype.
    order=int('FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551',16)
    ca_scalar=1+(int.from_bytes(hashlib.sha256(f'ca:{seed}'.encode()).digest(),'big')%(order-1))
    ac_scalar=1+(int.from_bytes(hashlib.sha256(f'ac:{seed}'.encode()).digest(),'big')%(order-1))
    ca=ec.derive_private_key(ca_scalar,ec.SECP256R1()); aircraft=ec.derive_private_key(ac_scalar,ec.SECP256R1())
    pub=aircraft.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.CompressedPoint)
    record=b'SAM-AIRCRAFT-KEY-V1|'+pub
    sig=ca.sign(record,ec.ECDSA(hashes.SHA256()))
    ca.public_key().verify(sig,record,ec.ECDSA(hashes.SHA256()))
    return hashlib.sha256(pub).digest(), True

def fuse(crypto,physical,trust):
    if 'CONFLICTING' in (crypto,physical,trust): return 'CONFLICTING'
    if (crypto,physical,trust)==('VERIFIED','VERIFIED','VERIFIED'): return 'VERIFIED'
    return 'INSUFFICIENT_EVIDENCE'

def peak_mib():
    v=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return v/(1024*1024) if sys.platform=='darwin' else v/1024

def worker(a):
    start=time.perf_counter(); cpu0=time.process_time()
    if not a.skip_hash_check:
        got=sha256_file(a.selected)
        if got!=a.expected_selected_sha256: raise SystemExit(f'Selected SHA-256 mismatch: {got}')
    sensors=load_sensors(a.sensors); biases=load_biases(a.calibration); modeled=set(sensors)&set(biases)
    root_key,trust_ok=trust_bootstrap(a.seed)
    counts={'rows_read':0,'test_rows':0,'test_original_ge4_rows':0,'physical_supported_rows':0,
            'hmac_verified_rows':0,'A1_VERIFIED':0,'A1_INSUFFICIENT_EVIDENCE':0,'A1_CONFLICTING':0}
    residuals=[]; assurance={'VERIFIED':0,'INSUFFICIENT_EVIDENCE':0,'CONFLICTING':0}
    a7_crypto_verified=0; a7_physical_verified=0
    with gzip.open(a.selected,'rt',newline='',encoding='utf-8') as f:
        for row in csv.DictReader(f):
            counts['rows_read']+=1
            if row['split'].strip().lower()!='test': continue
            counts['test_rows']+=1
            if not truthy(row['eligible_ge4']): continue
            counts['test_original_ge4_rows']+=1
            msg=canonical_message(row)
            interval=int(float(row.get('timeAtServer') or 0.0))
            key=hmac.new(root_key,b'interval:'+interval.to_bytes(8,'big',signed=False),hashlib.sha3_256).digest()[:16]
            tag=hmac.new(key,msg,hashlib.sha3_256).digest()[:16]
            crypto='VERIFIED' if hmac.compare_digest(tag,hmac.new(key,msg,hashlib.sha3_256).digest()[:16]) else 'CONFLICTING'
            if crypto=='VERIFIED': counts['hmac_verified_rows']+=1
            lat,lon=finite(row['latitude']),finite(row['longitude']); alt=finite(row['geoAltitude'])
            if alt is None: alt=finite(row['baroAltitude'])
            physical='INSUFFICIENT_EVIDENCE'
            if None not in (lat,lon,alt):
                try: ms=measurements(row['goodMeasurements'],modeled)
                except (json.JSONDecodeError,TypeError): ms=[]
                if len(ms)>=4 and rank3([sensors[sid] for sid,_ in ms]):
                    xyz=ecef(lat,lon,alt); delays={sid:float(np.linalg.norm(xyz-sensors[sid])/C*1e9) for sid,_ in ms}
                    corrected={sid:ts-biases[sid] for sid,ts in ms}; ref=ms[0][0]
                    residuals.extend((corrected[sid]-corrected[ref])-(delays[sid]-delays[ref]) for sid,_ in ms[1:])
                    physical='VERIFIED'; counts['physical_supported_rows']+=1
            trust='VERIFIED' if trust_ok else 'CONFLICTING'
            state=fuse(crypto,physical,trust); assurance[state]+=1; counts['A1_'+state]+=1
            if crypto=='VERIFIED' and trust=='VERIFIED': a7_crypto_verified+=1
            if physical=='VERIFIED': a7_physical_verified+=1
    wall=time.perf_counter()-start; cpu=time.process_time()-cpu0
    absr=np.abs(np.asarray(residuals,dtype=float))
    n=counts['test_original_ge4_rows']
    return {
      'counts':counts,'assurance_states':assurance,
      'A0':{'LEGACY_UNASSURED':n},
      'A2_no_crypto':{'INSUFFICIENT_EVIDENCE':n},
      'A3_no_physical':{'INSUFFICIENT_EVIDENCE':n},
      'A6_trust_modes':{'valid_cache':{'VERIFIED':counts['physical_supported_rows'],'INSUFFICIENT_EVIDENCE':n-counts['physical_supported_rows']},'cold_or_expired_cache':{'INSUFFICIENT_EVIDENCE':n},'revoked_record':{'CONFLICTING':n}},
      'A7_single_source':{'crypto_only_VERIFIED':a7_crypto_verified,'physical_only_VERIFIED':a7_physical_verified,'physical_only_INSUFFICIENT_EVIDENCE':n-a7_physical_verified},
      'validation':{'absolute_q50_ns':float(np.quantile(absr,.5)),'absolute_q95_ns':float(np.quantile(absr,.95))},
      'timing':{'wall_seconds':wall,'cpu_seconds':cpu,'microseconds_per_original_ge4_row':wall*1e6/n,'original_ge4_rows_per_second':n/wall},
      'memory':{'peak_rss_mib':peak_mib()}}

def summary(vals):
    return {'n':len(vals),'mean':statistics.fmean(vals),'median':statistics.median(vals),'minimum':min(vals),'maximum':max(vals),'sample_stdev':statistics.stdev(vals) if len(vals)>1 else 0.0,'values':vals}

def child(a):
    cmd=[sys.executable,str(Path(__file__).resolve()),'--worker','--selected',str(a.selected),'--sensors',str(a.sensors),'--calibration',str(a.calibration),'--seed',str(a.seed),'--expected-selected-sha256',a.expected_selected_sha256]
    if a.skip_hash_check: cmd.append('--skip-hash-check')
    env=os.environ.copy(); env.update({'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','VECLIB_MAXIMUM_THREADS':'1'})
    return json.loads(subprocess.run(cmd,check=True,capture_output=True,text=True,env=env).stdout)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--selected',type=Path,required=True); p.add_argument('--sensors',type=Path,required=True)
    p.add_argument('--calibration',type=Path,required=True); p.add_argument('--report',type=Path)
    p.add_argument('--seed',type=int,default=1103); p.add_argument('--warmups',type=int,default=1); p.add_argument('--repetitions',type=int,default=30)
    p.add_argument('--expected-selected-sha256',default=EXPECTED_SELECTED_SHA256); p.add_argument('--skip-hash-check',action='store_true'); p.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    a=p.parse_args()
    if a.worker: print(json.dumps(worker(a))); return
    if a.report is None: p.error('--report is required')
    if a.repetitions<5: p.error('--repetitions must be at least 5')
    for _ in range(a.warmups): child(a)
    runs=[child(a) for _ in range(a.repetitions)]
    base=runs[0]
    for x in runs[1:]:
        if x['counts']!=base['counts'] or x['assurance_states']!=base['assurance_states']: raise SystemExit('Non-deterministic counts')
    if not a.skip_hash_check:
        if base['counts']['test_original_ge4_rows']!=82986 or base['counts']['physical_supported_rows']!=78358: raise SystemExit('Frozen Phase 5D count mismatch')
        if abs(base['validation']['absolute_q50_ns']-64.98799972087727)>1e-6: raise SystemExit('Frozen q50 mismatch')
    report={'schema':'sam.phase14.integrated-message-pipeline.v1',
      'scope':{'implemented':'per-observation physical + synthetic post-disclosure HMAC + cached trust + deterministic fusion software pipeline','not_implemented':['authenticator captured from original LocaRDS RF payload','TESLA disclosure scheduling inside the timed path','raw-IQ recovery','trust-service networking or ledger consensus','certified airborne hardware','attack/anomaly classifier']},
      'platform':{'system':platform.system(),'release':platform.release(),'machine':platform.machine(),'processor':platform.processor(),'python':platform.python_version(),'numpy':np.__version__,'logical_cpu_count':os.cpu_count()},
      'configuration':{'seed':a.seed,'warmups':a.warmups,'measured_fresh_process_repetitions':a.repetitions,'message_surrogate_bytes':14,'hmac':'HMAC-SHA3-256','transmitted_tag_bytes':16,'trust_record':'ECDSA P-256/SHA-256 verified once then cached','fusion_policy':'VERIFIED requires crypto + trust + physical; conflict dominates'},
      'inputs':{'selected_sha256':sha256_file(a.selected),'sensors_sha256':sha256_file(a.sensors),'calibration_sha256':sha256_file(a.calibration)},
      'counts':base['counts'],'assurance_states':base['assurance_states'],'component_variants':{k:base[k] for k in ('A0','A2_no_crypto','A3_no_physical','A6_trust_modes','A7_single_source')},
      'validation':base['validation'],
      'summaries':{k:summary([float(x['timing'][k]) for x in runs]) for k in ('wall_seconds','cpu_seconds','microseconds_per_original_ge4_row','original_ge4_rows_per_second')},
      'peak_rss_mib':summary([float(x['memory']['peak_rss_mib']) for x in runs]),
      'interpretation_limits':['This is the first co-executed SAM software path, but the authenticator is deterministically synthesized and bound to each real LocaRDS observation.','Timing is an offline Python/Mac measurement and excludes TESLA disclosure delay, RF processing, network transport, and ledger operations.','Assurance-state counts are policy outcomes on valid synthetic authenticators and benign LocaRDS observations, not detection-accuracy results.','No precision, recall, F1, false-positive or false-negative result is produced.']}
    a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'schema':report['schema'],'platform':report['platform'],'configuration':report['configuration'],'counts':report['counts'],'assurance_states':report['assurance_states'],'component_variants':report['component_variants'],'validation':report['validation'],'summaries':report['summaries'],'peak_rss_mib':report['peak_rss_mib'],'interpretation_limits':report['interpretation_limits']},indent=2))

if __name__=='__main__': main()

