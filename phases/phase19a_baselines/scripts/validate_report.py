#!/usr/bin/env python3
import json,sys
if len(sys.argv)!=2:raise SystemExit('usage: validate_report.py REPORT.json')
r=json.load(open(sys.argv[1]));assert r['schema']=='sam.phase19a.authentication-baselines.v1';assert len(r['methods'])==5
assert all(r['correctness'].values())
m={x['method']:x for x in r['methods']};assert m['Legacy unauthenticated']['logical_security_bytes_per_message']==0
assert m['Pre-shared HMAC']['modified_message_rejected'] is True
assert m['ECDSA per message']['modified_message_rejected'] is True
assert m['TESLA-style post-disclosure HMAC']['protocol_authentication_delay_seconds']==1.0
assert m['SAM crypto-trust-fusion stage']['protocol_authentication_delay_seconds']==1.0
print('SAM Phase 19A report validation passed.')

