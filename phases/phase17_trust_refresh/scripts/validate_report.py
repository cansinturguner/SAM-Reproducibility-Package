#!/usr/bin/env python3
import json,sys
if len(sys.argv)!=2: raise SystemExit('usage: validate_report.py REPORT.json')
r=json.load(open(sys.argv[1])); assert r['schema']=='sam.phase17.integrated-trust-refresh.v2'; assert len(r['scenarios'])==4
assert all(r['correctness'].values())
for x in r['scenarios']:
 assert x['counts']['eligible_rows']==82986 and x['counts']['physical_supported']==78358
 assert x['counts']['hmac_verified']==82986
assert r['scenarios'][0]['counts']['trust_insufficient']==0
assert r['scenarios'][3]['counts']['trust_insufficient']>0
assert r['scenarios'][3]['counts']['refresh_failures']<100
print('SAM Phase 17 report validation passed.')
