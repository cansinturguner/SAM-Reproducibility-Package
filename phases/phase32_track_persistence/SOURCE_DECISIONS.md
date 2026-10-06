# Source decisions

- Inputs: Phase 31 development, subset-1 test, and subset-2 event streams.
- Track segmentation: same aircraft; a new segment begins after a gap greater than 30 seconds.
- Candidate online policies: raw 1-of-1, 2-of-3 with three-clean clearing, 3-of-5 with three-clean clearing, and three-consecutive with three-clean clearing.
- Selection: development-validation only; at most two available observations to activate under persistent conflict; choose the strongest candidate whose nuisance-episode rate does not exceed the raw rule.
- Unavailable evidence supplies no vote; an already active alert is held.
- Delay is reported in observations, not seconds.
