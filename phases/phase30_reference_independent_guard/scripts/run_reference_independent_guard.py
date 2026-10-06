#!/usr/bin/env python3
"""Evaluate a development-calibrated, reference-independent receiver guard."""
from __future__ import annotations
import argparse, csv, gzip, hashlib, json, os, platform, sys, time
from pathlib import Path
import numpy as np

P27 = Path(os.environ.get("SAM_PHASE27_SCRIPTS", str(Path(__file__).resolve().parents[2] / "phase27_threshold_aware_integration" / "scripts")))
if not P27.exists():
    raise SystemExit("Phase 27 is required: phases/phase27_threshold_aware_integration/scripts")
sys.path.insert(0, str(P27))
import threshold_core as core  # noqa: E402

MAGNITUDES = (100, 250, 500, 750, 1000, 2000, 5000, 10000)

def aircraft_group(aircraft, seed, calibration_percent):
    token = f"{seed}|{aircraft}".encode()
    return "calibration" if int.from_bytes(hashlib.sha256(token).digest()[:8], "big") % 100 < calibration_percent else "validation"

def context(row, sensors, biases, modeled):
    lat, lon = core.finite(row.get("latitude")), core.finite(row.get("longitude"))
    alt = core.finite(row.get("geoAltitude"))
    if alt is None: alt = core.finite(row.get("baroAltitude"))
    if None in (lat, lon, alt): return None, "missing_position_or_altitude"
    try: observed = core.measurements(row.get("goodMeasurements", "[]"), modeled)
    except (json.JSONDecodeError, TypeError): observed = []
    if len(observed) < 4: return None, "fewer_than_4_modeled_receivers"
    if not core.rank3([sensors[sid] for sid, _ in observed]): return None, "rank_below_3"
    xyz = core.ecef(lat, lon, alt)
    ids = [sid for sid, _ in observed]
    delays = np.asarray([np.linalg.norm(xyz - sensors[sid]) / core.C * 1e9 for sid in ids])
    corrected = np.asarray([ts - biases[sid] for sid, ts in observed])
    return {"sensor_ids": ids, "errors_ns": corrected - delays}, None

def current_score(errors):
    return float(np.median(np.abs(errors[1:] - errors[0])))

def receiver_scores(errors):
    matrix = np.abs(errors[:, None] - errors[None, :])
    return np.asarray([np.median(np.delete(matrix[i], i)) for i in range(len(errors))], dtype=float)

def guard_score(errors):
    return float(np.max(receiver_scores(errors)))

def qhigher(values, q):
    return float(np.quantile(np.asarray(values), q, method="higher"))

def method_acc():
    return {"trials":0,"baseline_consistent_trials":0,"baseline_conflicting_trials":0,"result_conflicting":0,"consistent_to_conflicting":0,"conflicting_to_consistent":0}

def update_method(a, baseline, result):
    a["trials"] += 1
    if baseline:
        a["baseline_conflicting_trials"] += 1
        if not result: a["conflicting_to_consistent"] += 1
    else:
        a["baseline_consistent_trials"] += 1
        if result: a["consistent_to_conflicting"] += 1
    if result: a["result_conflicting"] += 1

def finish_method(a):
    out = dict(a); n=a["trials"]; bc=a["baseline_consistent_trials"]; bx=a["baseline_conflicting_trials"]
    out["result_conflict_fraction_all_trials"] = a["result_conflicting"]/n if n else None
    out["consistent_to_conflicting_fraction"] = a["consistent_to_conflicting"]/bc if bc else None
    out["conflicting_to_consistent_fraction"] = a["conflicting_to_consistent"]/bx if bx else None
    return out

def trial_acc():
    return {"current":method_acc(),"guard":method_acc(),"combined":method_acc(),"guard_conflicting":0,"target_highest":0,"guard_and_target_highest":0}

def update_trial(a, bc, bg, rc, rg, highest):
    update_method(a["current"], bc, rc); update_method(a["guard"], bg, rg); update_method(a["combined"], bc or bg, rc or rg)
    if rg: a["guard_conflicting"] += 1
    if highest: a["target_highest"] += 1
    if rg and highest: a["guard_and_target_highest"] += 1

def finish_trial(a):
    n=a["current"]["trials"]; gc=a["guard_conflicting"]
    return {"current_reference_rule":finish_method(a["current"]),"reference_independent_guard":finish_method(a["guard"]),"combined_rule":finish_method(a["combined"]),"target_ranked_highest_fraction_all_trials":a["target_highest"]/n if n else None,"target_ranked_highest_given_guard_conflict":a["guard_and_target_highest"]/gc if gc else None}

def cluster_ci(scores, aircraft, threshold, seed):
    scores=np.asarray(scores); aircraft=np.asarray(aircraft); unique,inverse=np.unique(aircraft,return_inverse=True)
    totals=np.bincount(inverse); conflicts=np.bincount(inverse,weights=(scores>threshold).astype(float)); rng=np.random.default_rng(seed); draws=[]
    for _ in range(2000):
        d=rng.integers(0,len(unique),size=len(unique)); draws.append(conflicts[d].sum()/totals[d].sum())
    low,high=np.quantile(draws,[.025,.975])
    return {"method":"aircraft-cluster bootstrap with replacement; row-weighted conflict fraction","estimate":float(np.mean(scores>threshold)),"ci95_low":float(low),"ci95_high":float(high),"replicates":2000,"seed":seed,"aircraft":len(unique)}

