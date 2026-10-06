# Phase 32 — Track-level persistence and nuisance-alert analysis

Phase 32 consumes the per-observation event files produced by Phase 31. It segments observations by aircraft and a fixed 30-second gap, compares four causal persistence policies, and selects a policy using development-validation data only.

The frozen selection rule chooses the strongest candidate that activates within at most two available observations under persistent conflict and does not exceed the raw development-validation alert-episode rate. The selected policy is then applied unchanged to the aircraft-disjoint subset-1 test and subset-2 transfer partition.

`PHYSICAL_EVIDENCE_UNAVAILABLE` does not add a vote; an alert that is already active is held. Version 2 reports held-unavailable alert rows separately and provides two consistent fractions: all eligible rows and available-evidence rows. Reported alert episodes are nuisance indicators on trusted-aircraft data, not population false-alarm estimates.
