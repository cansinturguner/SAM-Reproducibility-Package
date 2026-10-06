#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import numpy as np
s=Path(__file__).with_name("run_reference_independent_guard.py"); spec=importlib.util.spec_from_file_location("p30",s); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
base=np.asarray([0.,10.,-10.,5.]); assert m.current_score(base)==10.; assert m.guard_score(base)==float(np.max(m.receiver_scores(base)))
shift=base.copy(); shift[2]+=1000.; assert m.guard_score(shift)>m.guard_score(base); assert np.isclose(m.guard_score(shift[[2,0,3,1]]),m.guard_score(shift)); assert m.qhigher([1,2,3,4],.5)==3
print("SAM Phase 30 self-test passed.")
