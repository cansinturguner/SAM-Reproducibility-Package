# Phase 9 source and scope decisions

The protocol structure is based on M. Ngamboé et al., “CABBA: Compatible
Authenticated Bandwidth-efficient Broadcast protocol for ADS-B,”
*International Journal of Critical Infrastructure Protection*, vol. 48,
Art. 100728, 2025.

Source-defined elements used here:

- one-way TESLA key chain;
- per-interval message authentication keys derived from interval keys;
- buffering until delayed key disclosure;
- 128-bit interval keys;
- B1 disclosure in the next interval;
- an 8-bit sequence number in Type A security data;
- a left-truncated HMAC with `lambda <= 196` bits.

Explicit Phase 9 experimental choices:

- one-second intervals;
- HMAC-SHA3-256 and a 128-bit transmitted tag, aligned with Phase 8;
- ten-minute synthetic workload at 6.2 messages/s;
- equal, independent Type-A and B1 reception-loss probabilities;
- 200 deterministic Monte Carlo replicates per loss setting.

These choices are recorded in the JSON report and are not represented as
mandatory CABBA, DO-260C, or ED-102B parameters.

Deferred:

- ECDSA-signed B2 keys and Type-C certificates;
- certificate validation and trust-service availability;
- Phase Overlay waveform, RS FEC, BER, and RF channel occupancy;
- fusion with Phase 1–7 physical evidence;
- avionics hardware and certification evidence.

