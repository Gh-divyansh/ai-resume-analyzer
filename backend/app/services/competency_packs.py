"""Loading and deterministic validation for inactive competency packs."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

from pydantic import ValidationError

from app.schemas.domain_evidence import CompetencyPack, normalize_pack_alias


PACK_ROOT = Path(__file__).resolve().parents[1] / "packs"
TECHNOLOGY_CORE_PATH = PACK_ROOT / "technology-core" / "1.json"
NONTECHNICAL_PACK_PATHS = tuple(
    PACK_ROOT / pack / "1.json"
    for pack in (
        "healthcare-core", "education-core", "finance-core", "sales-core", "hr-core", "marketing-core",
        "design-core", "engineering-core", "hospitality-core", "legal-core", "customer-service-core", "trades-core",
    )
)


class PackStatus(str, Enum):
    inactive = "inactive"
    active = "active"
    needs_calibration = "needs_calibration"


# Explicit release gate. A pack can be loaded for offline calibration without
# being eligible to influence production matching.
NONTECHNICAL_PACK_STATUS = {
    "healthcare-core": PackStatus.active,
    "education-core": PackStatus.needs_calibration,
    "finance-core": PackStatus.needs_calibration,
    "sales-core": PackStatus.needs_calibration,
    "hr-core": PackStatus.needs_calibration,
    "marketing-core": PackStatus.needs_calibration,
    "design-core": PackStatus.needs_calibration,
    "engineering-core": PackStatus.needs_calibration,
    "hospitality-core": PackStatus.needs_calibration,
    "legal-core": PackStatus.needs_calibration,
    "customer-service-core": PackStatus.needs_calibration,
    "trades-core": PackStatus.needs_calibration,
}


def load_pack(path: Path) -> CompetencyPack:
    """Load one pack and surface malformed metadata/data as a clear ValueError."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"Competency pack was not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Competency pack contains invalid JSON: {path}") from error

    try:
        return CompetencyPack.model_validate(payload)
    except ValidationError as error:
        raise ValueError(f"Invalid competency pack '{path.name}': {error}") from error


def load_technology_core() -> CompetencyPack:
    """Load the inactive compatibility pack with explicit metadata checks."""

    pack = load_pack(TECHNOLOGY_CORE_PATH)
    if (pack.pack_id, pack.version, pack.namespace) != ("technology-core", "1", "technology"):
        raise ValueError("technology-core compatibility pack metadata is invalid.")
    return pack


def load_nontechnical_packs() -> list[CompetencyPack]:
    """Load inactive, bounded cross-domain packs for offline calibration only."""

    return [load_pack(path) for path in NONTECHNICAL_PACK_PATHS]


def load_active_nontechnical_packs() -> list[CompetencyPack]:
    """Return only release-approved packs for the additive production layer."""

    return [pack for pack in load_nontechnical_packs() if NONTECHNICAL_PACK_STATUS[pack.pack_id] is PackStatus.active]


def alias_map(pack: CompetencyPack) -> dict[str, tuple[str, ...]]:
    """Expose a display-name-to-aliases mapping for parity checks only."""

    return {concept.display_name: tuple(concept.aliases) for concept in pack.concepts}


__all__ = ["PACK_ROOT", "TECHNOLOGY_CORE_PATH", "NONTECHNICAL_PACK_PATHS", "NONTECHNICAL_PACK_STATUS", "PackStatus", "alias_map", "load_active_nontechnical_packs", "load_pack", "load_technology_core", "load_nontechnical_packs", "normalize_pack_alias"]
