"""Canonical physical tire-surface semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


TireCorner = Literal["lf", "rf", "lr", "rr"]
Axle = Literal["front", "rear"]
VehicleSide = Literal["left", "right"]


@dataclass(frozen=True)
class TireCornerSemantics:
    """Physical meaning of iRacing L/R tire samples for one corner."""

    corner: TireCorner
    axle: Axle
    vehicle_side: VehicleSide
    inner_raw_side: Literal["left", "right"]
    outer_raw_side: Literal["left", "right"]


TIRE_CORNERS: dict[TireCorner, TireCornerSemantics] = {
    "lf": TireCornerSemantics("lf", "front", "left", "right", "left"),
    "rf": TireCornerSemantics("rf", "front", "right", "left", "right"),
    "lr": TireCornerSemantics("lr", "rear", "left", "right", "left"),
    "rr": TireCornerSemantics("rr", "rear", "right", "left", "right"),
}


def semantic_source(corner: TireCorner, position: Literal["inner", "outer"]) -> str:
    semantics = TIRE_CORNERS[corner]
    return semantics.inner_raw_side if position == "inner" else semantics.outer_raw_side


__all__ = ["Axle", "TIRE_CORNERS", "TireCorner", "TireCornerSemantics", "semantic_source"]
