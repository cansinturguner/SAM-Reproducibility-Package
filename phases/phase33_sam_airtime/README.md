# Phase 33 — SAM reference transport and analytical airtime

Phase 33 closes the distinction between logical security bytes and RF airtime.
It defines one explicit, bounded reference transport using only parameters
already exercised by the package:

- 204 usable security bits per PPM/D8PSK overlay frame (Phase 24);
- 120 microseconds per legacy-readable carrier frame (Phase 23 comparator);
- Type-A material is overlaid on the corresponding surveillance frame;
- B1 and B2 objects use additional carrier frames and are fragmented by the
  204-bit usable overlay capacity.

This is an analytical reference profile, not a DO-260C/ED-102B allocation,
certified waveform, or commercial-receiver compatibility claim.  It makes the
transport assumption visible and allows SAM and CABBA airtime quantities to be
reported with explicit boundaries.

Run:

```bash
python phases/phase33_sam_airtime/scripts/run_phase33.py \
  --report reports/sam_phase33_sam_airtime.json
python phases/phase33_sam_airtime/scripts/validate_report.py \
  reports/sam_phase33_sam_airtime.json
```

The default sensitivity matrix uses the Phase 16 message rates and policies.
The canonical row is 6.2 messages/s, 200 aircraft, a one-second key interval,
one B1 transmission per interval, one B2 transmission per 60 seconds, and a
one-hour accounting horizon.

