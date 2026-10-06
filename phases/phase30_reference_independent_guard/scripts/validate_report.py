#!/usr/bin/env python3
import argparse,json,math
from pathlib import Path
def req(x,m):
    if not x: raise SystemExit(m)
def frac(x,m): req(x is None or 0<=float(x)<=1,"invalid "+m)
def main():
    p=argparse.ArgumentParser(); p.add_argument("report",type=Path); a=p.parse_args(); r=json.loads(a.report.read_text())
    req(r.get("schema")=="sam.phase30.reference-independent-receiver-guard.v1","schema mismatch"); m=r["method"]
    req(m["candidate_reference_independent"] is True,"not independent"); req(m["test_used_for_threshold_selection"] is False,"test leakage"); req(math.isclose(m["guard_threshold_quantile"],.99),"quantile mismatch")
    c=r["counts"]; req(c["development_validation_original_ge4"]==13430,"dev count"); req(c["development_validation_available"]==13240,"dev available"); req(c["subset1_test_original_ge4"]==82986,"test count"); req(c["subset1_test_available"]==78358,"test available"); req(c["subset1_test_unavailable"]==4628,"test unavailable")
    b=r["baseline_benign_reference"]; req(b["current_reference_rule"]["consistent_rows"]==77309,"frozen consistent mismatch"); req(b["current_reference_rule"]["conflicting_rows"]==1049,"frozen conflict mismatch")
    for name,x in b.items(): req(x["consistent_rows"]+x["conflicting_rows"]==78358,name+" total"); frac(x["empirical_benign_reference_conflict_fraction_among_available"],name)
    req(set(r["timestamp_corruption"])=={"100","250","500","750","1000","2000","5000","10000"},"magnitudes")
    for mag,groups in r["timestamp_corruption"].items():
        req(set(groups)=={"all_receivers","decision_reference","nonreference"},mag+" groups")
        for group,item in groups.items():
            for method in ("current_reference_rule","reference_independent_guard","combined_rule"):
                x=item[method]; req(x["baseline_consistent_trials"]+x["baseline_conflicting_trials"]==x["trials"],f"{mag}/{group}/{method}"); frac(x["result_conflict_fraction_all_trials"],"result"); frac(x["consistent_to_conflicting_fraction"],"transition"); frac(x["conflicting_to_consistent_fraction"],"reverse")
            frac(item["target_ranked_highest_fraction_all_trials"],"rank"); frac(item["target_ranked_highest_given_guard_conflict"],"rank conditional")
    print("SAM Phase 30 reference-independent receiver guard validation passed.")
if __name__=="__main__": main()
