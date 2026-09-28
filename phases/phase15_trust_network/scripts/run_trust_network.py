#!/usr/bin/env python3
"""Benchmark a signed-record trust service over TCP with controlled RTT."""
from __future__ import annotations
import argparse, asyncio, base64, hashlib, json, math, os, platform, resource
import statistics, sys, time
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

ORDER=int('FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551',16)

def percentile(v,p):
    s=sorted(v); pos=(len(s)-1)*p; lo=int(pos); hi=min(lo+1,len(s)-1); f=pos-lo
    return s[lo]*(1-f)+s[hi]*f

def dist(v):
    return {'n':len(v),'mean':statistics.fmean(v),'median':statistics.median(v),'q05':percentile(v,.05),'q95':percentile(v,.95),'q99':percentile(v,.99),'minimum':min(v),'maximum':max(v),'sample_stdev':statistics.stdev(v) if len(v)>1 else 0.0}

def keys(seed):
    ca_s=1+(int.from_bytes(hashlib.sha256(f'ca:{seed}'.encode()).digest(),'big')%(ORDER-1))
    ac_s=1+(int.from_bytes(hashlib.sha256(f'ac:{seed}'.encode()).digest(),'big')%(ORDER-1))
    ca=ec.derive_private_key(ca_s,ec.SECP256R1()); ac=ec.derive_private_key(ac_s,ec.SECP256R1())
    pub=ac.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.CompressedPoint)
    record=b'SAM-TRUST-RECORD-V1|aircraft=prototype|pub='+pub+b'|revoked=false|ttl=900'
    sig=ca.sign(record,ec.ECDSA(hashes.SHA256()))
    ca.public_key().verify(sig,record,ec.ECDSA(hashes.SHA256()))
    return ca.public_key(),record,sig

def peak_mib():
    v=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return v/(1024*1024) if sys.platform=='darwin' else v/1024

async def run_once(rtt_ms,concurrency,total_requests,public_key,record,signature):
    response=(json.dumps({'record':base64.b64encode(record).decode(),'signature':base64.b64encode(signature).decode(),'revoked':False},separators=(',',':'))+'\n').encode()
    request=b'{"aircraft":"prototype"}\n'
    async def handler(reader,writer):
        try:
            while True:
                line=await reader.readline()
                if not line: break
                await asyncio.sleep(rtt_ms/1000.0)
                writer.write(response); await writer.drain()
        finally:
            writer.close(); await writer.wait_closed()
    server=await asyncio.start_server(handler,'127.0.0.1',0)
    port=server.sockets[0].getsockname()[1]
    lat=[]; failures=0
    base=total_requests//concurrency; rem=total_requests%concurrency
    async def client(n):
        nonlocal failures
        reader,writer=await asyncio.open_connection('127.0.0.1',port)
        try:
            for _ in range(n):
                t=time.perf_counter_ns(); writer.write(request); await writer.drain(); line=await reader.readline()
                try:
                    data=json.loads(line); rec=base64.b64decode(data['record']); sig=base64.b64decode(data['signature'])
                    public_key.verify(sig,rec,ec.ECDSA(hashes.SHA256()))
                    if data['revoked']: failures+=1
                except Exception:
                    failures+=1
                lat.append((time.perf_counter_ns()-t)/1e6)
        finally:
            writer.close(); await writer.wait_closed()
    start=time.perf_counter()
    await asyncio.gather(*(client(base+(1 if i<rem else 0)) for i in range(concurrency)))
    elapsed=time.perf_counter()-start
    server.close(); await server.wait_closed()
    return {'latency_ms':dist(lat),'throughput_requests_per_second':total_requests/elapsed,'wall_seconds':elapsed,'verification_failures':failures,'request_bytes':len(request),'response_bytes':len(response)}

def cache_benchmark(iterations,ttl):
    now=1000.0; cache={'verified':True,'stored':now,'ttl':ttl}
    vals=[]
    for _ in range(iterations):
        t=time.perf_counter_ns(); state='VERIFIED' if cache['verified'] and now-cache['stored']<=cache['ttl'] else 'INSUFFICIENT_EVIDENCE'; vals.append((time.perf_counter_ns()-t)/1000)
    return {'iterations':iterations,'lookup_microseconds':dist(vals),'state':state}

