#!/usr/bin/env python3
import json, math, sys
from pathlib import Path

def fail(x): raise SystemExit('Validation failed: '+x)
if len(sys.argv)!=2: raise SystemExit('Usage: validate_report.py REPORT.json')
r=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if r.get('schema')!='sam.phase14.integrated-message-pipeline.v1': fail('schema')
c=r['counts']; n=c['test_original_ge4_rows']
if n!=82986 or c['physical_supported_rows']!=78358: fail('frozen counts')
if c['hmac_verified_rows']!=n: fail('HMAC coverage')
if c['A1_VERIFIED']!=78358 or c['A1_INSUFFICIENT_EVIDENCE']!=4628 or c['A1_CONFLICTING']!=0: fail('A1 states')
if sum(r['assurance_states'].values())!=n: fail('state total')
if not math.isclose(r['validation']['absolute_q50_ns'],64.98799972087727,abs_tol=1e-6): fail('q50')
if not math.isclose(r['validation']['absolute_q95_ns'],227.07981870131601,abs_tol=1e-6): fail('q95')
if r['component_variants']['A6_trust_modes']['revoked_record']['CONFLICTING']!=n: fail('revoked state')
if r['configuration']['measured_fresh_process_repetitions']<5: fail('repetitions')
print('SAM Phase 14 report validation passed.')
