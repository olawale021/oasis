"""Model registry (PRD 17.3).

Append-only JSON registry at data/models/registry.json. Each entry records,
for one model artifact release: version label, artifact file + sha256
checksum, model type, training window, feature list, key hyperparameters,
calibration method, validation/test metrics, registration timestamp, and
whether it is the deployed artifact for its role.

A given (artifact, checksum) is registered once -- re-registering an
unchanged file is a no-op, while a retrain (new checksum) appends a new
entry and, if deployed, demotes the previous deployed entry for that role.
Entries are never deleted or rewritten beyond that `deployed` flip, so the
registry doubles as the deployment log required by PRD 18.4.

Training scripts call `register()` automatically after writing an artifact.
CLI:

    python3 src/model_registry.py list
    python3 src/model_registry.py register data/models/outcome_model_pl.json --deployed
    python3 src/model_registry.py verify
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import config

REGISTRY_PATH = config.MODELS_DIR / "registry.json"

# Fields worth copying into the registry per artifact type. Large numeric
# blobs (coefficients, trees) stay in the artifact; the checksum covers them.
METRIC_KEYS = (
    "test_log_loss",
    "test_accuracy",
    "test_rps",
    "test_draw_log_loss",
    "test_exact_score_accuracy",
    "test_ou_ece",
    "test_btts_ece",
)
PARAM_KEYS = ("decay", "alpha", "temperature", "intercept", "home_flag_coef", "rho", "num_class", "params")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_registry() -> list:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text())
    return []


def _write_registry(entries: list) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(entries, indent=2, ensure_ascii=False))


def _role_of(artifact_path: Path) -> str:
    """The deployment slot an artifact competes for -- its filename stem
    (e.g. outcome_model_pl, goals_model). One deployed entry per role."""
    return artifact_path.stem


def artifact_features(artifact: dict) -> list | None:
    """Feature list for the registry row. A blend has none at its top level;
    report the ordered union across its components (recursively), so the
    performance page's 'N features' is meaningful for blends too."""
    if artifact.get("type") == "blend":
        seen = []
        for c in artifact.get("components", []):
            for f in artifact_features(c["model"]) or []:
                if f not in seen:
                    seen.append(f)
        return seen or None
    return artifact.get("features")


def build_entry(artifact_path: Path, deployed: bool, notes: str = None) -> dict:
    artifact = json.loads(artifact_path.read_text())
    version = artifact.get("label") or artifact.get("type") or artifact_path.stem
    return {
        "version": version.split(" ")[0],
        "role": _role_of(artifact_path),
        "artifact": str(artifact_path.relative_to(config.ROOT_DIR)),
        "checksum_sha256": _sha256(artifact_path),
        "model_type": artifact.get("type"),
        "training_window": artifact.get("trained_on"),
        "selected_on": artifact.get("selected_on"),
        "features": artifact_features(artifact),
        "parameters": {k: artifact[k] for k in PARAM_KEYS if k in artifact},
        "calibration": (
            f"temperature scaling (T={artifact['temperature']})" if "temperature" in artifact else None
        ),
        "metrics": {k: artifact[k] for k in METRIC_KEYS if k in artifact},
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "deployed": deployed,
        "notes": notes,
    }


def register(artifact_path: Path, deployed: bool = False, notes: str = None) -> dict:
    """Idempotent: an unchanged artifact is not re-registered (its existing
    entry is returned, with the deployed flag promoted if newly deployed)."""
    artifact_path = Path(artifact_path).resolve()
    entries = _load_registry()
    checksum = _sha256(artifact_path)
    role = _role_of(artifact_path)

    existing = next((e for e in entries if e["checksum_sha256"] == checksum and e["role"] == role), None)
    if existing:
        if deployed and not existing["deployed"]:
            for e in entries:
                if e["role"] == role:
                    e["deployed"] = e is existing
            existing["deployed_at"] = datetime.now(timezone.utc).isoformat()
            _write_registry(entries)
        return existing

    entry = build_entry(artifact_path, deployed, notes)
    if deployed:
        for e in entries:
            if e["role"] == role:
                e["deployed"] = False
        entry["deployed_at"] = entry["registered_at"]
    entries.append(entry)
    _write_registry(entries)
    return entry


class UnregisteredModelError(RuntimeError):
    pass


def verify_deployed(artifact_path: Path) -> dict:
    """Guard for serving paths (predict/export): the artifact must be the
    registered, deployed release for its role, byte-for-byte. Raises
    UnregisteredModelError otherwise -- predictions must never be generated
    from an artifact the registry cannot account for (PRD 17.3/17.4)."""
    artifact_path = Path(artifact_path).resolve()
    role = _role_of(artifact_path)
    entry = next((e for e in _load_registry() if e["role"] == role and e["deployed"]), None)
    if entry is None:
        raise UnregisteredModelError(
            f"no deployed registry entry for role {role!r} -- run: python3 src/model_registry.py register {artifact_path} --deployed"
        )
    actual = _sha256(artifact_path)
    if actual != entry["checksum_sha256"]:
        raise UnregisteredModelError(
            f"{artifact_path.name} does not match the deployed registry entry "
            f"(registry {entry['checksum_sha256'][:12]}… vs disk {actual[:12]}…). "
            f"The artifact changed without being registered -- retrain via the training script "
            f"(which auto-registers) or register it explicitly."
        )
    return entry


def verify() -> list:
    """Recompute checksums for every registered artifact still on disk.
    Returns a list of problems (empty = clean)."""
    problems = []
    for e in _load_registry():
        path = config.ROOT_DIR / e["artifact"]
        if not path.exists():
            if e["deployed"]:
                problems.append(f"DEPLOYED artifact missing: {e['artifact']} ({e['version']})")
            continue
        actual = _sha256(path)
        if e["deployed"] and actual != e["checksum_sha256"]:
            problems.append(
                f"checksum mismatch for deployed {e['artifact']}: registry {e['checksum_sha256'][:12]}… "
                f"vs disk {actual[:12]}… — the artifact changed without being registered"
            )
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description="Model registry (PRD 17.3).")
    sub = parser.add_subparsers(dest="command", required=True)

    p_register = sub.add_parser("register", help="Register a model artifact")
    p_register.add_argument("artifact", type=Path)
    p_register.add_argument("--deployed", action="store_true", help="Mark as the deployed artifact for its role")
    p_register.add_argument("--notes", type=str, default=None)

    sub.add_parser("list", help="List registry entries")
    sub.add_parser("verify", help="Check registered checksums against artifacts on disk")

    args = parser.parse_args()

    if args.command == "register":
        entry = register(args.artifact, deployed=args.deployed, notes=args.notes)
        flag = " [deployed]" if entry["deployed"] else ""
        print(f"registered {entry['role']} {entry['version']}{flag} sha256={entry['checksum_sha256'][:12]}…")
    elif args.command == "list":
        entries = _load_registry()
        if not entries:
            print("registry is empty")
        for e in entries:
            flag = " [deployed]" if e["deployed"] else ""
            metrics = e.get("metrics") or {}
            headline = f" · test_log_loss={metrics['test_log_loss']:.4f}" if "test_log_loss" in metrics else ""
            print(
                f"{e['registered_at'][:19]}  {e['role']:<24} {e['version']:<16}{flag}"
                f" sha256={e['checksum_sha256'][:12]}…{headline}"
            )
    elif args.command == "verify":
        problems = verify()
        if problems:
            for p in problems:
                print(f"PROBLEM: {p}")
            raise SystemExit(1)
        print(f"registry clean ({len(_load_registry())} entries)")


if __name__ == "__main__":
    main()
