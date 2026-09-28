#!/usr/bin/env python3
import json,sys
from pathlib import Path
def fail(x): raise SystemExit('Validation failed: '+x)
if len(sys.argv)!=2: raise SystemExit('Usage: validate_report.py REPORT.json')
r=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if r.get('schema')!='sam.phase15.trust-network-cache.v1': fail('schema')
if not all(r['correctness'].values()): fail('correctness')
expected=len(r['configuration']['emulated_rtt_ms'])*len(r['configuration']['concurrency'])
if len(r['online_scenarios'])!=expected: fail('scenario count')
if any(x['verification_failures'] for x in r['online_scenarios']): fail('online verification')
states={x['name']:x['state'] for x in r['service_states']}
if states!={'online_valid':'VERIFIED','offline_valid_cache':'VERIFIED','offline_cold_start':'INSUFFICIENT_EVIDENCE','offline_expired_cache':'INSUFFICIENT_EVIDENCE','online_revoked_record':'CONFLICTING'}: fail('service states')
for x in r['online_scenarios']:
    if x['latency_ms_across_all_requests']['median_of_repetition_medians']<0: fail('latency')
if r['configuration']['repetitions']<5: fail('repetitions')
print('SAM Phase 15 report validation passed.')