def main():
    p=argparse.ArgumentParser()
    for name in ("selected","sensors","calibration","decision_model","report"): p.add_argument("--"+name.replace("_","-"),dest=name,type=Path,required=True)
    p.add_argument("--magnitudes-ns",type=int,nargs="+",default=MAGNITUDES); p.add_argument("--skip-hash-check",action="store_true"); a=p.parse_args()
    mags=sorted(set(a.magnitudes_ns))
    if not mags or any(x<=0 for x in mags): p.error("magnitudes must be positive")
    started=time.perf_counter(); model=core.load_decision_model(a.decision_model)
    hashes=core.verify_model_inputs(model,a.selected,a.sensors,a.calibration,a.skip_hash_check)
    seed=int(model["seed"]); calpct=int(model["calibration_percent"]); current_threshold=float(model["threshold_ns"])
    sensors=core.load_sensors(a.sensors); biases=core.load_biases(a.calibration); modeled=set(sensors)&set(biases)
    dev=[]; current=[]; guard=[]; aircraft=[]; contexts=[]
    counts={"development_validation_original_ge4":0,"development_validation_available":0,"subset1_test_original_ge4":0,"subset1_test_available":0,"subset1_test_unavailable":0}; unavailable={}
    with gzip.open(a.selected,"rt",newline="",encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not core.truthy(row.get("eligible_ge4")): continue
            split=row.get("split","").strip().lower(); ac=str(row.get("aircraft","")).strip()
            isdev=split=="development" and aircraft_group(ac,seed,calpct)=="validation"; istest=split=="test"
            if not (isdev or istest): continue
            counts["development_validation_original_ge4" if isdev else "subset1_test_original_ge4"] += 1
            c,reason=context(row,sensors,biases,modeled)
            if c is None:
                if istest: counts["subset1_test_unavailable"]+=1; unavailable[reason]=unavailable.get(reason,0)+1
                continue
            cs,gs=current_score(c["errors_ns"]),guard_score(c["errors_ns"])
            if isdev: counts["development_validation_available"]+=1; dev.append(gs)
            else: counts["subset1_test_available"]+=1; current.append(cs); guard.append(gs); aircraft.append(ac); contexts.append(c)
    guard_threshold=qhigher(dev,.99); current=np.asarray(current); guard=np.asarray(guard); bc=current>current_threshold; bg=guard>guard_threshold; combined=bc|bg
    trials={m:{g:trial_acc() for g in ("all_receivers","decision_reference","nonreference")} for m in mags}
    for row_index,c in enumerate(contexts):
        errors=c["errors_ns"]
        for m in mags:
            for sign in (-1,1):
                for target in range(len(errors)):
                    shifted=errors.copy(); shifted[target]+=sign*m; rc=current_score(shifted)>current_threshold; rs=receiver_scores(shifted); rg=float(np.max(rs))>guard_threshold
                    highest=target in np.flatnonzero(np.isclose(rs,np.max(rs),rtol=0,atol=1e-12))
                    for group in ("all_receivers","decision_reference" if target==0 else "nonreference"): update_trial(trials[m][group],bool(bc[row_index]),bool(bg[row_index]),rc,rg,highest)
    def base_result(mask): return {"consistent_rows":int(np.sum(~mask)),"conflicting_rows":int(np.sum(mask)),"empirical_benign_reference_conflict_fraction_among_available":float(np.mean(mask))}
    baseline={"current_reference_rule":base_result(bc)|{"threshold_ns":current_threshold,"aircraft_cluster_ci95":cluster_ci(current,aircraft,current_threshold,seed)},"reference_independent_guard":base_result(bg)|{"threshold_ns":guard_threshold,"threshold_source":"development-validation q99, higher order statistic","aircraft_cluster_ci95":cluster_ci(guard,aircraft,guard_threshold,seed)},"combined_rule":base_result(combined)|{"condition":"current conflict OR guard conflict"}}
    report={"schema":"sam.phase30.reference-independent-receiver-guard.v1","scope":"development-calibrated candidate guard for single-receiver timestamp corruption","platform":{"system":platform.system(),"release":platform.release(),"machine":platform.machine(),"python":platform.python_version(),"numpy":np.__version__},"inputs":{"sha256":hashes},"method":{"current_score":"median absolute residual against first sorted receiver","candidate_receiver_score":"median absolute pair residual incident on each receiver","candidate_observation_score":"maximum receiver score","candidate_reference_independent":True,"guard_threshold_quantile":.99,"guard_threshold_selected_on":"development-validation aircraft only","test_used_for_threshold_selection":False,"controlled_corruption":"one receiver shifted by both signs"},"counts":counts,"unavailable_reasons":unavailable,"baseline_benign_reference":baseline,"timestamp_corruption":{str(m):{g:finish_trial(x) for g,x in groups.items()} for m,groups in trials.items()},"runtime":{"wall_seconds":time.perf_counter()-started},"interpretation_limits":["The candidate guard is evaluated, not automatically adopted into the frozen SAM policy.","The benign result is an empirical benign-reference conflict fraction, not a population false-positive rate.","Controlled timestamp shifts are sensitivity conditions, not real-world attack-detection rates.","Target ranking is not proof of receiver compromise.","The experiment uses the same LocaRDS subset-1 sensor network and frozen clock model."]}
    a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"guard_threshold_ns":guard_threshold,"baseline_benign_reference":baseline,"timestamp_corruption":report["timestamp_corruption"]},indent=2))

if __name__=="__main__": main()
