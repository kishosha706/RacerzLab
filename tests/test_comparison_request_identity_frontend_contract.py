from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("path", "fetch_marker", "state_setter"),
    (
        (
            "ui/src/components/TimeDeltaComparison.tsx",
            "const nextData = await fetchCompareTimeAnalysis(request);",
            "setRequestState",
        ),
        (
            "ui/src/components/EngineeringSystemsComparison.tsx",
            "const nextData = await fetchEngineeringSystems(request);",
            "setRequestState",
        ),
    ),
)
def test_lap_comparison_surfaces_bind_results_to_the_exact_request(
    path: str,
    fetch_marker: str,
    state_setter: str,
) -> None:
    source = _read(path)

    request_block = source.split("const request = useMemo", 1)[1].split("const requestKey", 1)[0]
    for field in (
        "baseline_run_id",
        "test_run_id",
        "baseline_lap",
        "test_lap",
        "step_pct",
    ):
        assert field in request_block

    assert "JSON.stringify(request)" in source
    assert "sequence: ++requestSequenceRef.current" in source
    assert "latestRequestRef.current = requestIdentity" in source
    assert "setRequestState({ requestKey, data: null, loading: true, error: null });" in source
    assert "const data = stateOwnsRequest ? requestState.data : null;" in source
    assert "const loading = requestKey != null && (!stateOwnsRequest || requestState.loading);" in source
    assert "const error = stateOwnsRequest ? requestState.error : null;" in source

    success_block = source.split(fetch_marker, 1)[1].split("} catch (caught)", 1)[0]
    assert success_block.index("if (!isLatestRequest()) return;") < success_block.index(state_setter)
    error_block = source.split("} catch (caught)", 1)[1].split("\n    }", 1)[0]
    assert error_block.index("if (!isLatestRequest()) return;") < error_block.index(state_setter)

    assert "setData(await" not in source
    assert "setLoading(false)" not in source


@pytest.mark.parametrize(
    ("path", "error_text"),
    (
        (
            "ui/src/components/TimeDeltaComparison.tsx",
            "Time comparison scope error: the response did not match the selected runs and laps.",
        ),
        (
            "ui/src/components/EngineeringSystemsComparison.tsx",
            "Engineering comparison scope error: the response did not match the selected runs and laps.",
        ),
    ),
)
def test_lap_comparison_responses_must_match_every_requested_identity(
    path: str,
    error_text: str,
) -> None:
    source = _read(path)

    for expression in (
        "nextData.baseline_run_id === request.baseline_run_id",
        "nextData.test_run_id === request.test_run_id",
        "nextData.baseline_lap === request.baseline_lap",
        "nextData.test_lap === request.test_lap",
    ):
        assert expression in source

    mismatch_block = source.split("if (!responseMatchesRequest)", 1)[1].split(
        "setRequestState({ requestKey, data: nextData",
        1,
    )[0]
    assert "data: null" in mismatch_block
    assert error_text in mismatch_block
    assert "return;" in mismatch_block


def test_stint_comparison_rejects_late_success_error_and_loading_commits() -> None:
    source = _read("ui/src/tabs/LapsTab.tsx")

    request_block = source.split("const stintCompareRequest = useMemo", 1)[1].split(
        "const stintCompareRequestKey",
        1,
    )[0]
    for field in (
        "baseline_run_id",
        "baseline_stint_id",
        "test_run_id",
        "test_stint_id",
    ):
        assert field in request_block

    assert "JSON.stringify(stintCompareRequest)" in source
    assert "sequence: ++stintCompareRequestSequenceRef.current" in source
    assert "latestStintCompareRequestRef.current = requestIdentity" in source
    assert "const stintCompare = stintCompareStateOwnsRequest ? stintCompareRequestState.data : null;" in source
    assert "(!stintCompareStateOwnsRequest || stintCompareRequestState.loading)" in source
    assert "stintCompareStateOwnsRequest ? stintCompareRequestState.error : null" in source

    success_block = source.split(".then((nextData) => {", 1)[1].split(".catch((err: unknown)", 1)[0]
    assert success_block.index("if (!isLatestRequest()) return;") < success_block.index(
        "setStintCompareRequestState",
    )
    error_block = source.split(".catch((err: unknown) => {", 1)[1].split("return () =>", 1)[0]
    assert error_block.index("if (!isLatestRequest()) return;") < error_block.index(
        "setStintCompareRequestState",
    )

    assert ".then(setStintCompare)" not in source
    assert ".finally(() => setStintCompareLoading(false))" not in source
    assert "setStintCompareError" not in source


