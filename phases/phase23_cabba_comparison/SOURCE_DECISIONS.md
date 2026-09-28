# Source and implementation decisions

Primary protocol source:

- M. Ngamboé et al., "CABBA: Compatible Authenticated Bandwidth-efficient
  Broadcast protocol for ADS-B," International Journal of Critical
  Infrastructure Protection, vol. 48, 100728, 2025.
  DOI: 10.1016/j.ijcip.2024.100728.
- Public preprint: arXiv:2312.09870.

Frozen published parameters used by this reproduction:

- Type A: ADS-B message, MAC, and 8-bit sequence number;
- maximum Type A MAC length: 196 bits;
- Type B1: 128-bit interval key;
- Type B2: 128-bit interval key and 512-bit signature;
- Type C: 256-bit conceptual aircraft public key and 512-bit CA signature;
- TESLA interval and B1 period: 5 seconds;
- Scenario 1: B2 5 s, C 5 s;
- Scenario 2: B2 10 s, C 15 s;
- Scenario 3: B2 10 s, C 20 s;
- Scenario 4: B2 15 s, C 30 s.

Source inconsistency:

- CABBA Table 3 explicitly reports Scenario 4 as `TB2=15 s`, `TC=30 s`.
- The accompanying prose describes B2 as occurring every other five-second
  TESLA interval, which would imply 10 s.
- Later uncertainty-delay Tables 4 and 5 state `TB2=TC=30 s`.
- This package uses the explicit Table 3 values for the four-scenario schedule
  comparison. It does not claim that the paper resolves the inconsistency.

Implementation choices not assigned to the CABBA authors:

- HMAC-SHA-256 is used because the public protocol description names HMAC but
  does not identify its digest.
- P-256/SHA-256 with fixed-width 64-byte r||s signatures instantiates the
  paper's 128-bit-security and 512-bit-signature description.
- A compressed SEC1 public key is used internally by the Python prototype.
  Published wire-size accounting remains separate from this software encoding.
- Key derivation and key-chain hashing are domain-separated SHA-256 operations.

The report labels these as reproduction choices. RF/phase-overlay and Reed-
Solomon behavior are outside the experiment and no result is claimed for them.
