#!/usr/bin/env python3
import argparse, json
from pathlib import Path

def require(value, message):
    if not value: raise SystemExit(message)

def main():
    p=argparse.ArgumentParser(); p.add_argument("report",type=Path); p.add_argument("model",type=Path); a=p.parse_args()
    r=json.loads(a.report.read_text()); m=json.loads(a.model.read_text())
    require(r.get("schema")=="sam.phase31.reference-independent-receiver-integrity.v1","report schema mismatch")
    require(m.get("schema")=="sam.phase31.receiver-integrity-model.v1","model schema mismatch")
    require(m.get("reference_independent") is True,"model is not reference independent")
    require(m.get("test_used_for_selection") is False,"test leakage")
    require(float(m["threshold_ns"])>0,"invalid threshold")
    for name in ("development_validation","subset1_frozen_test","subset2_transfer"):
        x=r[name]; require(x["originally_eligible_rows"]>=x["physical_available_rows"]>0,name+" counts")
        for branch in ("reference_rule","receiver_integrity_guard","combined_rule"):
            b=x[branch]; require(b["PHYSICALLY_CONSISTENT"]+b["PHYSICALLY_CONFLICTING"]==b["available_rows"],name+"/"+branch)
            f=b["empirical_benign_reference_conflict_fraction_among_available"]; require(0<=f<=1,"invalid fraction")
    require(set(r["single_receiver_timestamp_corruption"])=={"100","250","500","750","1000","2000","5000","10000"},"magnitude set")
    for item in r["single_receiver_timestamp_corruption"].values():
        for key in ("result_conflict_fraction","consistent_to_conflicting_fraction","target_ranked_highest_fraction"):
            require(item[key] is None or 0<=item[key]<=1,"invalid corruption fraction")
    print("SAM Phase 31 reference-independent receiver integrity validation passed.")

if __name__=="__main__": main()
