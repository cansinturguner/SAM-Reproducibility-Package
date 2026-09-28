#!/usr/bin/env python3
import json,sys
if len(sys.argv)!=2:raise SystemExit('usage: validate_report.py REPORT.json')
r=json.load(open(sys.argv[1]));assert r['schema']=='sam.phase18.protocol-conformance.v1'
assert r['summary']['case_count']==12 and r['summary']['passed_count']==12
assert r['summary']['pass_fraction']==1.0 and r['summary']['unexpected_verified_count']==0
m={x['case']:x for x in r['cases']};assert m['valid_all_evidence']['actual']=='VERIFIED'
for n in ('modified_message','wrong_interval_key','stale_sequence_replay','invalid_b2_signature','invalid_ca_record_signature','revoked_record','physical_conflict'):assert m[n]['actual']=='CONFLICTING'
for n in ('expired_cache','cold_cache','missing_disclosure','missing_physical_evidence'):assert m[n]['actual']=='INSUFFICIENT_EVIDENCE'
print('SAM Phase 18 report validation passed.')

