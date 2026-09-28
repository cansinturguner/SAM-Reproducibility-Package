#!/usr/bin/env python3
import json,sys
from pathlib import Path
if len(sys.argv)!=2:raise SystemExit('usage: validate_report.py REPORT.json')
r=json.loads(Path(sys.argv[1]).read_text())
assert r['schema']=='sam.phase22b.residual-tail-audit.v1'
assert r['scope']['correction_applied'] is False
assert r['counts']['rows_read']==6535444
assert r['counts']['eligible_rows']==107314
assert r['counts']['supported_rows']==98024
assert r['counts']['pair_residuals']==376221
f=r['tail_fractions'];assert f['within_500_ns']<=f['within_1000_ns']<=f['within_10000_ns']<=f['within_100000_ns']<=f['within_1000000_ns']
print('SAM Phase 22B residual-tail audit passed.')
