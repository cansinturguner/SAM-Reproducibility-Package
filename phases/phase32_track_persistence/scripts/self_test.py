#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from run_phase32 import POLICIES,activation_delays,apply_policy,persistent_step_delay

def row(state): return {"state":state}
C="PHYSICALLY_CONSISTENT";X="PHYSICALLY_CONFLICTING";U="PHYSICAL_EVIDENCE_UNAVAILABLE"
out=apply_policy([row(C),row(X),row(X),row(C),row(C),row(C)],POLICIES["two_of_three_h3"])
assert out==[False,False,True,True,True,False]
assert apply_policy([row(X),row(U),row(X)],POLICIES["two_of_three_h3"])==[False,False,True]
assert persistent_step_delay(POLICIES["raw_1_of_1"])==1
assert persistent_step_delay(POLICIES["two_of_three_h3"])==2
timed=[{"state":C,"time":0.0},{"state":X,"time":1.0},{"state":X,"time":3.5}]
assert activation_delays(timed,POLICIES["two_of_three_h3"])==[{"seconds":2.5,"available_observations":2}]
print("SAM Phase 32 self-test passed.")
