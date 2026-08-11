"""Auditable contracts for every professional analysis surface.

The registry prevents charts from becoming decoration: each surface must state
the decision it supports, its numerical basis, gap behavior, provenance, and
the non-authorizing follow-up available to the driver.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AnalysisSurfaceContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    surface_id: str = Field(min_length=1)
    professional_term: str = Field(min_length=1)
    decision_question: str = Field(min_length=1)
    consumer: str = Field(min_length=1)
    numerical_basis: str = Field(min_length=1)
    units: tuple[str, ...] = Field(min_length=1)
    provenance: tuple[str, ...] = Field(min_length=1)
    confidence_rule: str = Field(min_length=1)
    gap_behavior: str = Field(min_length=1)
    driver_follow_up: str = Field(min_length=1)
    proxy_policy: str = Field(min_length=1)


ANALYSIS_SURFACE_CONTRACTS: tuple[AnalysisSurfaceContract, ...] = (
    AnalysisSurfaceContract(
        surface_id="matched_position_time_delta",
        professional_term="time variance and synchronized comparison",
        decision_question="Where is repeatable time gained or lost at the same physical track position?",
        consumer="Laps engineering comparison",
        numerical_basis="Cumulative elapsed-time interpolation on a common lap-position grid across eligible paired laps.",
        units=("s", "% lap"),
        provenance=("run IDs", "eligible lap IDs", "common-position coverage", "alignment method"),
        confidence_rule="Report empirical noise, paired-lap count, and alignment coverage; incomplete coverage cannot become a whole-window total.",
        gap_behavior="Uncovered positions remain gaps and break integrated totals.",
        driver_follow_up="Open the phase evidence and request a current P19 review.",
        proxy_policy="Timing is measured; cause attribution remains evidence-gated.",
    ),
    AnalysisSurfaceContract(
        surface_id="platform_channel_overlay",
        professional_term="overlays and math channels",
        decision_question="Which measured or calculated platform signal changes at the selected position?",
        consumer="Platform workbench",
        numerical_basis="Position-synchronized raw channels and declared calculated-channel formulas.",
        units=("channel native unit", "% lap", "ft"),
        provenance=("channel registry", "formula", "dependencies", "run/lap selection"),
        confidence_rule="Calculated channels disclose proxy status and missing dependencies.",
        gap_behavior="Missing samples render as breaks, never zero.",
        driver_follow_up="Inspect the linked evidence event and its related setup context.",
        proxy_policy="Aero/load/scrub channels remain relative proxies, never measured forces.",
    ),
    AnalysisSurfaceContract(
        surface_id="track_position_map",
        professional_term="map and synchronized cursor statistics",
        decision_question="Where on track does the event or phase occur?",
        consumer="Track-map overlay and evidence inspector",
        numerical_basis="Imported map centerline plus telemetry lap position; cursor values share the selected physical position.",
        units=("% lap", "m", "ft"),
        provenance=("map ID/version", "run ID", "lap ID", "position mapping confidence"),
        confidence_rule="Unknown or mismatched map identity blocks geometric cause attribution.",
        gap_behavior="Unmapped sections stay unknown and are not extrapolated.",
        driver_follow_up="Select the event/zone and open its telemetry evidence.",
        proxy_policy="Centerline location does not imply measured banking, width, or elevation.",
    ),
    AnalysisSurfaceContract(
        surface_id="damper_velocity_histogram",
        professional_term="histogram",
        decision_question="Which measured shaft-velocity regimes are occupied and repeated?",
        consumer="Damper response analysis",
        numerical_basis="Measured shock shaft-velocity samples grouped into declared bins on eligible windows.",
        units=("in/s", "% samples"),
        provenance=("corner channel", "sample rate", "window", "bin edges"),
        confidence_rule="Regime classification requires adequate coverage and repetition at that corner.",
        gap_behavior="Missing shaft data suppresses the histogram and regime classification.",
        driver_follow_up="Inspect the repeated regime evidence or collect the missing shaft data; setup authority remains with P19.",
        proxy_policy="Shaft velocity is measured; damper force is not inferred without a force curve.",
    ),
    AnalysisSurfaceContract(
        surface_id="damper_psd",
        professional_term="power spectral density (PSD)",
        decision_question="Is a repeated suspension oscillation present at a supported frequency?",
        consumer="Damper response analysis",
        numerical_basis="Windowed shaft-velocity spectrum with declared effective sample rate and window duration.",
        units=("Hz", "spectral amplitude proxy"),
        provenance=("corner channel", "effective sample rate", "window duration", "eligible attempt IDs"),
        confidence_rule="Short, irregular, clipped, or non-repeated windows suppress frequency conclusions.",
        gap_behavior="Gaps split windows; spectra are never bridged across missing samples.",
        driver_follow_up="Repeat the same zone and confirm the frequency; any setting decision remains with P19.",
        proxy_policy="Spectral amplitude is descriptive and is not measured damping force.",
    ),
    AnalysisSurfaceContract(
        surface_id="engineering_metrics",
        professional_term="metrics and confidence intervals",
        decision_question="Is the observed effect larger than noise and safe enough to act on?",
        consumer="Race/Learning decision cards",
        numerical_basis="Server-derived eligible cohorts, matched context, empirical noise, and controlled-effect scoring.",
        units=("s", "mph", "%", "confidence 0-1"),
        provenance=("source runs", "source laps", "event IDs", "source channels"),
        confidence_rule="Every action exposes blockers, uncertainty, and contradictory evidence.",
        gap_behavior="Unavailable components cap or block the decision instead of receiving neutral values.",
        driver_follow_up="Follow the exact P19-controlled outcome or measurement mission.",
        proxy_policy="Metrics retain measured/calculated/proxy identity through the API and UI.",
    ),
    AnalysisSurfaceContract(
        surface_id="reproducible_report",
        professional_term="report",
        decision_question="Can another engineer reproduce why this decision was made?",
        consumer="Markdown report and evidence export",
        numerical_basis="The same server selection, contracts, metrics, and evidence IDs shown in the active decision.",
        units=("source-native units",),
        provenance=("run/lap/setup IDs", "analysis version", "evidence packet IDs", "channel provenance"),
        confidence_rule="Reports include blockers, caveats, contradictions, and version identity.",
        gap_behavior="Missing evidence is printed as unavailable, never omitted or converted to zero.",
        driver_follow_up="Archive the result or reproduce the P19-bound controlled test.",
        proxy_policy="Reports use the same proxy labels and prohibited-claim rules as runtime.",
    ),
)


def analysis_surface_contracts() -> tuple[AnalysisSurfaceContract, ...]:
    return ANALYSIS_SURFACE_CONTRACTS


__all__ = ["ANALYSIS_SURFACE_CONTRACTS", "AnalysisSurfaceContract", "analysis_surface_contracts"]
