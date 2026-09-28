#!/usr/bin/env python3
import hashlib
from pathlib import Path


EXPECTED = {
    "data/raw/locards/subset_1/set_1.csv": "6295f7f04afeecd997c329dc0b12712f81723a2fe4d1a7b8b8ea01727eef0ccf",
    "data/raw/locards/subset_1/set_1_sensors.csv": "998a63f5fc89fa41fd1a37468431da96f355812054e7bca8b2a4f4db0ba47d1b",
    "data/raw/locards/subset_1/set_1_aircraft.csv": "62b5b48bd66783074b2c9de65a5edd4de8f9f579f1fc05f3aabb9cb49a5a1a03",
    "data/raw/locards/subset_2/set_2.csv": "5ff68c7e402caa183678c03f4d23ba45b63bc96fa1177f8ce7e4fb530c45dd58",
    "data/raw/locards/subset_2/set_2_sensors.csv": "998a63f5fc89fa41fd1a37468431da96f355812054e7bca8b2a4f4db0ba47d1b",
    "data/raw/locards/subset_2/set_2_aircraft.csv": "70156a0865e655f4fb470e5814fd153708ac9f97ef193b70ebf3f4a5d84e1893",
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    failures = []
    for name, expected in EXPECTED.items():
        path = Path(name)
        if not path.is_file():
            failures.append(f"MISSING {name}")
            continue
        actual = sha256(path)
        status = "OK" if actual == expected else "HASH_MISMATCH"
        print(f"{status} {name} {actual}")
        if actual != expected:
            failures.append(f"HASH_MISMATCH {name}")
    if failures:
        raise SystemExit("Input verification failed:\n" + "\n".join(failures))
    print("All LocaRDS input hashes verified.")


if __name__ == "__main__":
    main()

