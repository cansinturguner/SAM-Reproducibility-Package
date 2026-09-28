import importlib
import platform
import sys


PACKAGES = [
    "numpy",
    "pandas",
    "scipy",
    "pyarrow",
    "matplotlib",
    "seaborn",
    "statsmodels",
    "cryptography",
    "psutil",
    "pyModeS",
]


def main() -> None:
    print(f"Python {sys.version.split()[0]}")
    print(f"Machine {platform.machine()}")
    failed = []
    for package in PACKAGES:
        try:
            module = importlib.import_module(package)
            version = getattr(module, "__version__", "installed")
            print(f"OK {package} {version}")
        except Exception as exc:
            failed.append((package, str(exc)))
            print(f"FAILED {package}: {exc}")
    if failed:
        raise SystemExit(1)
    print("SAM Phase 1 environment verification passed.")


if __name__ == "__main__":
    main()
