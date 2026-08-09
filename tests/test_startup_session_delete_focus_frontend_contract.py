from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _startup() -> str:
    return (ROOT / "ui/src/components/StartupScreen.tsx").read_text(encoding="utf-8")


def _between(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def test_delete_confirmation_focuses_keep_and_keep_restores_its_trigger() -> None:
    startup = _startup()

    confirm_effect = _between(
        startup,
        "if (!confirmDelete || deletingSession) return;",
        "}, [confirmDelete, deletingSession]);",
    )
    assert "keepButtonRefs.current.get(confirmDelete)" in confirm_effect
    assert "keepButton.focus();" in confirm_effect

    keep_handler = _between(
        startup,
        "const handleKeepSession = useCallback((sessionId: string) => {",
        "}, []);",
    )
    assert 'kind: "delete-trigger", sessionId' in keep_handler
    assert "setConfirmDelete(null);" in keep_handler
    assert "deleteTriggerRefs.current.get(pendingFocus.sessionId)" in startup
    assert "document.activeElement === target" in startup


def test_successful_delete_waits_for_reload_then_focuses_by_stable_session_id() -> None:
    startup = _startup()
    neighbor_helper = _between(
        startup,
        "function neighboringSessionIds(",
        "export function StartupScreen",
    )
    delete_handler = _between(
        startup,
        "const handleDelete = useCallback(async (sessionId: string) => {",
        "}, [loadSessions, sessions]);",
    )

    assert ".session_id" in neighbor_helper
    assert ".name" not in neighbor_helper
    assert "if (next) neighbors.push(next.session_id);" in neighbor_helper
    assert "if (previous) neighbors.push(previous.session_id);" in neighbor_helper
    assert "if (deletingSessionRef.current) return;" in delete_handler
    assert delete_handler.index("await deleteSession(sessionId);") < delete_handler.index(
        "await loadSessions();"
    ) < delete_handler.index('kind: "session-or-new"')
    assert "preferredSessionIds" in delete_handler
    assert "fallbackIndex" in delete_handler
    assert "sessionCardRefs.current.get(sessionId)" in startup
    assert "target ??= newSessionButtonRef.current;" in startup
    assert "ref={newSessionButtonRef}" in startup


def test_stale_session_loads_cannot_replace_the_latest_list_or_focus_target() -> None:
    startup = _startup()

    assert "const loadRequestRef = useRef(0);" in startup
    assert startup.count("requestId !== loadRequestRef.current") == 2
    assert "if (requestId === loadRequestRef.current) setLoading(false);" in startup
    assert "if (!pendingFocus || loading || confirmDelete) return;" in startup
    assert "candidate?.isConnected" in startup
    assert "!target?.isConnected || target.disabled" in startup


def test_failed_delete_is_visible_while_safe_confirmation_focus_is_preserved() -> None:
    startup = _startup()
    delete_handler = _between(
        startup,
        "const handleDelete = useCallback(async (sessionId: string) => {",
        "}, [loadSessions, sessions]);",
    )

    assert 'setDeleteError("Could not remove this session. Nothing was deleted. Try again or keep it.");' in delete_handler
    assert 'className="session-delete-error" role="alert"' in startup
    catch_block = delete_handler.split("} catch {", 1)[1].split("} finally", 1)[0]
    assert "setConfirmDelete(null);" not in catch_block
    assert "if (!confirmDelete || deletingSession) return;" in startup
