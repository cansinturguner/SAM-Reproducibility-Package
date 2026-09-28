# SAM Phase 16 Communication Overhead and Scheduling Sensitivity

This phase measures the logical communication cost of the implemented SAM
cryptographic protocol elements. It does not claim a DO-260C or ED-102B RF
mapping and does not estimate 1090 MHz channel occupancy.

Run from the `sam_phase1` project directory with the existing virtual
environment active:

```bash
python ~/Downloads/sam_phase16_communication_overhead/scripts/evaluate_overhead.py \
  --report reports/sam_phase16_communication_overhead.json \
  --seed 1103 \
  --duration-seconds 3600 \
  --message-rates 2,6.2,10 \
  --aircraft-counts 1,50,200 \
  --b2-period-seconds 60
```

Validate the report:

```bash
python ~/Downloads/sam_phase16_communication_overhead/scripts/validate_report.py \
  reports/sam_phase16_communication_overhead.json
```

The package models these logical security objects:

- Type A: one-byte sequence plus 16-byte HMAC tag per surveillance message;
- B1: 16-byte disclosed interval key;
- B2: 16-byte interval key plus 64-byte ECDSA signature;
- compact CA record: 97 bytes, fetched through the trust service and reported
  separately from the broadcast security stream.

The default policy matrix varies the TESLA interval and B1/B2 repetition count.
All quantities are exact deterministic accounting results. They exclude RF
framing, Phase Overlay encoding, FEC, modulation, certificates beyond the
compact prototype, retransmission scheduling, and ledger traffic.

