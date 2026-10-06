#!/usr/bin/env python3
import argparse,json
from pathlib import Path
def req(x,m):
    if not x: raise SystemExit(m)
def main():
    p=argparse.ArgumentParser();p.add_argument("report",type=Path);a=p.parse_args();r=json.loads(a.report.read_text())
    req(r.get("schema")=="sam.phase32.track-persistence-nuisance.v2","schema mismatch")
    req(r["configuration"]["test_used_for_selection"] is False,"test leakage")
    selected=r["development_selection"]["selected_policy"]; req(selected in r["configuration"]["candidate_policies"],"unknown selected policy")
    req(r["persistent_conflict_activation_delay_observations"][selected]<=2,"selected delay exceeds rule")
    for dataset,policies in r["all_policy_results"].items():
        for name,x in policies.items():
            req(x["eligible_rows"]==x["available_rows"]+x["unavailable_rows"],dataset+"/"+name+" row partition")
            req(x["eligible_rows"]>=x["available_rows"]>=0,dataset+"/"+name+" counts")
            req(x["alert_rows_all_eligible"]==x["alert_rows_on_available_evidence"]+x["alert_hold_rows_on_unavailable_evidence"],dataset+"/"+name+" alert partition")
            for key in ("alert_fraction_all_eligible_rows","alert_fraction_among_available_rows"):
                f=x[key]; req(f is None or 0<=f<=1,"invalid "+key)
            req(x["alert_episodes_per_1000_available"] is None or x["alert_episodes_per_1000_available"]>=0,"invalid episode rate")
    print("SAM Phase 32 v2 track persistence and nuisance-alert validation passed.")
if __name__=="__main__":main()
