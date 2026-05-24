"""User preference input model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Optional

Budget = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class UserPreferences:
    """Preferences collected from UI or CLI."""

    location: str
    budget: Budget
    cuisine: str
    min_rating: float = 0.0
    extras: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.location or not str(self.location).strip():
            raise ValueError("location is required")
        if self.budget not in ("low", "medium", "high"):
            raise ValueError("budget must be low, medium, or high")
        if not self.cuisine or not str(self.cuisine).strip():
            raise ValueError("cuisine is required")
        if self.min_rating < 0 or self.min_rating > 5:
            raise ValueError("min_rating must be between 0 and 5")

    @property
    def location_normalized(self) -> str:
        return self.location.strip()

    @property
    def cuisine_normalized(self) -> str:
        return self.cuisine.strip()

    @property
    def extras_normalized(self) -> List[str]:
        return [e.strip() for e in self.extras if e and str(e).strip()]