def test_stint_comparison_response_must_match_selected_run_and_stint_scope() -> None:
    source = _read("ui/src/tabs/LapsTab.tsx")

    for expression in (
        "nextData.baseline_stint.run_id === stintCompareRequest.baseline_run_id",
        "nextData.baseline_stint.stint_id === stintCompareRequest.baseline_stint_id",
        "nextData.test_stint.run_id === stintCompareRequest.test_run_id",
        "nextData.test_stint.stint_id === stintCompareRequest.test_stint_id",
    ):
        assert expression in source

    mismatch_block = source.split("if (!responseMatchesRequest)", 1)[1].split(
        "setStintCompareRequestState({\n          requestKey: stintCompareRequestKey,\n          data: nextData",
        1,
    )[0]
    assert "data: null" in mismatch_block
    assert "Stint comparison scope error" in mismatch_block
    assert "return;" in mismatch_block
    assert 'role="alert"' in source
    assert "No comparison metrics are shown." in source
    assert "{stintCompare && (" in source


def test_lap_window_stint_and_history_loaders_reject_previous_run_results() -> None:
    source = _read("ui/src/tabs/LapsTab.tsx")

    assert "setWindowsData(null);" in source
    assert "const currentWindowsData = windowsDataRunId === overview.run_id ? windowsData : null;" in source
    assert "setWindowsDataRunId(requestedRunId);" in source
    assert "setStintData(null);" in source
    assert "const currentStintData = stintDataRunId === overview.run_id ? stintData : null;" in source
    assert "setStintDataRunId(requestedRunId);" in source
    assert "historyStintGenerationRef.current += 1;" in source
    assert "if (generation !== historyStintGenerationRef.current) return;" in source
    assert "stintResponseMatchesRun(response, requestedRunId)" in source
    assert "stintResponseMatchesRun(response, runId)" in source
    assert "lapWindowsResponseMatchesRun(response, requestedRunId)" in source
    assert "response.run_id === runId" in source
    assert "response.run_summary == null || response.run_summary.run_id === runId" in source
    assert "returnedStints.every((stint) => stint.run_id === runId)" in source
    assert "returnedLaps.every((lap) => lap.run_id === runId)" in source
    assert "returnedWindows.every((window) => window.run_id === runId)" in source


def test_platform_raw_zoom_response_must_match_selected_run_and_lap_scope() -> None:
    source = _read("ui/src/tabs/PlatformTab.tsx")

    request_start = source.index("const requestId = ++detailTraceRequestRef.current;")
    disable_guard = source.index("if (!rawZoomTraceEnabled || visibleZoomRange == null)")
    assert request_start < disable_guard
    assert "payload.run_id === overview.run_id" in source
    assert "(lap == null ? payload.lap == null : payload.lap === lap)" in source
    assert 'payload.trace_meta?.window_start_ft' in source
    assert 'payload.trace_meta?.window_end_ft' in source
    assert 'Math.abs(returnedWindowStart - rawRange.start) <= 0.01' in source
    assert 'Math.abs(returnedWindowEnd - rawRange.end) <= 0.01' in source
    assert "&& responseMatchesWindow" in source

    mismatch_block = source.split("if (!responseMatchesRequest)", 1)[1].split(
        "detailTraceCacheRef.current.set(cacheKey, payload)",
        1,
    )[0]
    assert "setDetailTrace(null);" in mismatch_block
    assert "Raw zoom scope error" in mismatch_block
    assert "run, lap, and distance window" in mismatch_block
    assert "Overview trace remains visible." in mismatch_block
    assert "return;" in mismatch_block


