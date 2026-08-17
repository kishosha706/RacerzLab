"""Durable, fail-closed persistence for Crew Chief investigations."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.crew_chief import (
    ComponentResponseRecord,
    CrewChiefEffectivenessRecord,
    CrewChiefEvent,
    CrewChiefInvestigation,
    DriverKnowledgeRecord,
    EngineeringObjective,
    SuccessContract,
)
from racelab_engine.models.engineering_learning import EngineeringExperienceRecord
from racelab_engine.models.investigation_adaptation import (
    DiscriminatorOutcome,
    InvestigationOutcomeCertificate,
    PairedInvestigationComparison,
    PairedInvestigationDecision,
    investigation_adaptation_source_snapshot_sha256,
)
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.engineering_learning_repository import (
    LEARNING_CAPTURE_INTEGRITY_BLOCKER,
    EngineeringLearningIntegrityError,
    EngineeringLearningRepository,
)
from racelab_engine.storage.investigation_adaptation_repository import (
    InvestigationAdaptationIntegrityError,
    InvestigationAdaptationRepository,
)


def crew_chief_event_hash(event: CrewChiefEvent) -> str:
    payload = event.model_dump(mode="json", exclude={"event_hash"})
    return canonical_json_sha256(payload)


def _event_capture_source(event: CrewChiefEvent) -> dict[str, Any]:
    payload = event.model_dump(mode="json", exclude={"event_hash"})
    event_payload = payload["payload"]
    event_payload.update(
        {
            "learning_capture_state": "not_applicable",
            "learning_capture_experience_id": None,
            "learning_capture_experience_sha256": None,
            "learning_capture_blocker_reason": None,
            "adaptation_capture_state": "not_applicable",
            "adaptation_capture_certificate_id": None,
            "adaptation_capture_certificate_sha256": None,
            "adaptation_capture_blocker_reason": None,
        }
    )
    return payload


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CrewChiefIntegrityError(ValueError):
    """Raised when durable investigation history cannot be trusted."""


P34_CAPTURE_INTEGRITY_BLOCKER = (
    "P34 adaptation capture was blocked by immutable-ledger integrity; "
    "the attempted certificate and comparison were not admitted."
)
P34_CAPTURE_P33_BLOCKER = (
    "P34 adaptation capture was blocked because the authoritative P33 terminal "
    "truth unit could not be admitted."
)


class CrewChiefRepository:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path

    def save_investigation(self, investigation: CrewChiefInvestigation) -> None:
        connection = initialize_database(self.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT investigation_json FROM crew_chief_investigations "
                "WHERE investigation_id = ?",
                (investigation.investigation_id,),
            ).fetchone()
            encoded = investigation.model_dump_json()
            if row is not None and row["investigation_json"] != encoded:
                raise CrewChiefIntegrityError(
                    "investigation identity already owns other data"
                )
            if row is None:
                connection.execute(
                    """
                    INSERT INTO crew_chief_investigations (
                      investigation_id, run_id, session_id, workspace_revision,
                      status, opened_at, investigation_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        investigation.investigation_id,
                        investigation.workspace_identity.run_id,
                        investigation.workspace_identity.session_id,
                        investigation.workspace_identity.workspace_revision,
                        investigation.status,
                        investigation.opened_at.isoformat(),
                        encoded,
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_investigation(self, investigation_id: str) -> CrewChiefInvestigation | None:
        connection = initialize_database(self.db_path)
        try:
            row = connection.execute(
                "SELECT * FROM crew_chief_investigations WHERE investigation_id = ?",
                (investigation_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        investigation = CrewChiefInvestigation.model_validate_json(
            row["investigation_json"]
        )
        if (
            investigation.investigation_id != row["investigation_id"]
            or investigation.workspace_identity.run_id != row["run_id"]
            or investigation.workspace_identity.session_id != row["session_id"]
            or investigation.workspace_identity.workspace_revision
            != row["workspace_revision"]
            or investigation.status != row["status"]
            or investigation.opened_at.isoformat() != row["opened_at"]
        ):
            raise CrewChiefIntegrityError("investigation row identity is corrupt")
        return investigation

    def latest_investigation(
        self, run_id: str, session_id: str
    ) -> CrewChiefInvestigation | None:
        connection = initialize_database(self.db_path)
        try:
            row = connection.execute(
                """
                SELECT investigation_id FROM crew_chief_investigations
                WHERE run_id = ? AND session_id = ?
                ORDER BY opened_at DESC, investigation_id DESC LIMIT 1
                """,
                (run_id, session_id),
            ).fetchone()
        finally:
            connection.close()
        return self.get_investigation(row["investigation_id"]) if row else None

    def record_continue_action(self, investigation_id: str) -> int:
        """Record one user-requested Continue/bounded-advance action outside P34 events."""

        connection = initialize_database(self.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            updated = connection.execute(
                """
                UPDATE crew_chief_investigations
                SET continue_action_count = continue_action_count + 1
                WHERE investigation_id = ?
                """,
                (investigation_id,),
            )
            if updated.rowcount != 1:
                raise CrewChiefIntegrityError(
                    "Crew Chief continue action has no investigation identity"
                )
            row = connection.execute(
                "SELECT continue_action_count FROM crew_chief_investigations "
                "WHERE investigation_id = ?",
                (investigation_id,),
            ).fetchone()
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return int(row["continue_action_count"])

    def continue_action_count(self, investigation_id: str) -> int:
        connection = initialize_database(self.db_path)
        try:
            row = connection.execute(
                "SELECT continue_action_count FROM crew_chief_investigations "
                "WHERE investigation_id = ?",
                (investigation_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise CrewChiefIntegrityError(
                "Crew Chief continue action count has no investigation identity"
            )
        value = int(row["continue_action_count"])
        if value < 0:
            raise CrewChiefIntegrityError("Crew Chief continue action count is corrupt")
        return value

    @classmethod
    def _p34_pair_source_snapshot_sha256(cls, pair: Any) -> str:
        return investigation_adaptation_source_snapshot_sha256(
            run_id=pair.run_id,
            session_id=pair.session_id,
            workspace_revision=pair.workspace_revision,
            authority_revision=pair.authority_revision,
            current_truth_sha256=pair.current_truth_sha256,
            p19_snapshot_sha256=pair.p19_snapshot_sha256,
            p20_projection_sha256=pair.p20_projection_sha256,
            p26_projection_sha256=pair.p26_projection_sha256,
            p32_projection_sha256=pair.p32_projection_sha256,
        )

    @classmethod
    def _validate_p34_prediction_receipt(
        cls,
        connection: Any,
        event: CrewChiefEvent,
    ) -> None:
        """Authenticate an optional frozen-pair receipt before event append."""

        pair_id = event.payload.adaptation_prediction_pair_id
        pair_sha256 = event.payload.adaptation_prediction_pair_sha256
        if pair_id is not None:
            row = connection.execute(
                "SELECT record_id, record_sha256, record_kind, recorded_at, "
                "record_json FROM investigation_adaptation_records "
                "WHERE record_id = ?",
                (pair_id,),
            ).fetchone()
            if (
                row is None
                or row["record_sha256"] != pair_sha256
                or row["record_kind"] != "paired_decision"
            ):
                raise CrewChiefIntegrityError(
                    "Crew Chief event P34 prediction receipt is stale or swapped"
                )
            try:
                pair = PairedInvestigationDecision.model_validate_json(
                    row["record_json"]
                )
                recorded_at = datetime.fromisoformat(row["recorded_at"])
            except (TypeError, ValueError) as exc:
                raise CrewChiefIntegrityError(
                    "Crew Chief event P34 prediction receipt is corrupt"
                ) from exc
            if (
                pair.pair_id != pair_id
                or pair.pair_sha256 != pair_sha256
                or pair.investigation_id != event.investigation_id
                or pair.workspace_revision != event.workspace_revision
                or pair.step_number + 1 != event.sequence
                or pair.decision_frozen_at >= event.created_at
                or recorded_at > event.created_at
                or event.payload.adaptation_prediction_source_snapshot_sha256
                != cls._p34_pair_source_snapshot_sha256(pair)
                or not cls._p34_production_action_matches_event(pair, event)
            ):
                raise CrewChiefIntegrityError(
                    "Crew Chief event does not exactly follow its frozen P34 prediction"
                )
            return

        if event.event_type not in {
            "tool_invoked",
            "driver_question_asked",
            "decision_emitted",
        }:
            return
        rows = connection.execute(
            "SELECT record_json FROM investigation_adaptation_records "
            "WHERE record_kind = 'paired_decision' AND investigation_id = ? "
            "AND workspace_revision = ? AND step_number = ?",
            (
                event.investigation_id,
                event.workspace_revision,
                event.sequence - 1,
            ),
        ).fetchall()
        for row in rows:
            try:
                pair = PairedInvestigationDecision.model_validate_json(
                    row["record_json"]
                )
            except (TypeError, ValueError):
                # P34 corruption is handled by its typed terminal savepoint. It
                # must not become a new Crew/P19 authority gate here.
                continue
            if (
                pair.decision_frozen_at < event.created_at
                and cls._p34_production_action_matches_event(pair, event)
            ):
                raise CrewChiefIntegrityError(
                    "Crew Chief executable event omitted its frozen P34 prediction receipt"
                )

    @classmethod
    def _append_event(cls, connection: Any, event: CrewChiefEvent) -> None:
        if crew_chief_event_hash(event) != event.event_hash:
            raise CrewChiefIntegrityError("Crew Chief event hash mismatch")
        cls._validate_p34_prediction_receipt(connection, event)
        existing = connection.execute(
            "SELECT event_json FROM crew_chief_events WHERE event_id = ?",
            (event.event_id,),
        ).fetchone()
        encoded = event.model_dump_json()
        if existing is not None:
            if existing["event_json"] != encoded:
                raise CrewChiefIntegrityError("event identity already owns other data")
            return
        row = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) AS last_sequence, "
            "(SELECT event_hash FROM crew_chief_events AS latest "
            " WHERE latest.investigation_id = ? "
            " ORDER BY sequence DESC LIMIT 1) AS last_event_hash "
            "FROM crew_chief_events WHERE investigation_id = ?",
            (event.investigation_id, event.investigation_id),
        ).fetchone()
        expected = int(row["last_sequence"]) + 1
        if event.sequence != expected:
            raise CrewChiefIntegrityError(
                f"event sequence {event.sequence} does not follow {expected - 1}"
            )
        connection.execute(
            """
            INSERT INTO crew_chief_events (
              event_id, investigation_id, sequence, workspace_revision,
              created_at, event_hash, event_type, event_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.investigation_id,
                event.sequence,
                event.workspace_revision,
                event.created_at.isoformat(),
                event.event_hash,
                event.event_type,
                encoded,
            ),
        )
        previous_hash = row["last_event_hash"]
        updated = connection.execute(
            """
            UPDATE crew_chief_investigations
            SET event_count = ?, event_head_hash = ?
            WHERE investigation_id = ? AND event_count = ?
              AND (
                (? IS NULL AND event_head_hash IS NULL)
                OR event_head_hash = ?
              )
            """,
            (
                event.sequence,
                event.event_hash,
                event.investigation_id,
                event.sequence - 1,
                previous_hash,
                previous_hash,
            ),
        )
        if updated.rowcount != 1:
            raise CrewChiefIntegrityError(
                "Crew Chief event stream head does not match append history"
            )

    def append_event(self, event: CrewChiefEvent) -> None:
        if event.event_type in {"decision_emitted", "investigation_abandoned"}:
            raise ValueError(
                "Terminal Crew events require the atomic P33 learning-capture path."
            )
        connection = initialize_database(self.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._append_event(connection, event)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def append_events(self, events: tuple[CrewChiefEvent, ...]) -> None:
        """Commit one ordered non-terminal event unit without partial history."""

        if not events:
            raise ValueError("Crew Chief event unit cannot be empty.")
        if any(
            event.event_type in {"decision_emitted", "investigation_abandoned"}
            for event in events
        ):
            raise ValueError(
                "Terminal Crew events require the atomic P33 learning-capture path."
            )
        connection = initialize_database(self.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            for event in events:
                self._append_event(connection, event)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def append_inspection_trace(
        self, events: tuple[CrewChiefEvent, ...]
    ) -> None:
        """Atomically persist one tool pair and its complete cognitive trace."""

        if (
            len(events) < 4
            or events[0].event_type != "tool_invoked"
            or events[1].event_type != "tool_result_attached"
            or events[-1].event_type != "critique_completed"
            or not any(event.event_type == "subgoal_completed" for event in events)
        ):
            raise ValueError(
                "Crew Chief inspection trace requires request, result, subgoal, and critic events."
            )
        self.append_events(events)

    def append_terminal_event_and_experience(
        self,
        event: CrewChiefEvent,
        experience: EngineeringExperienceRecord,
        *,
        outcome_certificate: InvestigationOutcomeCertificate | None = None,
        outcome_comparison: PairedInvestigationComparison | None = None,
        discriminator_outcome: DiscriminatorOutcome | None = None,
    ) -> CrewChiefEvent:
        """Commit terminal Crew/P33/P34 truth atomically when P34 is healthy.

        Typed P34 corruption is attention-only: Crew and P33 still commit with
        an immutable blocked P34 attempt on the terminal event.  Unexpected
        failures roll back the complete transaction.
        """

        if event.event_type not in {"decision_emitted", "investigation_abandoned"}:
            raise ValueError("P33 terminal append requires a terminal Crew event.")
        if (
            experience.source_kind != "resolved_investigation"
            or experience.source_investigation_id != event.investigation_id
            or event.event_id not in experience.source_event_ids
            or experience.investigation_outcome is None
        ):
            raise ValueError(
                "P33 investigation experience must bind the exact terminal Crew event."
            )
        captured = self._event_with_learning_capture(
            event,
            experience,
            state="captured",
            outcome_certificate=outcome_certificate,
            adaptation_state=(
                "captured" if outcome_certificate is not None else "not_applicable"
            ),
        )
        learning_blocked = self._event_with_learning_capture(
            event,
            experience,
            state="blocked",
            blocker_reason=LEARNING_CAPTURE_INTEGRITY_BLOCKER,
            outcome_certificate=outcome_certificate,
            adaptation_state=(
                "blocked" if outcome_certificate is not None else "not_applicable"
            ),
            adaptation_blocker_reason=(
                P34_CAPTURE_P33_BLOCKER if outcome_certificate is not None else None
            ),
        )
        adaptation_blocked = self._event_with_learning_capture(
            event,
            experience,
            state="captured",
            outcome_certificate=outcome_certificate,
            adaptation_state=(
                "blocked" if outcome_certificate is not None else "not_applicable"
            ),
            adaptation_blocker_reason=(
                P34_CAPTURE_INTEGRITY_BLOCKER
                if outcome_certificate is not None
                else None
            ),
        )
        connection = initialize_database(self.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT event_json FROM crew_chief_events WHERE event_id = ?",
                (event.event_id,),
            ).fetchone()
            if existing is not None:
                persisted = CrewChiefEvent.model_validate_json(existing["event_json"])
                if persisted.payload.learning_capture_state in {"captured", "blocked"}:
                    self._assert_same_learning_capture_attempt(
                        persisted,
                        event,
                        experience,
                        outcome_certificate,
                    )
                    if persisted.payload.adaptation_capture_state == "captured":
                        if outcome_certificate is None or outcome_comparison is None:
                            raise ValueError(
                                "A captured P34 terminal attempt requires its exact replay unit."
                            )
                        self._validate_p34_terminal_capture(
                            connection,
                            event,
                            experience,
                            outcome_certificate,
                            outcome_comparison,
                            discriminator_outcome,
                        )
                    connection.rollback()
                    return persisted
            EngineeringLearningRepository(self.db_path).stream_state(
                connection=connection,
                validate_chain=True,
                validate_payloads=False,
            )
            persisted_event = captured
            if outcome_certificate is not None:
                connection.execute("SAVEPOINT p34_terminal_capture")
                try:
                    if outcome_comparison is None:
                        raise InvestigationAdaptationIntegrityError(
                            "P34 outcome certificate requires its paired comparison"
                        )
                    self._validate_p34_terminal_capture(
                        connection,
                        event,
                        experience,
                        outcome_certificate,
                        outcome_comparison,
                        discriminator_outcome,
                    )
                    adaptation_repository = InvestigationAdaptationRepository(
                        self.db_path
                    )
                    from racelab_engine.services.investigation_adaptation_service import (
                        append_p34_terminal_capture_unit_in_transaction,
                    )

                    pair_result = adaptation_repository.query_records(
                        record_kinds=("paired_decision",),
                        investigation_id=event.investigation_id,
                        limit=10_000,
                        connection=connection,
                    )
                    if pair_result.blockers:
                        raise InvestigationAdaptationIntegrityError(
                            pair_result.blockers[0]
                        )
                    append_p34_terminal_capture_unit_in_transaction(
                        adaptation_repository,
                        connection,
                        investigation_pairs=tuple(reversed(pair_result.records)),
                        certificate=outcome_certificate,
                        comparison=outcome_comparison,
                        discriminator_outcome=discriminator_outcome,
                    )
                    connection.execute("RELEASE SAVEPOINT p34_terminal_capture")
                except InvestigationAdaptationIntegrityError:
                    connection.execute("ROLLBACK TO SAVEPOINT p34_terminal_capture")
                    connection.execute("RELEASE SAVEPOINT p34_terminal_capture")
                    persisted_event = adaptation_blocked
            self._append_event(connection, persisted_event)
            EngineeringLearningRepository.append_experience_in_transaction(
                connection,
                experience,
            )
            connection.commit()
            return persisted_event
        except EngineeringLearningIntegrityError:
            connection.rollback()
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._append_event(connection, learning_blocked)
                connection.commit()
                return learning_blocked
            except Exception:
                connection.rollback()
                raise
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _canonical_p34_pair_in_transaction(
        connection: Any,
        investigation_id: str,
    ) -> Any:
        repository = InvestigationAdaptationRepository()
        result = repository.query_records(
            record_kinds=("paired_decision",),
            investigation_id=investigation_id,
            limit=10_000,
            connection=connection,
        )
        if result.blockers:
            raise InvestigationAdaptationIntegrityError(result.blockers[0])
        pairs = tuple(reversed(result.records))
        if not pairs:
            return None
        persistence_order = {
            pair.pair_id: index for index, pair in enumerate(pairs)
        }

        def category(pair: Any) -> int:
            both_tools = (
                getattr(pair, "baseline_decision", None) is not None
                and pair.baseline_decision.decision_kind == "inspect_tool"
                and pair.memory_decision.decision_kind == "inspect_tool"
            )
            if both_tools and (
                pair.baseline_decision.executable_identity
                != pair.memory_decision.executable_identity
            ):
                return 0
            return 1 if both_tools else 2

        return min(
            pairs,
            key=lambda pair: (
                category(pair),
                pair.step_number,
                persistence_order[pair.pair_id],
                pair.pair_id,
            ),
        )

    @staticmethod
    def _p34_production_action_matches_event(
        pair: Any,
        event: CrewChiefEvent,
    ) -> bool:
        decision = pair.production_decision
        if (
            event.sequence != pair.step_number + 1
            or event.workspace_revision != pair.workspace_revision
        ):
            return False
        if decision.decision_kind == "inspect_tool":
            return (
                event.event_type == "tool_invoked"
                and event.payload.tool_id == decision.action_id
            )
        if decision.decision_kind == "ask_driver":
            return (
                event.event_type == "driver_question_asked"
                and event.payload.question_id == decision.action_id
            )
        if decision.decision_kind in {"no_call", "observe_only"}:
            terminal_kind = event.payload.decision_kind
            expected_decision_kind = (
                "no_call" if terminal_kind == "no_call" else "observe_only"
            )
            expected_action = (
                f"terminal:{terminal_kind}:"
                f"{canonical_json_sha256([terminal_kind, event.payload.message])[:24]}"
            )
            return (
                event.event_type == "decision_emitted"
                and terminal_kind is not None
                and decision.decision_kind == expected_decision_kind
                and decision.action_id == expected_action
            )
        return False

    @classmethod
    def _p34_production_decision_matches_next_event(
        cls,
        pair: Any,
        event: CrewChiefEvent,
    ) -> bool:
        return (
            event.payload.adaptation_prediction_pair_id == pair.pair_id
            and event.payload.adaptation_prediction_pair_sha256
            == pair.pair_sha256
            and event.payload.adaptation_prediction_source_snapshot_sha256
            == cls._p34_pair_source_snapshot_sha256(pair)
            and pair.decision_frozen_at < event.created_at
            and cls._p34_production_action_matches_event(pair, event)
        )

    @classmethod
    def _validate_p34_terminal_capture(
        cls,
        connection: Any,
        event: CrewChiefEvent,
        experience: EngineeringExperienceRecord,
        certificate: InvestigationOutcomeCertificate,
        comparison: PairedInvestigationComparison,
        discriminator_outcome: DiscriminatorOutcome | None,
    ) -> None:
        InvestigationAdaptationRepository().stream_state(
            connection=connection,
            validate_chain=True,
            validate_payloads=False,
        )
        pair = cls._canonical_p34_pair_in_transaction(
            connection,
            event.investigation_id,
        )
        if pair is None or (
            pair.pair_id != certificate.pair_id
            or pair.pair_sha256 != certificate.pair_sha256
            or pair.decision_frozen_at != certificate.decision_frozen_at
        ):
            raise InvestigationAdaptationIntegrityError(
                "P34 outcome does not bind the canonical preregistered pair"
            )
        investigation_row = connection.execute(
            "SELECT investigation_json FROM crew_chief_investigations "
            "WHERE investigation_id = ?",
            (event.investigation_id,),
        ).fetchone()
        if investigation_row is None:
            raise InvestigationAdaptationIntegrityError(
                "P34 outcome has no immutable Crew investigation opening"
            )
        try:
            investigation = CrewChiefInvestigation.model_validate_json(
                investigation_row["investigation_json"]
            )
        except (TypeError, ValueError) as exc:
            raise InvestigationAdaptationIntegrityError(
                "P34 outcome Crew investigation opening is corrupt"
            ) from exc
        expected_terminal = (
            "abandoned"
            if event.event_type == "investigation_abandoned"
            else event.payload.decision_kind
        )
        fact = experience.investigation_outcome
        if fact is None or (
            certificate.investigation_id != event.investigation_id
            or certificate.investigation_opened_at != investigation.opened_at
            or certificate.starting_workspace_revision
            != investigation.workspace_identity.workspace_revision
            or certificate.ending_workspace_revision != event.workspace_revision
            or certificate.final_p19_snapshot_sha256
            != experience.closing_reasoning.reasoning_snapshot_sha256
            or certificate.terminal_crew_decision != expected_terminal
            or certificate.certified_at != event.created_at
            or certificate.decision_frozen_at >= event.created_at
            or certificate.elapsed_wall_seconds != fact.elapsed_seconds
            or certificate.investigation_steps != event.sequence
            or certificate.causes_separated != fact.eliminated_cause_ids
            or certificate.causes_left_unresolved != fact.unresolved_cause_ids
            or tuple(
                (item.cause_id, item.state)
                for item in certificate.final_p19_cause_states
            )
            != tuple(
                (item.cause_id, item.status)
                for item in experience.closing_reasoning.causes
            )
            or certificate.created_workflow_ids != fact.workflow_ids
            or certificate.workflow_created != bool(fact.workflow_ids)
            or certificate.consumption_metrics_state != "unavailable"
            or certificate.lap_ids_consumed is not None
            or certificate.measurement_mission_ids is not None
            or not certificate.consumption_metric_blockers
            or not set(certificate.completed_mandatory_check_ids).issubset(
                pair.baseline_decision.mandatory_check_ids
            )
        ):
            raise InvestigationAdaptationIntegrityError(
                "P34 outcome certificate does not match terminal Crew/P33 truth"
            )
        rows = connection.execute(
            "SELECT event_json FROM crew_chief_events WHERE investigation_id = ? "
            "ORDER BY sequence, event_id",
            (event.investigation_id,),
        ).fetchall()
        try:
            history = tuple(
                CrewChiefEvent.model_validate_json(row["event_json"]) for row in rows
            )
        except (TypeError, ValueError) as exc:
            raise InvestigationAdaptationIntegrityError(
                "P34 outcome source Crew history is corrupt"
            ) from exc
        events = history if any(item.event_id == event.event_id for item in history) else (
            *history,
            event,
        )
        next_event = next(
            (
                item
                for item in events
                if item.sequence == pair.step_number + 1
            ),
            None,
        )
        if next_event is None or not cls._p34_production_decision_matches_next_event(
            pair,
            next_event,
        ):
            raise InvestigationAdaptationIntegrityError(
                "P34 production decision does not match the exact next Crew event"
            )
        requests = tuple(
            item
            for item in events
            if item.event_type == "tool_invoked" and item.payload.tool_id is not None
        )
        results = tuple(
            item
            for item in events
            if item.event_type == "tool_result_attached"
            and item.payload.tool_id is not None
        )
        questions = tuple(
            item
            for item in events
            if item.event_type == "driver_question_asked"
            and item.payload.question_id is not None
        )
        answers = tuple(
            item for item in events if item.event_type == "driver_answer_recorded"
        )
        result_artifact_ids = {
            artifact_id
            for item in results
            for artifact_id in item.payload.artifact_ids
        }
        if (
            certificate.tool_request_event_ids
            != tuple(item.event_id for item in requests)
            or certificate.tools_actually_requested
            != tuple(item.payload.tool_id for item in requests)
            or certificate.tool_result_event_ids
            != tuple(item.event_id for item in results)
            or certificate.tool_results_received
            != tuple(item.payload.tool_id for item in results)
            or certificate.driver_question_ids
            != tuple(item.payload.question_id for item in questions)
            or certificate.driver_answer_event_ids
            != tuple(item.event_id for item in answers)
            or not set(certificate.qualified_artifact_ids).issubset(
                result_artifact_ids
            )
            or certificate.strongest_contradiction_id
            != pair.strongest_contradiction_id
            or certificate.strongest_contradiction_handled
            != (
                pair.strongest_contradiction_id is not None
                and pair.strongest_contradiction_id
                in certificate.qualified_artifact_ids
            )
        ):
            raise InvestigationAdaptationIntegrityError(
                "P34 outcome certificate does not match ordered Crew evidence lineage"
            )
        if (
            (discriminator_outcome is None)
            != (comparison.discriminator_outcome_id is None)
            or (
                discriminator_outcome is not None
                and (
                    comparison.discriminator_outcome_id
                    != discriminator_outcome.outcome_id
                    or comparison.discriminator_outcome_sha256
                    != discriminator_outcome.outcome_sha256
                )
            )
        ):
            raise InvestigationAdaptationIntegrityError(
                "P34 comparison does not bind its exact discriminator outcome"
            )
        if discriminator_outcome is not None:
            adaptation_repository = InvestigationAdaptationRepository()
            source_pair = adaptation_repository.get_paired_decision(
                discriminator_outcome.source_pair_sha256,
                connection=connection,
            )
            event_by_id = {item.event_id: item for item in events}
            request = event_by_id.get(discriminator_outcome.request_event_id)
            result = event_by_id.get(discriminator_outcome.result_event_id)
            try:
                from racelab_engine.services.investigation_adaptation_service import (
                    build_discriminator_outcome_from_crew_events,
                )

                expected_discriminator = (
                    build_discriminator_outcome_from_crew_events(
                        prediction_pair=pair,
                        source_pair=source_pair,
                        certificate=certificate,
                        request_event=request,
                        result_event=result,
                        investigation_events=events,
                        transition_sequence=discriminator_outcome.transition_sequence,
                        evaluated_at=discriminator_outcome.evaluated_at,
                    )
                    if source_pair is not None
                    and request is not None
                    and result is not None
                    else None
                )
            except (TypeError, ValueError):
                expected_discriminator = None
            if expected_discriminator != discriminator_outcome:
                raise InvestigationAdaptationIntegrityError(
                    "P34 discriminator does not match ordered Crew/P19 lineage"
                )
        if (
            comparison.investigation_id != event.investigation_id
            or comparison.pair_id != pair.pair_id
            or comparison.pair_sha256 != pair.pair_sha256
            or comparison.certificate_id != certificate.certificate_id
            or comparison.certificate_sha256 != certificate.certificate_sha256
            or comparison.decision_frozen_at != pair.decision_frozen_at
            or comparison.compared_at < certificate.certified_at
        ):
            raise InvestigationAdaptationIntegrityError(
                "P34 comparison does not bind the exact pair and outcome certificate"
            )

    @staticmethod
    def _event_with_learning_capture(
        event: CrewChiefEvent,
        experience: EngineeringExperienceRecord,
        *,
        state: str,
        blocker_reason: str | None = None,
        outcome_certificate: InvestigationOutcomeCertificate | None = None,
        adaptation_state: str = "not_applicable",
        adaptation_blocker_reason: str | None = None,
    ) -> CrewChiefEvent:
        payload = event.payload.model_copy(
            update={
                "learning_capture_state": state,
                "learning_capture_experience_id": experience.experience_id,
                "learning_capture_experience_sha256": experience.experience_sha256,
                "learning_capture_blocker_reason": blocker_reason,
                "adaptation_capture_state": adaptation_state,
                "adaptation_capture_certificate_id": (
                    outcome_certificate.certificate_id
                    if outcome_certificate is not None
                    else None
                ),
                "adaptation_capture_certificate_sha256": (
                    outcome_certificate.certificate_sha256
                    if outcome_certificate is not None
                    else None
                ),
                "adaptation_capture_blocker_reason": adaptation_blocker_reason,
            }
        )
        draft = event.model_copy(update={"payload": payload, "event_hash": "0" * 64})
        return CrewChiefEvent.model_validate(
            {
                **draft.model_dump(mode="python"),
                "event_hash": crew_chief_event_hash(draft),
            }
        )

    @staticmethod
    def _assert_same_learning_capture_attempt(
        persisted: CrewChiefEvent,
        requested: CrewChiefEvent,
        experience: EngineeringExperienceRecord,
        outcome_certificate: InvestigationOutcomeCertificate | None,
    ) -> None:
        if (
            _event_capture_source(persisted) != _event_capture_source(requested)
            or persisted.payload.learning_capture_experience_id
            != experience.experience_id
            or persisted.payload.learning_capture_experience_sha256
            != experience.experience_sha256
            or persisted.payload.adaptation_capture_certificate_id
            != (
                outcome_certificate.certificate_id
                if outcome_certificate is not None
                else None
            )
            or persisted.payload.adaptation_capture_certificate_sha256
            != (
                outcome_certificate.certificate_sha256
                if outcome_certificate is not None
                else None
            )
        ):
            raise ValueError(
                "A finalized Crew learning-capture source cannot be rebound."
            )

    def list_events(self, investigation_id: str) -> tuple[CrewChiefEvent, ...]:
        connection = initialize_database(self.db_path)
        try:
            rows = connection.execute(
                "SELECT * FROM crew_chief_events WHERE investigation_id = ? "
                "ORDER BY sequence, event_id",
                (investigation_id,),
            ).fetchall()
            stream = connection.execute(
                "SELECT event_count, event_head_hash "
                "FROM crew_chief_investigations WHERE investigation_id = ?",
                (investigation_id,),
            ).fetchone()
        finally:
            connection.close()
        if stream is None:
            if rows:
                raise CrewChiefIntegrityError(
                    "Crew Chief event stream has no owning investigation"
                )
            return ()
        events: list[CrewChiefEvent] = []
        for expected, row in enumerate(rows, start=1):
            event = CrewChiefEvent.model_validate_json(row["event_json"])
            if (
                event.investigation_id != investigation_id
                or event.event_id != row["event_id"]
                or event.sequence != expected
                or event.event_hash != row["event_hash"]
                or event.workspace_revision != row["workspace_revision"]
                or event.created_at.isoformat() != row["created_at"]
                or event.event_type != row["event_type"]
                or crew_chief_event_hash(event) != event.event_hash
            ):
                raise CrewChiefIntegrityError("Crew Chief event history is corrupt")
            events.append(event)
        expected_head = events[-1].event_hash if events else None
        if (
            int(stream["event_count"]) != len(events)
            or stream["event_head_hash"] != expected_head
        ):
            raise CrewChiefIntegrityError("Crew Chief event stream head is corrupt")
        return tuple(events)

    def save_objective(
        self,
        investigation_id: str,
        workspace_revision: str,
        objective: EngineeringObjective,
    ) -> None:
        objective_id = (
            f"cco_{canonical_json_sha256([investigation_id, objective])[:24]}"
        )
        connection = initialize_database(self.db_path)
        try:
            connection.execute(
                """
                INSERT INTO engineering_objectives (
                  objective_id, investigation_id, workspace_revision, selected_at,
                  objective_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(investigation_id) DO UPDATE SET
                  objective_id=excluded.objective_id,
                  workspace_revision=excluded.workspace_revision,
                  selected_at=excluded.selected_at,
                  objective_json=excluded.objective_json
                """,
                (
                    objective_id,
                    investigation_id,
                    workspace_revision,
                    _now(),
                    f'{{"objective":"{objective.value}"}}',
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def save_success_contract(
        self, investigation_id: str, contract: SuccessContract
    ) -> None:
        connection = initialize_database(self.db_path)
        try:
            connection.execute(
                """
                INSERT INTO crew_chief_success_contracts (
                  contract_id, investigation_id, workspace_revision, created_at,
                  contract_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(investigation_id) DO UPDATE SET
                  contract_id=excluded.contract_id,
                  workspace_revision=excluded.workspace_revision,
                  created_at=excluded.created_at,
                  contract_json=excluded.contract_json
                """,
                (
                    contract.contract_id,
                    investigation_id,
                    contract.workspace_revision,
                    _now(),
                    contract.model_dump_json(),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def save_response_record(self, record: ComponentResponseRecord) -> None:
        connection = initialize_database(self.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT record_json FROM component_response_records "
                "WHERE source_workflow_id = ?",
                (record.source_workflow_id,),
            ).fetchone()
            encoded = record.model_dump_json()
            if existing and existing["record_json"] != encoded:
                raise CrewChiefIntegrityError("workflow response history is immutable")
            connection.execute(
                """
                INSERT OR IGNORE INTO component_response_records (
                  record_id, source_workflow_id, source_run_id, context_identity,
                  created_at, record_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    record.source_workflow_id,
                    record.source_run_ids[-1],
                    record.context_identity,
                    _now(),
                    encoded,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_response_records(
        self, context_identity: str
    ) -> tuple[ComponentResponseRecord, ...]:
        connection = initialize_database(self.db_path)
        try:
            rows = connection.execute(
                "SELECT * FROM component_response_records "
                "WHERE context_identity = ? ORDER BY created_at, record_id",
                (context_identity,),
            ).fetchall()
        finally:
            connection.close()
        records: list[ComponentResponseRecord] = []
        for row in rows:
            record = ComponentResponseRecord.model_validate_json(row["record_json"])
            if (
                record.record_id != row["record_id"]
                or record.source_workflow_id != row["source_workflow_id"]
                or record.source_run_ids[-1] != row["source_run_id"]
                or record.context_identity != row["context_identity"]
            ):
                raise CrewChiefIntegrityError(
                    "component response history row identity is corrupt"
                )
            records.append(record)
        return tuple(records)

    def save_driver_memory(self, record: DriverKnowledgeRecord) -> None:
        connection = initialize_database(self.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            encoded = record.model_dump_json()
            existing = connection.execute(
                "SELECT record_json FROM crew_chief_driver_memory WHERE record_id = ?",
                (record.record_id,),
            ).fetchone()
            if existing and existing["record_json"] != encoded:
                raise CrewChiefIntegrityError("driver-memory identity is immutable")
            connection.execute(
                """
                INSERT OR IGNORE INTO crew_chief_driver_memory (
                  record_id, investigation_id, session_id, recorded_at, record_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    record.investigation_id,
                    record.session_id,
                    record.recorded_at.isoformat(),
                    encoded,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_driver_memory(self, session_id: str) -> tuple[DriverKnowledgeRecord, ...]:
        connection = initialize_database(self.db_path)
        try:
            rows = connection.execute(
                "SELECT * FROM crew_chief_driver_memory "
                "WHERE session_id = ? ORDER BY recorded_at, record_id",
                (session_id,),
            ).fetchall()
        finally:
            connection.close()
        records: list[DriverKnowledgeRecord] = []
        for row in rows:
            record = DriverKnowledgeRecord.model_validate_json(row["record_json"])
            if (
                record.record_id != row["record_id"]
                or record.investigation_id != row["investigation_id"]
                or record.session_id != row["session_id"]
                or record.recorded_at.isoformat() != row["recorded_at"]
            ):
                raise CrewChiefIntegrityError(
                    "Crew Chief driver-memory row identity is corrupt"
                )
            records.append(record)
        return tuple(records)

    def save_effectiveness(self, record: CrewChiefEffectivenessRecord) -> None:
        connection = initialize_database(self.db_path)
        try:
            connection.execute(
                """
                INSERT INTO crew_chief_effectiveness_records (
                  record_id, investigation_id, workspace_revision, recorded_at,
                  record_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(investigation_id) DO UPDATE SET
                  record_id=excluded.record_id,
                  workspace_revision=excluded.workspace_revision,
                  recorded_at=excluded.recorded_at,
                  record_json=excluded.record_json
                """,
                (
                    record.record_id,
                    record.investigation_id,
                    record.workspace_revision,
                    record.recorded_at.isoformat(),
                    record.model_dump_json(),
                ),
            )
            connection.commit()
        finally:
            connection.close()


__all__ = [
    "CrewChiefIntegrityError",
    "CrewChiefRepository",
    "crew_chief_event_hash",
]
