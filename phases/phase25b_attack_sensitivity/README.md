# SAM Phase 25B — Controlled Attack Sensitivity

Phase 25B applies the frozen Phase 25A decision to controlled physical-state
perturbations on the subset-1 test observations:

- deterministic position offsets from 100 m through 10 km, including the
  400–1000 m range used in the published scenario family;
- a fixed ground-spoofer/fake-track arrival-time scenario.

The threat-model source is Leonardi and Sirbu, *Sensors* 21(15), 4992 (2021),
DOI `10.3390/s21154992`. This phase independently adapts the two scenario
families to SAM. It does **not** reproduce their EKF, T1/T2 detector, code, or
reported results.

## Run

Run Phase 25A first, then:

```bash
bash phases/phase25b_attack_sensitivity/run_phase.sh
```

The output is controlled conflict sensitivity. It is not real-world detection
accuracy and must not be reported as precision, recall, F1, or certified attack
detection probability.