def test_lap_and_stint_transport_failures_are_unavailable_and_retryable() -> None:
    source = _read("ui/src/tabs/LapsTab.tsx")

    assert 'status: "error"' in source
    assert "Lap-window evidence is unavailable. No best-window conclusion is shown." in source
    assert "Retry lap windows" in source
    assert "Stint evidence is unavailable." in source
    assert "No stint-length or valid-lap conclusion is available from this failed request." in source
    assert "Retry stint evidence" in source
    assert 'currentStintsLoadStatus === "ready" && visibleStints.length === 0' in source
    assert "historyStintErrors" in source
    assert "Retry run" in source


def test_compare_insights_reject_late_or_cross_scope_recommendations() -> None:
    source = _read("ui/src/tabs/CompareTab.tsx")

    assert "const insightsRequestSequenceRef = useRef(0);" in source
    assert "insightsRequestSequenceRef.current += 1;" in source
    assert "const sequence = ++insightsRequestSequenceRef.current;" in source
    assert "const isLatestInsightsRequest = () => !cancelled" in source
    assert "const insightsStateOwnsScope = insightsScopeKey === comparisonScopeKey;" in source
    assert "const scopedInsights = insightsStateOwnsScope ? insights : null;" in source
    assert "<ComparisonInsightPanel insights={scopedInsights}" in source

    current_scope_guard = source.split("const resultMatchesCurrentScope =", 1)[1].split(
        "if (!resultMatchesCurrentScope)",
        1,
    )[0]
    for expression in (
        "result.baseline_run_id === baselineRunId",
        "result.test_run_id === testRunId",
        "result.baseline_lap === effectiveBaselineLap",
        "result.test_lap === effectiveTestLap",
        "result.target_zone_start_pct - startPct",
        "result.target_zone_end_pct - endPct",
    ):
        assert expression in current_scope_guard

    success_block = source.split(
        "fetchCompareInsights(request).then((nextData) => {",
        1,
    )[1].split("}).catch((caught: unknown) => {", 1)[0]
    assert success_block.index("if (!isLatestInsightsRequest()) return;") < success_block.index(
        "const responseMatchesRequest",
    )
    for expression in (
        "nextData.baseline_run_id === request.baseline_run_id",
        "nextData.test_run_id === request.test_run_id",
        "nextData.baseline_lap === request.baseline_lap",
        "nextData.test_lap === request.test_lap",
        "nextData.target_zone_start_pct - request.target_zone_start_pct",
        "nextData.target_zone_end_pct - request.target_zone_end_pct",
    ):
        assert expression in success_block

    mismatch_block = success_block.split("if (!responseMatchesRequest)", 1)[1].split(
        "setInsights(nextData)",
        1,
    )[0]
    assert "setInsights(null);" in mismatch_block
    assert "Comparison insights scope error" in mismatch_block
    assert "No insight observation is shown." in mismatch_block
    assert "return;" in mismatch_block
    assert 'role="alert"' in source


def test_compare_tire_read_uses_uninterrupted_eligible_lap_blocks() -> None:
    route = _read("api/routes_compare.py")
    eligibility = _read("racelab_engine/analysis/lap_eligibility.py")

    tire_call = route.split("tire_comparison = aggregate_tire_comparison", 1)[1].split(
        "shock_comparison =", 1
    )[0]
    assert "longest_contiguous_eligible_lap_count(bl_overview.laps)" in tire_call
    assert "longest_contiguous_eligible_lap_count(t_overview.laps)" in tire_call
    assert "min(" in tire_call
    assert "if previous_lap_number is not None and lap.lap_number == previous_lap_number + 1" in eligibility
    assert "if not lap_is_eligible(lap):" in eligibility


def test_compare_insights_name_drag_scrub_as_a_proxy_not_measured_drag() -> None:
    source = _read("ui/src/components/ComparisonInsightPanel.tsx")

    assert 'import { ProxyBadge } from "./ProxyBadge";' in source
    assert "Drag/scrub proxy Δ" in source
    assert 'data-value-basis="proxy"' in source
    assert '<ProxyBadge kind="proxy"' in source
    assert "comparison-insight-proxy-authority" in source
    assert "Any drag/scrub language below means telemetry-derived resistance or scrub suspicion" in source
    assert "not measured aerodynamic drag force or a drag coefficient" in source
    assert "<th>Drag Δ</th>" not in source