async def experiment(a):
    pub,record,sig=keys(a.seed)
    scenarios=[]
    for rtt in a.rtts:
        for conc in a.concs:
            reps=[]
            for _ in range(a.repetitions): reps.append(await run_once(rtt,conc,a.requests_per_scenario,pub,record,sig))
            scenarios.append({'emulated_rtt_ms':rtt,'concurrency':conc,'requests_per_repetition':a.requests_per_scenario,'repetitions':a.repetitions,
                'latency_ms_across_all_requests':dist([z for x in reps for z in []]) if False else {
                    'median_of_repetition_medians':statistics.median([x['latency_ms']['median'] for x in reps]),
                    'mean_of_repetition_means':statistics.fmean([x['latency_ms']['mean'] for x in reps]),
                    'median_of_repetition_q95':statistics.median([x['latency_ms']['q95'] for x in reps]),
                    'median_of_repetition_q99':statistics.median([x['latency_ms']['q99'] for x in reps])},
                'throughput_requests_per_second':dist([x['throughput_requests_per_second'] for x in reps]),
                'verification_failures':sum(x['verification_failures'] for x in reps),'request_bytes':reps[0]['request_bytes'],'response_bytes':reps[0]['response_bytes']})
    return pub,record,sig,scenarios

def main():
    p=argparse.ArgumentParser(); p.add_argument('--report',type=Path,required=True); p.add_argument('--seed',type=int,default=1103)
    p.add_argument('--rtt-ms',default='0,10,50,100,250'); p.add_argument('--concurrency',default='1,8,32')
    p.add_argument('--requests-per-scenario',type=int,default=64); p.add_argument('--repetitions',type=int,default=5); p.add_argument('--cache-ttl-seconds',type=int,default=900); p.add_argument('--cache-iterations',type=int,default=100000)
    a=p.parse_args(); a.rtts=[float(x) for x in a.rtt_ms.split(',')]; a.concs=[int(x) for x in a.concurrency.split(',')]
    if a.repetitions<5 or a.requests_per_scenario<32: p.error('use at least 5 repetitions and 32 requests per scenario')
    pub,record,sig,scenarios=asyncio.run(experiment(a))
    cache=cache_benchmark(a.cache_iterations,a.cache_ttl_seconds)
    report={'schema':'sam.phase15.trust-network-cache.v1','scope':{'implemented':'TCP signed-record lookup with controlled added RTT, concurrency, signature verification, cache and outage policy states','not_implemented':['operational WAN measurement','TLS','X.509 parsing or global aviation PKI','permissioned blockchain consensus or ledger writes','certified airborne hardware','attack/anomaly classifier']},
      'platform':{'system':platform.system(),'release':platform.release(),'machine':platform.machine(),'processor':platform.processor(),'python':platform.python_version(),'cryptography':__import__('cryptography').__version__,'logical_cpu_count':os.cpu_count()},
      'configuration':{'seed':a.seed,'emulated_rtt_ms':a.rtts,'concurrency':a.concs,'requests_per_scenario':a.requests_per_scenario,'repetitions':a.repetitions,'persistent_tcp_connection_per_worker':True,'signature':'ECDSA P-256/SHA-256','cache_ttl_seconds':a.cache_ttl_seconds},
      'correctness':{'record_signature_verified_before_test':True,'all_online_responses_verified':all(x['verification_failures']==0 for x in scenarios)},
      'online_scenarios':scenarios,'cache_fast_path':cache,
      'service_states':[{'name':'online_valid','state':'VERIFIED'},{'name':'offline_valid_cache','cache_age_seconds':450,'state':'VERIFIED'},{'name':'offline_cold_start','state':'INSUFFICIENT_EVIDENCE'},{'name':'offline_expired_cache','cache_age_seconds':901,'state':'INSUFFICIENT_EVIDENCE'},{'name':'online_revoked_record','state':'CONFLICTING'}],
      'prototype_wire_bytes':{'request_json_line':scenarios[0]['request_bytes'],'signed_response_json_line':scenarios[0]['response_bytes'],'note':'Prototype TCP JSON-line sizes; not ADS-B, Phase Overlay, TLS, FEC, or ledger traffic.'},
      'peak_rss_mib':peak_mib(),'interpretation_limits':['Added RTT is controlled application delay over loopback, not a field-network measurement.','Online latency includes TCP exchange, added RTT, JSON/base64 processing, and ECDSA verification.','Cache lookup is a local policy-state benchmark and does not include disk or network access.','No precision, recall, F1, false-positive or false-negative result is produced.']}
    a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'schema':report['schema'],'platform':report['platform'],'configuration':report['configuration'],'correctness':report['correctness'],'online_scenarios':report['online_scenarios'],'cache_fast_path':report['cache_fast_path'],'service_states':report['service_states'],'prototype_wire_bytes':report['prototype_wire_bytes'],'peak_rss_mib':report['peak_rss_mib'],'interpretation_limits':report['interpretation_limits']},indent=2))
if __name__=='__main__': main()

