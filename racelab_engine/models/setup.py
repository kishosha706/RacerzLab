from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class SetupSnapshot(BaseModel):
    setup_id: str
    run_id: str
    setup_name: Optional[str] = None
    setup_json: dict[str, Any] = Field(default_factory=dict)
    extracted_values: dict[str, Any] = Field(default_factory=dict)
    tape_percent: Optional[float] = None
    rear_end_ratio: Optional[float] = None
    lf_ride_height_mm: Optional[float] = None
    rf_ride_height_mm: Optional[float] = None
    lr_ride_height_mm: Optional[float] = None
    rr_ride_height_mm: Optional[float] = None
    lf_front_spring_n_per_mm: Optional[float] = None
    rf_front_spring_n_per_mm: Optional[float] = None
    lr_rear_spring_n_per_mm: Optional[float] = None
    rr_rear_spring_n_per_mm: Optional[float] = None
    nose_weight_percent: Optional[float] = None
    cross_weight_percent: Optional[float] = None
    front_brake_bias_percent: Optional[float] = None
    steering_ratio: Optional[str] = None
    steering_offset_deg: Optional[float] = None
