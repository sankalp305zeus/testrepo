"""Load, normalize, and cache the Zomato restaurant catalog."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from src.models.restaurant import Restaurant

logger = logging.getLogger(__name__)

DATASET_NAME = "ManikaSaini/zomato-restaurant-recommendation"
CACHE_VERSION = 1
DEFAULT_CACHE_PATH = Path("data/restaurants.parquet")

REQUIRED_COLUMNS = {
    "name",
    "address",
    "cuisines",
    "rate",
    "approx_cost(for two people)",
}

CITY_ALIASES = {
    "bangalore": "Bangalore",
    "bengaluru": "Bangalore",
    "banglore": "Bangalore",
}

KNOWN_CITIES = [
    "Bangalore",
    "Mumbai",
    "Delhi",
    "Pune",
    "Hyderabad",
    "Chennai",
    "Kolkata",
    "Ahmedabad",
    "Jaipur",
    "Goa",
]


def _cache_path() -> Path:
    return Path(os.getenv("CATALOG_CACHE_PATH", str(DEFAULT_CACHE_PATH)))


def _configure_hf_cache() -> None:
    hf_home = Path(os.getenv("HF_HOME", "data/hf_cache"))
    os.environ.setdefault("HF_HOME", str(hf_home))
    os.environ.setdefault("HF_DATASETS_CACHE", str(hf_home))
    hf_home.mkdir(parents=True, exist_ok=True)


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return text == "" or text.casefold() in {"nan", "none", "null", "-", "n/a"}


def _parse_rating(value: Any) -> float | None:
    if _is_blank(value):
        return None

    text = str(value).strip()
    if text.casefold() in {"new", "nan"}:
        return None

    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        return None

    rating = float(match.group(0))
    if rating < 0 or rating > 5:
        return None
    return rating


def _parse_cost(value: Any) -> float | None:
    if _is_blank(value):
        return None

    text = str(value).replace(",", "").replace("₹", "")
    values = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]
    if not values:
        return None

    cost = sum(values[:2]) / min(len(values), 2)
    if cost <= 0:
        return None
    return cost


def _parse_cuisines(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        parts = value
    else:
        parts = str(value).split(",")
    return [str(part).strip() for part in parts if str(part).strip()]


def _extract_city(address: Any, area: Any, listed_in_city: Any) -> str:
    for candidate in (address, area, listed_in_city):
        if _is_blank(candidate):
            continue
        text = str(candidate).casefold()
        for alias, canonical in CITY_ALIASES.items():
            if alias in text:
                return canonical
        for city in KNOWN_CITIES:
            if city.casefold() in text:
                return city

    if not _is_blank(listed_in_city):
        return str(listed_in_city).strip()
    return "Unknown"


def _validate_schema(columns: Sequence[str]) -> None:
    missing = sorted(REQUIRED_COLUMNS - set(columns))
    if missing:
        raise ValueError(f"Dataset missing required columns: {', '.join(missing)}")


def _row_to_restaurant(row: Mapping[str, Any], index: int) -> Restaurant | None:
    name = str(row.get("name", "")).strip()
    if not name:
        return None

    rating = _parse_rating(row.get("rate"))
    cost = _parse_cost(row.get("approx_cost(for two people)"))
    cuisines = _parse_cuisines(row.get("cuisines"))
    city = _extract_city(row.get("address"), row.get("location"), row.get("listed_in(city)"))

    if rating is None or cost is None or not cuisines or city == "Unknown":
        return None

    url = row.get("url")
    raw_id = str(url).strip() if not _is_blank(url) else f"{name}:{index}"
    restaurant_id = hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:12]

    metadata = {
        "address": row.get("address"),
        "area": row.get("location"),
        "listed_in_city": row.get("listed_in(city)"),
        "url": url,
        "rest_type": row.get("rest_type"),
        "votes": row.get("votes"),
    }
    metadata = {k: v for k, v in metadata.items() if not _is_blank(v)}

    return Restaurant(
        id=restaurant_id,
        name=name,
        location=city,
        cuisines=cuisines,
        rating=rating,
        cost_for_two=cost,
        metadata=metadata,
    )


def _normalize_dataset(split: Iterable[Mapping[str, Any]]) -> list[Restaurant]:
    column_names = getattr(split, "column_names", None)
    if column_names is not None:
        _validate_schema(column_names)

    restaurants = [
        restaurant
        for index, row in enumerate(split)
        if (restaurant := _row_to_restaurant(row, index)) is not None
    ]

    if not restaurants:
        raise RuntimeError("No valid restaurants found after dataset normalization")
    return restaurants


def _restaurants_to_dataframe(restaurants: Sequence[Restaurant]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cache_version": CACHE_VERSION,
            "id": restaurant.id,
            "name": restaurant.name,
            "location": restaurant.location,
            "cuisines": json.dumps(restaurant.cuisines, ensure_ascii=False),
            "rating": restaurant.rating,
            "cost_for_two": restaurant.cost_for_two,
            "metadata": json.dumps(restaurant.metadata, ensure_ascii=False),
        }
        for restaurant in restaurants
    )


def _dataframe_to_restaurants(df: pd.DataFrame) -> list[Restaurant]:
    if "cache_version" in df.columns:
        versions = set(int(v) for v in df["cache_version"].dropna().unique())
        if versions != {CACHE_VERSION}:
            raise ValueError("Cache version mismatch")

    restaurants: list[Restaurant] = []
    for row in df.to_dict(orient="records"):
        cuisines = row.get("cuisines", [])
        if isinstance(cuisines, str):
            cuisines = json.loads(cuisines)

        metadata = row.get("metadata", {})
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        restaurants.append(
            Restaurant(
                id=str(row["id"]),
                name=str(row["name"]),
                location=str(row["location"]),
                cuisines=list(cuisines),
                rating=float(row["rating"]),
                cost_for_two=float(row["cost_for_two"]),
                metadata=dict(metadata),
            )
        )
    return restaurants


def _load_remote_dataset() -> list[Restaurant]:
    _configure_hf_cache()
    from datasets import load_dataset

    dataset = load_dataset(DATASET_NAME)
    split_name = "train" if "train" in dataset else next(iter(dataset.keys()))
    split = dataset[split_name]
    _validate_schema(split.column_names)
    return _normalize_dataset(split)


def load_catalog() -> list[Restaurant]:
    """Return the normalized restaurant catalog, using parquet cache when present."""
    cache_path = _cache_path()
    force_refresh = os.getenv("FORCE_REFRESH_CATALOG", "").lower() in {"1", "true", "yes"}

    if cache_path.exists() and not force_refresh:
        try:
            return _dataframe_to_restaurants(pd.read_parquet(cache_path))
        except Exception as exc:
            logger.warning("Ignoring stale catalog cache at %s: %s", cache_path, exc)

    restaurants = _load_remote_dataset()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    _restaurants_to_dataframe(restaurants).to_parquet(cache_path, index=False)
    logger.info("Cached %d restaurants at %s", len(restaurants), cache_path)
    return restaurants


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    restaurants = load_catalog()
    cities = sorted({restaurant.location for restaurant in restaurants})
    logger.info("Loaded %d restaurants across %d cities", len(restaurants), len(cities))


if __name__ == "__main__":
    main()
