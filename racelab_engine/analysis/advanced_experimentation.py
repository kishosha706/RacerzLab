"""Safety-gated design-of-experiments helpers.

These tools stay unavailable until deterministic evidence contracts and the
controlled response memory have enough validated history.  They never operate
directly on telemetry samples; one row here represents one controlled test.
"""

from __future__ import annotations

import math
from itertools import product
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExperimentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExperimentHistorySummary(ExperimentModel):
    phase_exit_passed: dict[str, bool]
    controlled_experiments: int = Field(ge=0)
    distinct_contexts: int = Field(ge=0)
    experiments_per_factor: dict[str, int]
    held_out_validation_score: float | None = Field(default=None, ge=0.0, le=1.0)
    contradiction_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    traceable_fraction: float = Field(ge=0.0, le=1.0)


class ExperimentUnlock(ExperimentModel):
    unlocked: bool
    blockers: tuple[str, ...]
    minimums: dict[str, float | int]
    qualified_factor_keys: tuple[str, ...] = ()


class Factor(ExperimentModel):
    key: str = Field(min_length=1)
    low: float
    high: float

    @model_validator(mode="after")
    def validate_bounds(self) -> Factor:
        if not math.isfinite(self.low) or not math.isfinite(self.high) or self.low >= self.high:
            raise ValueError("factor bounds must be finite with low < high")
        return self


class DesignRun(ExperimentModel):
    run_number: int
    coded_levels: dict[str, Literal[-1, 1]]
    values: dict[str, float]


class ObjectivePoint(ExperimentModel):
    experiment_id: str = Field(min_length=1)
    objectives: dict[str, float]
    uncertainty: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_objectives(self) -> ObjectivePoint:
        if (
            not self.objectives
            or any(not key.strip() or not math.isfinite(value) for key, value in self.objectives.items())
            or not math.isfinite(self.uncertainty)
        ):
            raise ValueError("objectives and uncertainty must be non-empty and finite")
        return self


class ObjectiveProfile(ExperimentModel):
    name: str = Field(min_length=1)
    weights: dict[str, float]
    uncertainty_weight: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def validate_weights(self) -> ObjectiveProfile:
        if (
            not self.weights
            or any(not key.strip() or not math.isfinite(value) or value < 0.0 for key, value in self.weights.items())
            or not any(value > 0.0 for value in self.weights.values())
            or not math.isfinite(self.uncertainty_weight)
        ):
            raise ValueError("profile weights must be finite, non-negative, and include a positive weight")
        return self


