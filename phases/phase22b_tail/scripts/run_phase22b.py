#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, json, math, platform, os, time
from collections import Counter
from pathlib import Path
import numpy as np
from phase14_core import C, ecef, finite, load_biases, load_sensors, rank3, sha256_file, truthy

EXPECTED_OBS="5ff68c7e402caa183678c03f4d23ba45b63bc96fa1177f8ce7e4fb530c45dd58"
EXPECTED_SENSORS="998a63f5fc89fa41fd1a37468431da96f355812054e7bca8b2a4f4db0ba47d1b"
EXPECTED_AIRCRAFT="70156a0865e655f4fb470e5814fd153708ac9f97ef193b70ebf3f4a5d84e1893"

def trusted_ids(path):
    with path.open(newline='',encoding='utf-8-sig') as f:
        return {str(r['aircraft']).strip() for r in csv.DictReader(f) if truthy(r.get('trusted'))}

def parse(raw, allowed):
    d={}
    for x in json.loads(raw):
        if isinstance(x,list) and len(x)>=2:
            sid=str(x[0]).strip(); ts=finite(x[1])
            if sid in allowed and ts is not None:d.setdefault(sid,ts)
    return sorted(d.items())

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--observations',type=Path,required=True);p.add_argument('--sensors',type=Path,required=True)
    p.add_argument('--aircraft',type=Path,required=True);p.add_argument('--calibration',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);p.add_argument('--skip-hash-check',action='store_true')
    a=p.parse_args()
    hashes={'observations':sha256_file(a.observations),'sensors':sha256_file(a.sensors),'aircraft':sha256_file(a.aircraft),'calibration':sha256_file(a.calibration)}
    if not a.skip_hash_check:
        for k,v in [('observations',EXPECTED_OBS),('sensors',EXPECTED_SENSORS),('aircraft',EXPECTED_AIRCRAFT)]:
            if hashes[k]!=v:raise SystemExit(f'{k} SHA-256 mismatch: {hashes[k]}')
    trusted=trusted_ids(a.aircraft); sensors=load_sensors(a.sensors); biases=load_biases(a.calibration)
    modeled=set(sensors)&set(biases); good=set(sensors)
    thresholds=[500,1000,10_000,100_000,1_000_000,10_000_000,100_000_000,500_000_000]
    within=Counter(); pair_large=Counter(); pair_near_1s=Counter(); integer_multiple=Counter(); samples=[]
    total=eligible=supported=pairs=0; max_abs=0.0; start=time.perf_counter()
    with a.observations.open(newline='',encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            total+=1; ac=str(row.get('aircraft','')).strip()
            if ac not in trusted:continue
            try:good_ms=parse(row['measurements'],good)
            except (json.JSONDecodeError,TypeError):continue
            if len(good_ms)<4:continue
            eligible+=1; ms=[x for x in good_ms if x[0] in modeled]
            if len(ms)<4 or not rank3([sensors[s] for s,_ in ms]):continue
            lat,lon=finite(row['latitude']),finite(row['longitude']);alt=finite(row['geoAltitude'])
            if alt is None:alt=finite(row['baroAltitude'])
            if None in (lat,lon,alt):continue
            supported+=1; xyz=ecef(lat,lon,alt)
            delays={s:float(np.linalg.norm(xyz-sensors[s])/C*1e9) for s,_ in ms}; corrected={s:t-biases[s] for s,t in ms}
            ref=ms[0][0]
            for sid,_ in ms[1:]:
                residual=(corrected[sid]-corrected[ref])-(delays[sid]-delays[ref]); ar=abs(residual);pairs+=1;max_abs=max(max_abs,ar)
                for th in thresholds:
                    if ar<=th:within[str(th)]+=1
                pair=f'{ref}->{sid}'
                if ar>10_000:pair_large[pair]+=1
                nearest=round(residual/1_000_000_000)
                delta=abs(residual-nearest*1_000_000_000)
                if nearest!=0 and delta<=10_000:
                    pair_near_1s[pair]+=1;integer_multiple[str(nearest)]+=1
                    if len(samples)<30:samples.append({'id':row.get('id'),'timeAtServer':row.get('timeAtServer'),'aircraft':ac,'pair':pair,'residual_ns':residual,'nearest_integer_seconds':nearest,'distance_from_integer_second_ns':delta})
    report={'schema':'sam.phase22b.residual-tail-audit.v1','scope':{'implemented':'diagnostic audit of unmodified subset-2 calibrated residual tails','correction_applied':False},
      'platform':{'system':platform.system(),'release':platform.release(),'machine':platform.machine(),'python':platform.python_version(),'numpy':np.__version__,'logical_cpu_count':os.cpu_count()},
      'inputs':{'sha256':hashes},'counts':{'rows_read':total,'eligible_rows':eligible,'supported_rows':supported,'pair_residuals':pairs},
      'tail_fractions':{f'within_{th}_ns':within[str(th)]/pairs for th in thresholds},
      'over_threshold_counts':{'over_10us':pairs-within['10000'],'over_100us':pairs-within['100000'],'over_1ms':pairs-within['1000000'],'over_100ms':pairs-within['100000000'],'over_500ms':pairs-within['500000000']},
      'maximum_absolute_residual_ns':max_abs,'near_nonzero_integer_second_within_10us':{'count':sum(integer_multiple.values()),'fraction':sum(integer_multiple.values())/pairs,'integer_second_histogram':dict(integer_multiple)},
      'top_receiver_pairs_over_10us':pair_large.most_common(20),'top_receiver_pairs_near_integer_second':pair_near_1s.most_common(20),'near_integer_second_samples':samples,
      'runtime_wall_seconds':time.perf_counter()-start,
      'interpretation_limits':['This audit does not modify, wrap, trim or remove residuals.','Near-integer-second classification is diagnostic and does not by itself establish timestamp rollover.','Receiver-pair concentration does not identify malicious behavior or assign sensor fault.']}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()

