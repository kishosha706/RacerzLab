import type { CrewChiefEvidenceEntry, CrewChiefTerminalDecision } from "../types/crewChief";
import type { CurrentEngineeringKnowledgeProjection } from "../types/engineeringKnowledge";

type Props = {
  projection: CurrentEngineeringKnowledgeProjection;
  evidenceEntries: CrewChiefEvidenceEntry[];
  p19Next: CrewChiefTerminalDecision;
  onFocusEvidence: (entry: CrewChiefEvidenceEntry) => void;
};

function label(value: string): string {
  return value.replace(/^mechanism:/, "").replace(/_/g, " ");
}

function unique(values: string[]): string[] {
  return [...new Set(values)];
}

export function EngineeringKnowledgeSpine({
  projection,
  evidenceEntries,
  p19Next,
  onFocusEvidence,
}: Props) {
  const leading = projection.leading_hypothesis_ids
    .map((effectId) => projection.hypotheses.find((item) => item.effect_id === effectId))
    .filter((item) => item !== undefined);
  const current = leading[0] ?? projection.hypotheses.find(
    (item) => item.level !== "unsupported_remove",
  );
  const currentMechanisms = unique(leading.flatMap((item) => item.p35_mechanism_ids));
  const currentComponents = unique(leading.flatMap((item) => item.p26_component_family_ids));
  const missing = unique(leading.flatMap((item) => item.missing_evidence));
  const history = leading.flatMap((item) => item.controlled_history);
  const supportIds = new Set(leading.flatMap((item) => item.support_artifact_ids));
  const contradictionIds = new Set(leading.flatMap((item) => item.contradiction_artifact_ids));
  const navigable = evidenceEntries.filter(
    (entry) => supportIds.has(entry.artifact_id) || contradictionIds.has(entry.artifact_id),
  );
  const opportunity = evidenceEntries.find(
    (entry) => entry.artifact_id === projection.p32_opportunity_id,
  );
  const discriminatorFocus = projection.next_discriminator_contract_id == null
    ? null
    : evidenceEntries.find((entry) => (
      entry.typed_artifact?.artifact_type === "vehicle_dynamics_focus"
      && entry.typed_artifact.focus.observation_contract_id
        === projection.next_discriminator_contract_id
    )) ?? null;

  return (
    <section className="engineering-knowledge-spine" aria-label="Unified Dial-In engineering knowledge">
      <header>
        <div>
          <span className="eyebrow">DIAL-IN KNOWLEDGE · P35.1</span>
          <h3>{currentMechanisms.length > 0 ? "Current mechanism-to-setup map" : "Reviewed setup knowledge"}</h3>
        </div>
        <span className="engineering-knowledge-authority">P19 ONLY FOR ACTION</span>
      </header>

      <div className="engineering-knowledge-grid">
        <article>
          <h4>Why this system is relevant</h4>
          <p>{currentMechanisms.length > 0
            ? `${currentMechanisms.map(label).join(" · ")} remain current evidence candidates.`
            : "No current mechanism cleared the evidence gates; reviewed knowledge remains educational."}</p>
          <small>{projection.complaint_prior
            ? `Driver report is a prior only: “${projection.complaint_prior}”.`
            : "No driver complaint is being used as a ranking prior."}</small>
        </article>

        <article>
          <h4>What it physically changes</h4>
          <p>{current?.physical_role ?? `${label(current?.setup_area ?? "setup system")} remains a static mechanical relationship only.`}</p>
          <small>{currentComponents.length > 0
            ? `${currentComponents.map(label).join(" · ")} are mechanically related component families, not proven causes.`
            : "No current component family has cleared the evidence gates."}</small>
          {current && current.countereffect_ids.length > 0 && (
            <small>Protect: {current.countereffect_ids.slice(0, 3).map(label).join(" · ")}.</small>
          )}
        </article>

        <article>
          <h4>What the car is doing now</h4>
          <p>{projection.p32_opportunity_id == null
            ? "P32 has no measured time opportunity for this scope."
            : opportunity
              ? `P32 opportunity · ${opportunity.phase ?? "unscoped phase"} · ${opportunity.lap_pct_start ?? "?"}–${opportunity.lap_pct_end ?? "?"}% · L${opportunity.lap_numbers.join(", L")}`
              : "The exact P32 opportunity is bound, but its focus entry is not navigable here."}</p>
          {navigable.length > 0 && <div className="engineering-knowledge-evidence">
            {navigable.slice(0, 4).map((entry) => (
              <button type="button" key={entry.artifact_id} onClick={() => onFocusEvidence(entry)}>
                {entry.polarity === "support" ? "Open support" : "Open contradiction / uncertainty"}
              </button>
            ))}
          </div>}
        </article>

        <article>
          <h4>What evidence is missing</h4>
          <p>{missing.length > 0
            ? missing.slice(0, 3).join(" · ")
            : "No additional bridge-specific evidence debt is projected for the leading candidate."}</p>
        </article>

        <article>
          <h4>What would separate the candidates</h4>
          <p>{discriminatorFocus?.typed_artifact?.artifact_type === "vehicle_dynamics_focus"
            ? `${discriminatorFocus.typed_artifact.focus.inspection_tool_id.replace(/^inspect_/, "").replace(/_/g, " ")} in the exact current evidence scope.`
            : "No candidate-owned discriminator is available in the current scope."}</p>
          {discriminatorFocus && (
            <button type="button" onClick={() => onFocusEvidence(discriminatorFocus)}>
              Open bounded inspection
            </button>
          )}
        </article>

        <article>
          <h4>What history says</h4>
          <p>{history.length > 0
            ? `${history.length} exact/compatible controlled record${history.length === 1 ? "" : "s"}; policy and countereffects remain separate.`
            : "No exact or compatible controlled response is allowed to outrank current evidence."}</p>
          {history.slice(0, 3).map((item) => (
            <small key={`${item.experience_id}:${item.workflow_id}`}>
              {item.policy_verdict} · mechanism {item.mechanism_assessment} · response {item.control_response}
            </small>
          ))}
        </article>
      </div>

      <footer>
        <span>NEXT · P19</span>
        <strong>{p19Next.title}</strong>
        <p>{p19Next.instruction}</p>
      </footer>
    </section>
  );
}
