import type {
  AgentDetailEnvelope,
  Biography,
  RunFrame,
  RunManifest,
} from "../api/contracts";
import {
  beliefName,
  configNumber,
  countryName,
  percent,
  precise,
  titleCase,
} from "../lib/format";
import { eventShape } from "../lib/events";
import { Icon } from "./Icon";

interface PersonInspectorProps {
  detail: AgentDetailEnvelope | null;
  frame: RunFrame;
  loading: boolean;
  manifest: RunManifest;
  selectedAgentId: string | null;
  onClose: () => void;
  onSelectAgent: (agentId: string) => void;
}

function Meter({
  label,
  value,
  tone = "green",
}: {
  label: string;
  value: number;
  tone?: "green" | "gold" | "red" | "violet";
}) {
  const normalized = Math.min(1, Math.max(0, value));
  return (
    <div className="meter">
      <div className="meter-label">
        <span>{label}</span>
        <strong>{percent(normalized)}</strong>
      </div>
      <div className="meter-track">
        <span
          className={`meter-fill meter-${tone}`}
          style={{ width: `${normalized * 100}%` }}
        />
      </div>
    </div>
  );
}

function traitValue(
  traits: Record<string, number | string>,
  name: string,
): number | null {
  const value = traits[name];
  return typeof value === "number" ? value : null;
}

/**
 * What a life amounted to, once it is over.
 *
 * Everything shown is read off recorded state. Where the record is partial —
 * the event log is bounded, so an old person's early years may be gone — the
 * panel says so rather than presenting a fragment as a whole life.
 */
function LifeSummary({
  life,
  manifest,
}: {
  life: Biography;
  manifest: RunManifest;
}) {
  const span = life.founder
    ? `Already grown when the run began, died in year ${
        precise(life.died_year)
      }`
    : `Year ${precise(life.born_year)} to ${precise(life.died_year)}`;
  const childhood =
    life.childhood_development >= 0.85
      ? "well fed as a child"
      : life.childhood_development >= 0.6
        ? "adequately fed as a child"
        : "underfed as a child";
  const moved =
    life.birth_country === life.died_in_country
      ? null
      : `Left ${countryName(manifest.scenario, life.birth_country)} for ${
          countryName(manifest.scenario, life.died_in_country)
        }`;

  return (
    <section className="life-summary" aria-label="Life summary">
      <header>
        <span className="eyebrow">Life summary</span>
        <h3>{span}</h3>
      </header>

      <p className="life-sentence">
        Lived {precise(life.age_at_death)} years, {childhood}, and died of{" "}
        {titleCase(life.cause).toLowerCase()}
        {life.knew_seafaring ? ", knowing how to cross open water" : ""}.
        {life.bonded_years === null
          ? " Never formed a lasting bond."
          : ` Bonded for ${precise(life.bonded_years)} years.`}
      </p>

      <div className="life-figures">
        <span>
          <small>Children alive</small>
          <strong>{life.living_children}</strong>
        </span>
        <span>
          <small>Grandchildren alive</small>
          <strong>{life.living_grandchildren}</strong>
        </span>
        <span>
          <small>Generation</small>
          <strong>{life.generation}</strong>
        </span>
      </div>

      {moved === null ? null : <p className="life-moved">{moved}</p>}

      {life.moments.length === 0 ? null : (
        <ol className="life-moments">
          {life.moments.slice(-8).reverse().map((moment, index) => (
            <li key={`${moment.tick}-${moment.kind}-${index}`}>
              <span>{precise(moment.year)}</span>
              {eventShape(moment.kind).label}
            </li>
          ))}
        </ol>
      )}

      {life.moments_complete ? null : (
        <p className="life-partial">
          Only recent moments are kept. This person&rsquo;s earlier years are
          no longer in the engine&rsquo;s log.
        </p>
      )}
    </section>
  );
}

function InspectorLoading({ id }: { id: string }) {
  return (
    <div className="inspector-loading" aria-live="polite">
      <div className="person-avatar skeleton" />
      <div>
        <strong>Person {id}</strong>
        <span>Loading observed state…</span>
      </div>
      <div className="skeleton-block" />
      <div className="skeleton-block short" />
      <div className="skeleton-block" />
    </div>
  );
}

