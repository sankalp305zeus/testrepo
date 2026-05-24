"""Restaurant domain model (normalized catalog record)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Restaurant:
    """Canonical restaurant record after ingestion."""

    id: str
    name: str
    location: str  # City (e.g. Bangalore) for preference matching
    cuisines: List[str]
    rating: float
    cost_for_two: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def cuisine_display(self) -> str:
        return ", ".join(self.cuisines)
