# Phase 35 source decisions

1. The burst-loss model is a controlled two-state Gilbert-Elliott process. Its
   parameters are sensitivity conditions, not fitted 1090 MHz channel values.
2. A late Type-A packet is accepted for delayed verification only if its arrival
   plus the receiver's stated clock-uncertainty bound precedes key disclosure.
3. The 8-bit sequence value is scoped to a TESLA interval. The authenticated
   tuple is `(interval, sequence, payload)`. A 257th message in one interval is
   rejected rather than silently wrapping.
4. Once authenticated secure capability has been established for an aircraft,
   a legacy-routed observation cannot be promoted to the secure track. It
   becomes `INSUFFICIENT_EVIDENCE` with a downgrade reason; explicit invalidity
   remains `CONFLICTING`.

