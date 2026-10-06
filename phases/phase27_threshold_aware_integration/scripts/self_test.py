#!/usr/bin/env python3
"""Dependency-light semantic checks that do not require LocaRDS files."""

import threshold_core as core


threshold = 306.64062122826
assert core.classify_score(None, threshold) == core.PHYSICAL_EVIDENCE_UNAVAILABLE
assert core.classify_score(threshold, threshold) == core.PHYSICALLY_CONSISTENT
assert core.classify_score(threshold + 1e-6, threshold) == core.PHYSICALLY_CONFLICTING

assert core.fuse("VERIFIED", "VALID", core.PHYSICALLY_CONSISTENT) == "VERIFIED"
assert core.fuse("VERIFIED", "VALID", core.PHYSICALLY_CONFLICTING) == "CONFLICTING"
assert core.fuse("VERIFIED", "STALE", core.PHYSICALLY_CONSISTENT) == "INSUFFICIENT_EVIDENCE"
assert core.fuse("VERIFIED", "STALE", core.PHYSICALLY_CONFLICTING) == "CONFLICTING"
assert core.fuse("CONFLICTING", "VALID", core.PHYSICALLY_CONSISTENT) == "CONFLICTING"
assert core.fuse("VERIFIED", "REVOKED", core.PHYSICAL_EVIDENCE_UNAVAILABLE) == "CONFLICTING"

print("SAM Phase 27 semantic self-test passed.")

