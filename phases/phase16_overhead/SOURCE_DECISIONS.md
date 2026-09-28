# Source decisions and claim boundary

The byte counts are frozen from the implemented Phase 8-10 prototypes and the
Phase 13 consolidation:

- sequence plus HMAC tag: 17 bytes per Type-A object;
- disclosed interval key: 16 bytes per B1 object;
- signed interval-key content: 80 bytes per B2 object;
- compact signed aircraft-key record: 97 bytes per trust lookup.

The experiment deliberately reports **logical security bytes**, not RF channel
occupancy. A standards-conformant mapping would require a justified Phase
Overlay frame format, FEC, repetition and scheduling design that has not been
implemented. The 14-byte surveillance message is used only as a comparison
denominator for a logical overhead ratio.

No attack/anomaly labels, classifier, precision, recall, F1, false-positive or
false-negative metric are created.