class SearchObservation(ExperimentModel):
    experiment_id: str = Field(min_length=1)
    context_key: str = Field(min_length=1)
    values: dict[str, float]
    objective: float
    measurement_uncertainty: float = Field(ge=0.0)
    setup_passed_tech: bool
    evidence_packet_ids: tuple[str, ...] = Field(min_length=1)
    source_run_ids: tuple[str, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_search_observation(self) -> SearchObservation:
        if (
            not self.values
            or any(not key.strip() or not math.isfinite(value) for key, value in self.values.items())
            or not math.isfinite(self.objective)
            or not math.isfinite(self.measurement_uncertainty)
            or any(not value.strip() for value in self.evidence_packet_ids)
            or len(set(self.source_run_ids)) != len(self.source_run_ids)
            or any(not value.strip() for value in self.source_run_ids)
        ):
            raise ValueError("search observations require finite values and traceable evidence")
        return self


class SearchCandidate(ExperimentModel):
    values: dict[str, float]
    changed_factor: str
    predicted_objective: float
    predictive_uncertainty: float = Field(ge=0.0)
    predicted_interval_95: tuple[float, float]
    nearest_support_distance: float = Field(ge=0.0)
    expected_improvement: float = Field(ge=0.0)
    acquisition_score: float


class ParameterSearchResult(ExperimentModel):
    status: Literal["ready", "blocked"]
    context_key: str | None
    selected: SearchCandidate | None
    ranked_candidates: tuple[SearchCandidate, ...]
    blockers: tuple[str, ...]
    source_experiment_ids: tuple[str, ...]
    evidence_packet_ids: tuple[str, ...]
    source_run_ids: tuple[str, ...]
    scope: str


_REQUIRED_PHASES = tuple(f"P{index}" for index in range(7))


def evaluate_experiment_unlock(history: ExperimentHistorySummary) -> ExperimentUnlock:
    minimums: dict[str, float | int] = {
        "controlled_experiments": 30,
        "distinct_contexts": 3,
        "experiments_per_factor": 6,
        "held_out_validation_score": 0.65,
        "maximum_contradiction_rate": 0.25,
        "traceable_fraction": 1.0,
    }
    blockers: list[str] = []
    missing_phases = [phase for phase in _REQUIRED_PHASES if history.phase_exit_passed.get(phase) is not True]
    if missing_phases:
        blockers.append("Roadmap phase exits not verified: " + ", ".join(missing_phases) + ".")
    if history.controlled_experiments < 30:
        blockers.append("At least 30 eligible controlled experiments are required.")
    if history.distinct_contexts < 3:
        blockers.append("At least three independently validated contexts are required.")
    sparse = sorted(key for key, count in history.experiments_per_factor.items() if count < 6)
    if not history.experiments_per_factor or sparse:
        blockers.append("Every proposed factor needs at least six controlled observations.")
    if history.held_out_validation_score is None or history.held_out_validation_score < 0.65:
        blockers.append("Held-out predictive validation must reach 0.65.")
    if history.contradiction_rate is None or history.contradiction_rate > 0.25:
        blockers.append("Contradiction rate is unavailable or above 25%.")
    if history.traceable_fraction < 1.0:
        blockers.append("Every training experiment must be traceable to its source evidence packet.")
    qualified = tuple(sorted(
        key for key, count in history.experiments_per_factor.items() if count >= 6
    ))
    return ExperimentUnlock(
        unlocked=not blockers,
        blockers=tuple(blockers),
        minimums=minimums,
        qualified_factor_keys=qualified,
    )


def fractional_factorial_design(
    factors: list[Factor],
    unlock: ExperimentUnlock,
) -> tuple[DesignRun, ...]:
    if not unlock.unlocked:
        raise ValueError("advanced experimentation is locked: " + " ".join(unlock.blockers))
    if not 2 <= len(factors) <= 6:
        raise ValueError("fractional design requires two to six setup factors")
    if len({factor.key for factor in factors}) != len(factors):
        raise ValueError("factor keys must be unique")
    unqualified = sorted(
        factor.key for factor in factors if factor.key not in unlock.qualified_factor_keys
    )
    if unqualified:
        raise ValueError(
            "factors lack the required controlled history: " + ", ".join(unqualified)
        )
    for factor in factors:
        if factor.low >= factor.high:
            raise ValueError(f"factor {factor.key} must have low < high")

    base_count = len(factors) if len(factors) <= 4 else len(factors) - 1
    coded_rows: list[tuple[int, ...]] = []
    for base in product((-1, 1), repeat=base_count):
        if len(factors) <= 4:
            coded = base
        else:
            generator = 1
            for level in base:
                generator *= level
            coded = (*base, generator)
        coded_rows.append(coded)
    return tuple(
        DesignRun(
            run_number=index + 1,
            coded_levels={factor.key: coded[column] for column, factor in enumerate(factors)},
            values={
                factor.key: factor.low if coded[column] < 0 else factor.high
                for column, factor in enumerate(factors)
            },
        )
        for index, coded in enumerate(coded_rows)
    )


def response_surface_terms(values: dict[str, float]) -> dict[str, float]:
    """Build deterministic linear, quadratic, and pair-interaction features."""
    if not values or any(not key.strip() or not math.isfinite(value) for key, value in values.items()):
        raise ValueError("response-surface inputs must be non-empty and finite")
    keys = sorted(values)
    terms: dict[str, float] = {"intercept": 1.0}
    for key in keys:
        terms[key] = float(values[key])
        terms[f"{key}^2"] = float(values[key]) ** 2
    for index, left in enumerate(keys):
        for right in keys[index + 1:]:
            terms[f"{left}*{right}"] = float(values[left]) * float(values[right])
    return terms


def select_next_design_run(
    design: tuple[DesignRun, ...],
    completed_run_numbers: set[int],
) -> DesignRun | None:
    """Choose the untested row farthest from completed coded settings."""
    candidates = [run for run in design if run.run_number not in completed_run_numbers]
    if not candidates:
        return None
    completed = [run for run in design if run.run_number in completed_run_numbers]
    if not completed:
        return candidates[0]

    def distance(candidate: DesignRun) -> int:
        return min(
            sum(
                candidate.coded_levels[key] != reference.coded_levels[key]
                for key in candidate.coded_levels
            )
            for reference in completed
        )

    return max(candidates, key=lambda run: (distance(run), -run.run_number))


def pareto_frontier(
    points: list[ObjectivePoint],
    *,
    minimize: set[str],
) -> tuple[ObjectivePoint, ...]:
    """Return non-dominated points; uncertainty is never silently discarded."""
    if not points:
        return ()
    keys = set(points[0].objectives)
    if any(set(point.objectives) != keys for point in points):
        raise ValueError("all Pareto points must declare the same objectives")
    if minimize != keys:
        raise ValueError("objective direction must be explicit for every objective")

    frontier: list[ObjectivePoint] = []
    for candidate in points:
        dominated = False
        for other in points:
            if other is candidate:
                continue
            no_worse = all(other.objectives[key] <= candidate.objectives[key] for key in keys)
            strictly_better = any(other.objectives[key] < candidate.objectives[key] for key in keys)
            uncertainty_better = other.uncertainty < candidate.uncertainty
            if no_worse and (strictly_better or uncertainty_better) and other.uncertainty <= candidate.uncertainty:
                dominated = True
                break
        if not dominated:
            frontier.append(candidate)
    return tuple(frontier)


def select_objectives(
    points: list[ObjectivePoint],
    profiles: list[ObjectiveProfile],
) -> dict[str, ObjectivePoint]:
    """Select one uncertainty-penalized compromise per explicit race objective."""
    if not points or not profiles:
        return {}
    objective_keys = set(points[0].objectives)
    if any(set(point.objectives) != objective_keys for point in points):
        raise ValueError("all objective points must declare the same objectives")
    if len({profile.name for profile in profiles}) != len(profiles):
        raise ValueError("objective profile names must be unique")
    ranges = {
        key: (
            min(point.objectives[key] for point in points),
            max(point.objectives[key] for point in points),
        )
        for key in objective_keys
    }
    result: dict[str, ObjectivePoint] = {}
    for profile in profiles:
        if set(profile.weights) != objective_keys:
            raise ValueError(f"profile {profile.name} must weight every objective")
        if not any(weight > 0 for weight in profile.weights.values()):
            raise ValueError(f"profile {profile.name} must include a positive objective weight")
        def score(point: ObjectivePoint) -> float:
            normalized = {
                key: (
                    (point.objectives[key] - ranges[key][0]) / (ranges[key][1] - ranges[key][0])
                    if ranges[key][1] > ranges[key][0]
                    else 0.0
                )
                for key in objective_keys
            }
            weight_total = sum(profile.weights.values())
            return (
                sum(profile.weights[key] * normalized[key] for key in objective_keys) / weight_total
                + profile.uncertainty_weight * point.uncertainty
            )

        result[profile.name] = min(points, key=lambda point: (score(point), point.experiment_id))
    return result


def _cholesky(matrix: list[list[float]]) -> list[list[float]] | None:
    size = len(matrix)
    lower = [[0.0] * size for _ in range(size)]
    for row in range(size):
        for column in range(row + 1):
            value = matrix[row][column] - sum(
                lower[row][index] * lower[column][index]
                for index in range(column)
            )
            if row == column:
                if value <= 1e-12 or not math.isfinite(value):
                    return None
                lower[row][column] = math.sqrt(value)
            else:
                lower[row][column] = value / lower[column][column]
    return lower


def _solve_cholesky(lower: list[list[float]], values: list[float]) -> list[float]:
    size = len(values)
    forward = [0.0] * size
    for row in range(size):
        forward[row] = (
            values[row]
            - sum(lower[row][column] * forward[column] for column in range(row))
        ) / lower[row][row]
    result = [0.0] * size
    for row in range(size - 1, -1, -1):
        result[row] = (
            forward[row]
            - sum(lower[column][row] * result[column] for column in range(row + 1, size))
        ) / lower[row][row]
    return result


def _squared_distance(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right))