export function PersonInspector({
  detail,
  frame,
  loading,
  manifest,
  selectedAgentId,
  onClose,
  onSelectAgent,
}: PersonInspectorProps) {
  if (selectedAgentId === null) {
    return (
      <aside className="side-panel inspector-panel inspector-empty">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Inspect</span>
            <h2>Person</h2>
          </div>
          <Icon name="person" size={18} />
        </div>
        <div className="empty-inspector-art" aria-hidden="true">
          <span className="orbit orbit-one" />
          <span className="orbit orbit-two" />
          <Icon name="person" size={28} />
        </div>
        <h3>Select an individual</h3>
        <p>
          Choose a point on the map to observe inherited potential,
          development, present condition, decisions, and social memory.
        </p>
        <div className="inspector-principle">
          <Icon name="spark" size={14} />
          No combined “fitness” score
        </div>
      </aside>
    );
  }

  if (loading && detail === null) {
    return (
      <aside className="side-panel inspector-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Inspect</span>
            <h2>Person</h2>
          </div>
          <button
            aria-label="Close person inspector"
            className="icon-button"
            onClick={onClose}
            type="button"
          >
            <Icon name="close" size={16} />
          </button>
        </div>
        <InspectorLoading id={selectedAgentId} />
      </aside>
    );
  }

  if (detail === null) {
    return (
      <aside className="side-panel inspector-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Inspect</span>
            <h2>Person {selectedAgentId}</h2>
          </div>
          <button
            aria-label="Close person inspector"
            className="icon-button"
            onClick={onClose}
            type="button"
          >
            <Icon name="close" size={16} />
          </button>
        </div>
        <div className="inspector-error">
          This person is no longer available in the current observation.
        </div>
      </aside>
    );
  }

  const { agent } = detail;
  const country = countryName(
    manifest.scenario,
    agent.identity.birth_country,
  );
  const belief = beliefName(manifest.scenario, agent.identity.belief);
  const isStale = detail.tick !== frame.tick;
  const researchThreshold = configNumber(
    manifest,
    "discovery_threshold",
    1,
  );
  const maximumVesselDurability = configNumber(
    manifest,
    "vessel_durability",
    1,
  );
  const traitNames = [
    "metabolism",
    "fertility",
    "constitution",
    "immune_strength",
  ];

  const death = agent.status === "deceased" ? agent.death : null;

  return (
    <aside
      className={`side-panel inspector-panel${
        death === null ? "" : " is-deceased"
      }`}
    >
      <div className="panel-heading">
        <div>
          <span className="eyebrow">
            {death === null
              ? `Observed at tick ${detail.tick}`
              : `Final state at tick ${death.tick}`}
          </span>
          <h2>Person</h2>
        </div>
        <button
          aria-label="Close person inspector"
          className="icon-button"
          onClick={onClose}
          type="button"
        >
          <Icon name="close" size={16} />
        </button>
      </div>

      <div className="person-summary">
        <span className="person-avatar">
          <Icon name="person" size={20} />
        </span>
        <div>
          <h3>#{agent.id}</h3>
          <p>
            {country} · {titleCase(belief)}
          </p>
        </div>
        <span
          className={
            death === null
              ? `stage-badge stage-${agent.disease.stage}`
              : "stage-badge stage-deceased"
          }
        >
          {death === null ? titleCase(agent.disease.stage) : "Deceased"}
        </span>
      </div>

      {death === null ? null : (
        <div className="death-note" role="status">
          <Icon name="activity" size={14} />
          <span>
            Died in year {precise(death.year)} at age{" "}
            {precise(death.age)} — {titleCase(death.cause)}. Everything below
            is the state this person died in, not a live reading.
          </span>
        </div>
      )}

      {agent.biography === null ? null : (
        <LifeSummary life={agent.biography} manifest={manifest} />
      )}

      {isStale && death === null ? (
        <div className="stale-note">
          Detail is from tick {detail.tick}; map is at {frame.tick}.
        </div>
      ) : null}

      <div className="identity-row">
        <span>
          <small>Age</small>
          <strong>{precise(agent.life.age)} y</strong>
        </span>
        <span>
          <small>Generation</small>
          <strong>{agent.identity.generation}</strong>
        </span>
        <span>
          <small>Position</small>
          <strong>
            {precise(agent.location.x)}, {precise(agent.location.y)}
          </strong>
        </span>
      </div>

      <section className="inspector-section">
        <div className="section-title">
          <h4>Present condition</h4>
          <span>Acquired state</span>
        </div>
        <Meter label="Energy" value={agent.life.energy_fraction} tone="gold" />
        <Meter label="Health" value={agent.life.health_fraction} />
        <Meter label="Body condition" value={agent.life.body_condition} />
        <Meter
          label="Development"
          value={agent.life.development}
          tone="violet"
        />
        <div className="inventory-row">
          <span>
            <Icon name="food" size={13} />
            {precise(agent.inventories.food)} food
          </span>
          <span>
            <Icon name="material" size={13} />
            {precise(agent.inventories.materials)} material
          </span>
        </div>
      </section>

      <section className="inspector-section">
        <div className="section-title">
          <h4>Brain & behaviour</h4>
          <span>{titleCase(agent.brain.kind)}</span>
        </div>
        <div className="action-card">
          <span className="action-icon">
            <Icon name="brain" size={16} />
          </span>
          <div>
            <small>Last decision</small>
            <strong>
              {agent.brain.last_action === ""
                ? "No action yet"
                : titleCase(agent.brain.last_action)}
            </strong>
          </div>
          <span className="success-value">
            {percent(agent.brain.last_success)}
          </span>
        </div>
        <div className="culture-grid">
          {Object.entries(agent.culture).map(([name, value]) => (
            <Meter
              key={name}
              label={titleCase(name)}
              value={value}
              tone="violet"
            />
          ))}
        </div>
      </section>

      <section className="inspector-section">
        <div className="section-title">
          <h4>Biological potential</h4>
          <span>
            {percent(agent.biology.genome.heterozygosity)} heterozygosity
          </span>
        </div>
        <div className="trait-grid">
          {traitNames.map((name) => {
            const value = traitValue(agent.biology.traits, name);
            return value === null ? null : (
              <span key={name}>
                <small>{titleCase(name)}</small>
                <strong>{value <= 1 ? percent(value) : precise(value)}</strong>
              </span>
            );
          })}
        </div>
      </section>

      <section className="inspector-section">
        <div className="section-title">
          <h4>Technology</h4>
          <span>
            {agent.technology.knows_seafaring
              ? "Seafaring known"
              : "Land knowledge"}
          </span>
        </div>
        <Meter
          label="Research"
          value={agent.technology.research_progress / researchThreshold}
          tone="gold"
        />
        {agent.technology.vessel_durability > 0 ? (
          <Meter
            label="Vessel durability"
            value={
              agent.technology.vessel_durability /
              maximumVesselDurability
            }
          />
        ) : null}
      </section>

      <section className="inspector-section relationship-section">
        <div className="section-title">
          <h4>Remembered relations</h4>
          <span>{agent.relationships.length} retained</span>
        </div>
        {agent.relationships.length === 0 ? (
          <p className="muted-copy">No current social memories.</p>
        ) : (
          <div className="relationship-list">
            {agent.relationships.slice(0, 4).map((relationship) => (
              <button
                key={relationship.agent_id}
                onClick={() => onSelectAgent(relationship.agent_id)}
                type="button"
              >
                <span className="tiny-avatar">
                  <Icon name="person" size={11} />
                </span>
                <span>
                  <strong>#{relationship.agent_id}</strong>
                  <small>{relationship.encounters} encounters</small>
                </span>
                <span className="trust-value">
                  {percent(relationship.trust)}
                </span>
                <Icon name="chevron" size={13} />
              </button>
            ))}
          </div>
        )}
      </section>
    </aside>
  );
}
