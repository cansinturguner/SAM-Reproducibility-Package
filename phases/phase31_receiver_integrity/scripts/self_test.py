#!/usr/bin/env python3
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
from run_phase31 import receiver_scores, guard_score, current_score

clean=np.asarray([1000.,1010.,990.,1005.])
s=receiver_scores(clean)
assert s.shape==(4,) and guard_score(clean)>=0 and current_score(clean)>=0
shifted=clean.copy(); shifted[2]+=1000
ss=receiver_scores(shifted)
assert int(np.argmax(ss))==2
assert guard_score(shifted)>guard_score(clean)
print("SAM Phase 31 self-test passed.")