def contextual_bayesian_parameter_search(
    *,
    context_key: str,
    observations: list[SearchObservation],
    candidates: list[dict[str, float]],
    current_values: dict[str, float],
    observed_tech_envelope: dict[str, tuple[float, float]],
    unlock: ExperimentUnlock,
    minimize: bool = True,
    length_scale: float = 0.45,
    uncertainty_penalty: float = 0.35,
    legal_values: dict[str, tuple[float, ...]] | None = None,
) -> ParameterSearchResult:
    """Rank candidates with an exact-context Gaussian-process surrogate.

    This is deliberately bounded to the observed tech-passing envelope.  It is
    an uncertainty-aware next-test selector, not an optimizer that may publish
    an untested setup as best.
    """
    blockers: list[str] = []
    if not unlock.unlocked:
        blockers.append("Advanced experimentation unlock is not satisfied.")
    if not context_key.strip():
        blockers.append("An exact response-context key is required.")
    if len(observations) < 8:
        blockers.append("At least eight qualified exact-context observations are required.")
    if not candidates:
        blockers.append("At least one bounded candidate is required.")
    length_scale_squared = length_scale * length_scale
    if (
        not math.isfinite(length_scale)
        or length_scale <= 0.0
        or not math.isfinite(length_scale_squared)
        or length_scale_squared == 0.0
    ):
        blockers.append("A positive finite search length scale is required.")
    if not math.isfinite(uncertainty_penalty) or uncertainty_penalty < 0.0:
        blockers.append("A non-negative finite uncertainty penalty is required.")
    factor_keys = sorted(observed_tech_envelope)
    if not factor_keys:
        blockers.append("An observed tech-passing envelope is required.")
    if any(key not in unlock.qualified_factor_keys for key in factor_keys):
        blockers.append("Every searched factor must have qualified controlled history.")
    for key, bounds in observed_tech_envelope.items():
        if len(bounds) != 2 or not all(math.isfinite(float(value)) for value in bounds) or bounds[0] >= bounds[1]:
            blockers.append(f"Observed envelope for {key} is invalid.")
    if legal_values is None:
        blockers.append("Observed legal-option tables are required for every searched factor.")
    else:
        unknown_legal = set(legal_values) - set(factor_keys)
        if unknown_legal:
            blockers.append("Legal-option tables contain factors outside the search envelope.")
        missing_legal = set(factor_keys) - set(legal_values)
        if missing_legal:
            blockers.append("Every searched factor requires an observed legal-option table.")
        for key, values in legal_values.items():
            if not values or any(not math.isfinite(value) for value in values):
                blockers.append(f"Legal options for {key} must be finite and non-empty.")
    for observation in observations:
        if observation.context_key != context_key:
            blockers.append("Observations from different contexts cannot be pooled.")
            break
        if not observation.setup_passed_tech:
            blockers.append("Every search observation must be tech-passing.")
            break
        if set(observation.values) != set(factor_keys):
            blockers.append("Every observation must contain the same qualified factors.")
            break
        if not math.isfinite(observation.objective):
            blockers.append("Observation objectives must be finite.")
            break
    experiment_ids = [item.experiment_id for item in observations]
    if len(set(experiment_ids)) != len(experiment_ids):
        blockers.append("Search observations require unique controlled experiment IDs.")
    provenance_groups = [tuple(item.source_run_ids) for item in observations]
    if len(set(provenance_groups)) != len(provenance_groups):
        blockers.append("Search observations require independent A/B/A2 source-run provenance groups.")
    seen_source_runs: set[str] = set()
    for item in observations:
        if seen_source_runs.intersection(item.source_run_ids):
            blockers.append("Search experiments must use disjoint source runs unless clustered covariance is modeled.")
            break
        seen_source_runs.update(item.source_run_ids)
    if set(current_values) != set(factor_keys):
        blockers.append("Current setup values must contain the searched factors.")
    if blockers:
        return ParameterSearchResult(
            status="blocked",
            context_key=context_key or None,
            selected=None,
            ranked_candidates=(),
            blockers=tuple(dict.fromkeys(blockers)),
            source_experiment_ids=tuple(item.experiment_id for item in observations),
            evidence_packet_ids=tuple(dict.fromkeys(
                packet for item in observations for packet in item.evidence_packet_ids
            )),
            source_run_ids=tuple(dict.fromkeys(run for item in observations for run in item.source_run_ids)),
            scope="blocked_no_search_performed",
        )

    def normalize(values: dict[str, float]) -> tuple[float, ...] | None:
        if set(values) != set(factor_keys):
            return None
        normalized: list[float] = []
        for key in factor_keys:
            value = float(values[key])
            low, high = observed_tech_envelope[key]
            if not math.isfinite(value) or value < low or value > high:
                return None
            if legal_values is not None and key in legal_values and not any(
                math.isclose(value, option, rel_tol=0.0, abs_tol=1e-12)
                for option in legal_values[key]
            ):
                return None
            normalized.append((value - low) / (high - low))
        return tuple(normalized)

    train_x = [normalize(item.values) for item in observations]
    if any(value is None for value in train_x):
        blockers.append("An observation lies outside the observed tech-passing envelope.")
    if normalize(current_values) is None:
        blockers.append("Current setup values must stay inside the observed tech-passing envelope.")
    normalized_candidates = [(values, normalize(values)) for values in candidates]
    if any(value is None for _, value in normalized_candidates):
        blockers.append("Every candidate must stay inside the observed tech-passing envelope.")
    changed_factors: list[str] = []
    for values, _ in normalized_candidates:
        changed = [
            key for key in factor_keys
            if not math.isclose(float(values[key]), float(current_values[key]), rel_tol=0.0, abs_tol=1e-12)
        ]
        if len(changed) != 1:
            blockers.append("Each candidate must change exactly one setup control from the current setup.")
            break
        changed_factors.append(changed[0])
    if blockers:
        return ParameterSearchResult(
            status="blocked", context_key=context_key, selected=None, ranked_candidates=(),
            blockers=tuple(dict.fromkeys(blockers)),
            source_experiment_ids=tuple(item.experiment_id for item in observations),
            evidence_packet_ids=tuple(dict.fromkeys(
                packet for item in observations for packet in item.evidence_packet_ids
            )),
            source_run_ids=tuple(dict.fromkeys(run for item in observations for run in item.source_run_ids)),
            scope="blocked_no_search_performed",
        )
    training = [value for value in train_x if value is not None]
    outputs = [item.objective if minimize else -item.objective for item in observations]
    output_mean = sum(outputs) / len(outputs)
    output_scale = max(
        math.sqrt(sum((value - output_mean) ** 2 for value in outputs) / len(outputs)),
        sum(item.measurement_uncertainty for item in observations) / len(observations),
        1e-6,
    )
    centered = [(value - output_mean) / output_scale for value in outputs]
    covariance: list[list[float]] = []
    for row, left in enumerate(training):
        covariance_row = []
        for column, right in enumerate(training):
            kernel = math.exp(-0.5 * _squared_distance(left, right) / length_scale_squared)
            if row == column:
                normalized_noise = observations[row].measurement_uncertainty / output_scale
                kernel += normalized_noise ** 2 + 1e-6
            covariance_row.append(kernel)
        covariance.append(covariance_row)
    lower = _cholesky(covariance)
    if lower is None:
        return ParameterSearchResult(
            status="blocked", context_key=context_key, selected=None, ranked_candidates=(),
            blockers=("The uncertainty model is numerically singular; collect a more varied controlled design.",),
            source_experiment_ids=tuple(item.experiment_id for item in observations),
            evidence_packet_ids=tuple(dict.fromkeys(
                packet for item in observations for packet in item.evidence_packet_ids
            )),
            source_run_ids=tuple(dict.fromkeys(run for item in observations for run in item.source_run_ids)),
            scope="blocked_no_search_performed",
        )
    alpha = _solve_cholesky(lower, centered)
    best = min((value - output_mean) / output_scale for value in outputs)
    ranked: list[SearchCandidate] = []
    for candidate_index, (raw_values, point) in enumerate(normalized_candidates):
        assert point is not None
        kernel = [
            math.exp(-0.5 * _squared_distance(point, reference) / length_scale_squared)
            for reference in training
        ]
        mean_standardized = sum(left * right for left, right in zip(kernel, alpha))
        projection = _solve_cholesky(lower, kernel)
        variance = max(1e-9, 1.0 - sum(left * right for left, right in zip(kernel, projection)))
        sigma_standardized = math.sqrt(variance)
        improvement_standardized = best - mean_standardized
        z_score = improvement_standardized / sigma_standardized
        phi = math.exp(-0.5 * z_score * z_score) / math.sqrt(2.0 * math.pi)
        cdf = 0.5 * (1.0 + math.erf(z_score / math.sqrt(2.0)))
        expected_improvement = max(
            0.0,
            (improvement_standardized * cdf + sigma_standardized * phi) * output_scale,
        )
        sigma = sigma_standardized * output_scale
        acquisition = expected_improvement - uncertainty_penalty * sigma
        mean_internal = output_mean + mean_standardized * output_scale
        predicted = mean_internal if minimize else -mean_internal
        interval = (predicted - 1.96 * sigma, predicted + 1.96 * sigma)
        support_distance = min(math.sqrt(_squared_distance(point, reference)) for reference in training)
        ranked.append(SearchCandidate(
            values={key: float(raw_values[key]) for key in factor_keys},
            changed_factor=changed_factors[candidate_index],
            predicted_objective=predicted,
            predictive_uncertainty=sigma,
            predicted_interval_95=interval,
            nearest_support_distance=support_distance,
            expected_improvement=expected_improvement,
            acquisition_score=acquisition,
        ))
    ranked.sort(key=lambda item: (-item.acquisition_score, item.predictive_uncertainty, tuple(item.values.items())))
    return ParameterSearchResult(
        status="ready",
        context_key=context_key,
        selected=ranked[0] if ranked else None,
        ranked_candidates=tuple(ranked),
        blockers=(),
        source_experiment_ids=tuple(item.experiment_id for item in observations),
        evidence_packet_ids=tuple(dict.fromkeys(
            packet for item in observations for packet in item.evidence_packet_ids
        )),
        source_run_ids=tuple(dict.fromkeys(run for item in observations for run in item.source_run_ids)),
        scope="next_controlled_test_only_within_observed_tech_envelope",
    )


__all__ = [
    "DesignRun",
    "ExperimentHistorySummary",
    "ExperimentUnlock",
    "Factor",
    "ObjectivePoint",
    "ObjectiveProfile",
    "ParameterSearchResult",
    "SearchCandidate",
    "SearchObservation",
    "contextual_bayesian_parameter_search",
    "evaluate_experiment_unlock",
    "fractional_factorial_design",
    "pareto_frontier",
    "response_surface_terms",
    "select_objectives",
    "select_next_design_run",
]
