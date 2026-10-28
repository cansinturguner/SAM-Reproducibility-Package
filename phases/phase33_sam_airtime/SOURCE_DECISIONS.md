# Phase 33 source decisions

1. The 204-bit usable overlay field comes from the Phase 24 modeled layout:
   12 reference bits, 204 security bits, and 120 parity bits.
2. The 120-microsecond carrier-frame duration is the same legacy Type-A
   comparator used by Phase 23.
3. A Type-A object is bound to an existing surveillance frame and therefore
   does not create an additional frame in this reference profile.
4. B1 and B2 objects are conservatively fragmented into additional frames:
   `ceil(object_bits / 204)` frames per transmission.
5. Fragment identifiers, object identifiers, and any additional transport
   header are not specified by the current prototype. The calculation therefore
   reports a lower bound under the stated 204-bit usable-payload assumption.
6. CABBA Scenario 4 is recomputed with the equations and published packet
   durations already used in Phase 23. It is a comparator, not evidence that
   SAM and CABBA provide identical functions.

