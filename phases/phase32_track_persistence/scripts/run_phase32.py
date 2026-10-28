#!/usr/bin/env python3
"""Track-level persistence and nuisance-alert analysis for Phase 31 events."""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import platform
import statistics
import time
from collections import defaultdict
from pathlib import Path

POLICIES = {
    "raw_1_of_1": {"k": 1, "n": 1, "clear_consistent": 1},
    "two_of_three_h3": {"k": 2, "n": 3, "clear_consistent": 3},
    "three_of_five_h3": {"k": 3, "n": 5, "clear_consistent": 3},
    "three_consecutive_h3": {"k": 3, "n": 3, "clear_consistent": 3},
}


def finite(value):
    try: x=float(value)
    except (TypeError,ValueError): return None
    return x if math.isfinite(x) else None


def load_events(path):
    rows=[]
    with gzip.open(path,"rt",newline="",encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            t=finite(row.get("timeAtServer"))
            if t is None: continue
            rows.append({"id":row.get("id",""),"aircraft":str(row.get("aircraft","")),"time":t,"state":row.get("combined_state","")})
    rows.sort(key=lambda x:(x["aircraft"],x["time"],x["id"]))
    return rows


def group_tracks(rows,gap_seconds):
    tracks=[]; current=[]; last_aircraft=None; last_time=None
    for row in rows:
        boundary=(last_aircraft!=row["aircraft"] or last_time is None or row["time"]-last_time>gap_seconds or row["time"]<last_time)
        if boundary and current: tracks.append(current); current=[]
        current.append(row); last_aircraft=row["aircraft"]; last_time=row["time"]
    if current: tracks.append(current)
    return tracks


def apply_policy(track, policy):
    history=[]; active=False; clean_run=0; outputs=[]
    for row in track:
        state=row["state"]
        if state=="PHYSICAL_EVIDENCE_UNAVAILABLE":
            outputs.append(active); continue
        conflict=state=="PHYSICALLY_CONFLICTING"
        history.append(conflict); history=history[-policy["n"]:]
        clean_run=0 if conflict else clean_run+1
        if not active and len(history)>=policy["k"] and sum(history)>=policy["k"]:
            active=True
        if active and clean_run>=policy["clear_consistent"]:
            active=False
        outputs.append(active)
    return outputs


def episode_lengths(outputs):
    lengths=[]; run=0
    for x in outputs:
        if x: run+=1
        elif run: lengths.append(run); run=0
    if run: lengths.append(run)
    return lengths


def activation_delays(track, policy):
    """Return empirical delay from the earliest triggering conflict vote."""
    history=[]; active=False; clean_run=0; available_index=0; events=[]
    for row in track:
        state=row["state"]
        if state=="PHYSICAL_EVIDENCE_UNAVAILABLE":
            continue
        available_index+=1
        conflict=state=="PHYSICALLY_CONFLICTING"
        history.append({"conflict":conflict,"time":row["time"],"available_index":available_index})
        history=history[-policy["n"]:]
        clean_run=0 if conflict else clean_run+1
        if not active and len(history)>=policy["k"] and sum(x["conflict"] for x in history)>=policy["k"]:
            trigger_votes=[x for x in history if x["conflict"]]
            first=trigger_votes[-policy["k"]]
            events.append({
                "seconds":max(0.0,row["time"]-first["time"]),
                "available_observations":available_index-first["available_index"]+1,
            })
            active=True
        if active and clean_run>=policy["clear_consistent"]:
            active=False
    return events


def delay_summary(values):
    if not values:
        return {"n":0,"median":None,"q95":None,"maximum":None}
    ordered=sorted(values)
    return {
        "n":len(values),
        "median":statistics.median(values),
        "q95":ordered[math.ceil(.95*len(ordered))-1],
        "maximum":max(values),
    }


def summarize(rows,gap_seconds,policy):
    tracks=group_tracks(rows,gap_seconds); alerts=[]; lengths=[]; activation_events=[]; alert_aircraft=set(); available=conflicts=0
    available_alert_rows=unavailable_alert_hold_rows=0
    for track in tracks:
        out=apply_policy(track,policy); alerts.extend(out); lengths.extend(episode_lengths(out)); activation_events.extend(activation_delays(track,policy))
        available+=sum(x["state"]!="PHYSICAL_EVIDENCE_UNAVAILABLE" for x in track)
        conflicts+=sum(x["state"]=="PHYSICALLY_CONFLICTING" for x in track)
        available_alert_rows+=sum(bool(alert) and row["state"]!="PHYSICAL_EVIDENCE_UNAVAILABLE" for row,alert in zip(track,out))
        unavailable_alert_hold_rows+=sum(bool(alert) and row["state"]=="PHYSICAL_EVIDENCE_UNAVAILABLE" for row,alert in zip(track,out))
        if any(out): alert_aircraft.add(track[0]["aircraft"])
    alert_rows_all=sum(alerts); unavailable=len(rows)-available
    return {
        "eligible_rows":len(rows),"available_rows":available,"unavailable_rows":unavailable,
        "raw_conflicting_rows":conflicts,"track_segments":len(tracks),
        "aircraft":len({x["aircraft"] for x in rows}),
        "alert_rows_all_eligible":alert_rows_all,
        "alert_rows_on_available_evidence":available_alert_rows,
        "alert_hold_rows_on_unavailable_evidence":unavailable_alert_hold_rows,
        "alert_fraction_all_eligible_rows":alert_rows_all/len(rows) if rows else None,
        "alert_fraction_among_available_rows":available_alert_rows/available if available else None,
        "alert_episodes":len(lengths),
        "alert_episodes_per_1000_eligible":1000*len(lengths)/len(rows) if rows else None,
        "alert_episodes_per_1000_available":1000*len(lengths)/available if available else None,
        "aircraft_with_alert":len(alert_aircraft),
        "episode_length_observations":{"median":statistics.median(lengths) if lengths else None,"q95":sorted(lengths)[math.ceil(.95*len(lengths))-1] if lengths else None,"maximum":max(lengths) if lengths else None},
        "time_to_alert_seconds":delay_summary([x["seconds"] for x in activation_events]),
        "available_observations_to_alert":delay_summary([x["available_observations"] for x in activation_events]),
    }


def persistent_step_delay(policy):
    # Start from a clean inactive state and feed persistent conflicts.
    track=[{"state":"PHYSICALLY_CONSISTENT"} for _ in range(max(policy["n"],policy["clear_consistent"]))]
    apply_policy(track,policy)
    test=[{"state":"PHYSICALLY_CONFLICTING"} for _ in range(20)]
    out=apply_policy(test,policy)
    return next((i+1 for i,x in enumerate(out) if x),None)


def choose_policy(development_results):
    raw_rate=development_results["raw_1_of_1"]["alert_episodes_per_1000_available"]
    eligible=[]
    for name,p in POLICIES.items():
        delay=persistent_step_delay(p)
        rate=development_results[name]["alert_episodes_per_1000_available"]
        if delay is not None and delay<=2 and rate<=raw_rate+1e-12:
            eligible.append((p["k"],p["n"],name))
    return max(eligible)[2]


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--development-events",type=Path,required=True)
    p.add_argument("--subset1-events",type=Path,required=True)
    p.add_argument("--subset2-events",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    p.add_argument("--gap-seconds",type=float,default=30.0)
    a=p.parse_args()
    if a.gap_seconds<=0: p.error("--gap-seconds must be positive")
    started=time.perf_counter(); datasets={"development_validation":load_events(a.development_events),"subset1_frozen_test":load_events(a.subset1_events),"subset2_transfer":load_events(a.subset2_events)}
    results={name:{policy:summarize(rows,a.gap_seconds,spec) for policy,spec in POLICIES.items()} for name,rows in datasets.items()}
    selected=choose_policy(results["development_validation"])
    report={
        "schema":"sam.phase32.track-persistence-nuisance.v3",
        "scope":"development-selected temporal persistence and nuisance-alert analysis over Phase 31 physical decisions",
        "platform":{"system":platform.system(),"release":platform.release(),"machine":platform.machine(),"python":platform.python_version()},
        "configuration":{"track_gap_seconds":a.gap_seconds,"unavailable_handling":"does not add a vote; an already active alert is held and counted separately","candidate_policies":POLICIES,"selection_rule":"select the strongest candidate that activates within two available observations and does not exceed the raw development-validation episode rate","test_used_for_selection":False},
        "persistent_conflict_activation_delay_observations":{name:persistent_step_delay(spec) for name,spec in POLICIES.items()},
        "development_selection":{"selected_policy":selected,"development_metrics":results["development_validation"][selected]},
        "all_policy_results":results,
        "frozen_policy_results":{"subset1_frozen_test":results["subset1_frozen_test"][selected],"subset2_transfer":results["subset2_transfer"][selected]},
        "runtime":{"wall_seconds":time.perf_counter()-started},
        "interpretation_limits":[
            "Alert episodes are empirical nuisance-alert indicators on trusted-aircraft data, not population false-alarm rates.",
            "The persistence layer operates on Phase 31 decisions and cannot recover evidence that the physical branch marked unavailable.",
            "Persistent-conflict activation delay is measured in available observations; it is not a wall-clock attack-detection delay.",
            "The analysis does not use operational attack traffic or RF-labeled ground truth.",
            "Subset 2 is a same-infrastructure transfer partition, not an independent receiver network.",
        ],
    }
    a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"selected_policy":selected,"activation_delay":report["persistent_conflict_activation_delay_observations"][selected],"frozen_policy_results":report["frozen_policy_results"]},indent=2))

if __name__=="__main__": main()
