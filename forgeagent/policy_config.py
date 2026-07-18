"""Optional, narrowing-only project policy loaded from ``forgeagent-policy.yml``.

This module intentionally does not import PyYAML until a policy file exists.
Any missing dependency, parse failure, malformed value, or unexpected error
returns the immutable hardcoded baseline instead of changing runtime behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet


# These are duplicated as immutable floors only to compute restrictions. The
# policy file is always intersected/unioned with the runtime's authoritative
# constants by the consuming modules.
BASELINE_ALLOWED_IMPORTS = frozenset({"collections", "csv", "datetime", "json", "math", "re", "statistics", "string"})
BASELINE_REQUIRED_PROOF_CATEGORIES = frozenset({"normal", "edge", "contract"})
POLICY_FILENAME = "forgeagent-policy.yml"


@dataclass(frozen=True)
class EffectivePolicy:
    allowed_imports: FrozenSet[str]
    required_proof_categories: FrozenSet[str]
    require_human_review: bool
    trusted_signer_keys: FrozenSet[str] | None


def baseline_policy() -> EffectivePolicy:
    return EffectivePolicy(
        allowed_imports=BASELINE_ALLOWED_IMPORTS,
        required_proof_categories=BASELINE_REQUIRED_PROOF_CATEGORIES,
        require_human_review=False,
        trusted_signer_keys=None,
    )


def load_policy(root: str | Path = ".") -> EffectivePolicy:
    """Load a valid project policy or return the exact hardcoded baseline."""
    path = Path(root) / POLICY_FILENAME
    if not path.is_file():
        return baseline_policy()
    try:
        import yaml  # Optional dependency; never needed without a policy file.

        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return _narrowing_policy(raw)
    except Exception:
        return baseline_policy()


def _narrowing_policy(raw: object) -> EffectivePolicy:
    if raw is None:
        return baseline_policy()
    if not isinstance(raw, dict):
        raise ValueError("policy root must be a mapping")

    allowed = _string_list(raw.get("allowed_imports"), "allowed_imports", required=False)
    required = _string_list(raw.get("required_proof_categories"), "required_proof_categories", required=False)
    signers = _string_list(raw.get("trusted_signer_keys"), "trusted_signer_keys", required=False)
    for key in ("auto_promotion_rules", "deployment_restrictions"):
        if key in raw and not isinstance(raw[key], (bool, str, list, dict, type(None))):
            raise ValueError(f"{key} must be a scalar, list, or mapping")

    # These operations are the security boundary: configuration never receives
    # a direct assignment to an effective permission set.
    effective_imports = BASELINE_ALLOWED_IMPORTS if allowed is None else BASELINE_ALLOWED_IMPORTS & frozenset(allowed)
    effective_proofs = BASELINE_REQUIRED_PROOF_CATEGORIES | frozenset(required or ())
    force_review = any(bool(raw.get(key)) for key in ("auto_promotion_rules", "deployment_restrictions"))
    return EffectivePolicy(
        allowed_imports=effective_imports,
        required_proof_categories=effective_proofs,
        require_human_review=force_review,
        trusted_signer_keys=frozenset(signers) if signers is not None else None,
    )


def _string_list(value: object, label: str, required: bool) -> list[str] | None:
    if value is None:
        if required:
            raise ValueError(f"{label} is required")
        return None
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{label} must be a list of non-empty strings")
    return value
