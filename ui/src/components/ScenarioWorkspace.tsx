import { useState } from "react";

import type { SimulationClient } from "../api/client";
import type {
  ConfigValue,
  CountryContract,
  CreateRunRequest,
} from "../api/contracts";
import {
  cloneRunRequest,
  SCENARIO_PRESETS,
} from "../lib/scenarios";
import { Icon } from "./Icon";

interface ScenarioWorkspaceProps {
  baseRequest: CreateRunRequest;
  client: SimulationClient;
  onLaunch(request: CreateRunRequest): Promise<boolean>;
}

function numberValue(value: ConfigValue | undefined, fallback: number): number {
  return typeof value === "number" ? value : fallback;
}

function NumberField({
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange(value: number): void;
}) {
  return (
    <label className="workspace-field">
      <span>{label}</span>
      <input
        max={max}
        min={min}
        onChange={(event) => onChange(Number(event.target.value))}
        step={step}
        type="number"
        value={value}
      />
    </label>
  );
}

export function ScenarioWorkspace({
  baseRequest,
  client,
  onLaunch,
}: ScenarioWorkspaceProps) {
  const [draft, setDraft] = useState<CreateRunRequest>(() =>
    cloneRunRequest(baseRequest),
  );
  const [status, setStatus] = useState<
    "editing" | "validating" | "valid" | "launching"
  >("editing");
  const [message, setMessage] = useState<string | null>(null);
  const config = draft.config ?? {};
  const scenario = draft.scenario ?? { countries: [], seas: [] };
  const serviceAvailable = client.source === "service";

  const replace = (request: CreateRunRequest) => {
    setDraft(cloneRunRequest(request));
    setStatus("editing");
    setMessage(null);
  };

  const updateConfig = (name: string, value: ConfigValue) => {
    setDraft((current) => ({
      ...current,
      config: { ...current.config, [name]: value },
    }));
    setStatus("editing");
    setMessage(null);
  };

  const updateCountry = (
    index: number,
    update: Record<string, ConfigValue>,
  ) => {
    setDraft((current) => {
      const currentScenario = current.scenario ?? {
        countries: [],
        seas: [],
      };
      return {
        ...current,
        scenario: {
          ...currentScenario,
          countries: currentScenario.countries.map((country, countryIndex) =>
            countryIndex === index
              ? ({ ...country, ...update } as CountryContract)
              : country,
          ),
        },
      };
    });
    setStatus("editing");
    setMessage(null);
  };

  const validate = async (): Promise<CreateRunRequest | null> => {
    if (!serviceAvailable) {
      setMessage("Connect the engine service to validate custom worlds.");
      return null;
    }
    setStatus("validating");
    setMessage(null);
    try {
      const normalized = await client.validateScenario({
        ...(draft.config === undefined ? {} : { config: draft.config }),
        ...(draft.scenario === undefined ? {} : { scenario: draft.scenario }),
      });
      const request = {
        seed: Math.trunc(draft.seed),
        config: normalized.config,
        scenario: normalized.scenario,
      };
      setDraft(request);
      setStatus("valid");
      setMessage("Engine validation passed. Starting conditions are coherent.");
      return request;
    } catch (error: unknown) {
      setStatus("editing");
      setMessage(
        error instanceof Error ? error.message : "The scenario is not valid.",
      );
      return null;
    }
  };

  const launch = async () => {
    const request = status === "valid" ? draft : await validate();
    if (request === null) {
      return;
    }
    setStatus("launching");
    const opened = await onLaunch(request);
    if (!opened) {
      setStatus("valid");
      setMessage("The scenario passed validation, but its run did not open.");
    }
  };

  return (
    <main className="workspace scenario-workspace">
      <header className="workspace-hero">
        <div>
          <span className="eyebrow">Starting conditions</span>
          <h1>Scenario studio</h1>
          <p>
            Shape the world people inherit. The engine validates every draft
            before it becomes a run.
          </p>
        </div>
        <div className="workspace-hero-mark">
          <Icon name="globe" size={25} />
        </div>
      </header>

      {!serviceAvailable ? (
        <div className="workspace-callout">
          <Icon name="spark" size={16} />
          The synthetic demo can preview this editor, but only the engine
          service can validate and launch a custom scenario.
        </div>
      ) : null}

      <section className="preset-section" aria-labelledby="preset-title">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Quick starts</span>
            <h2 id="preset-title">Choose a world, then make it yours</h2>
          </div>
        </div>
        <div className="preset-grid">
          {SCENARIO_PRESETS.map((preset) => (
            <button
              className="preset-card"
              key={preset.id}
              onClick={() => replace(preset.request)}
              type="button"
            >
              <span className="preset-icon">
                <Icon
                  name={preset.id === "twin-shores" ? "waves" : "globe"}
                  size={18}
                />
              </span>
              <strong>{preset.name}</strong>
              <span>{preset.summary}</span>
            </button>
          ))}
        </div>
      </section>

      <div className="workspace-grid">
        <section className="workspace-panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">World rules</span>
              <h2>Canvas and clock</h2>
            </div>
          </div>
          <div className="field-grid">
            <NumberField
              label="Seed"
              onChange={(seed) =>
                setDraft((current) => ({ ...current, seed }))
              }
              step={1}
              value={draft.seed}
            />
            <NumberField
              label="Width"
              min={8}
              onChange={(value) => updateConfig("width", value)}
              value={numberValue(config.width, 56)}
            />
            <NumberField
              label="Height"
              min={8}
              onChange={(value) => updateConfig("height", value)}
              value={numberValue(config.height, 30)}
            />
            <NumberField
              label="Ticks / year"
              min={1}
              onChange={(value) => updateConfig("ticks_per_year", value)}
              value={numberValue(config.ticks_per_year, 12)}
            />
          </div>
          <label className="workspace-check">
            <input
              checked={config.wrap_world === true}
              onChange={(event) =>
                updateConfig("wrap_world", event.target.checked)
              }
              type="checkbox"
            />
            <span>
              <strong>Wrap world edges</strong>
              <small>People can cross from one edge to the opposite.</small>
            </span>
          </label>
        </section>

        <section className="workspace-panel span-two">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Founders</span>
              <h2>Countries and cultures</h2>
            </div>
            <button
              className="quiet-button"
              onClick={() => {
                const width = numberValue(config.width, 56);
                const height = numberValue(config.height, 30);
                const id =
                  Math.max(-1, ...scenario.countries.map((country) => country.id)) +
                  1;
                setDraft((current) => ({
                  ...current,
                  scenario: {
                    ...(current.scenario ?? { seas: [] }),
                    countries: [
                      ...(current.scenario?.countries ?? []),
                      {
                        id,
                        name: `Country ${id + 1}`,
                        region: [0, 0, width, height],
                        population: 60,
                        religion: `belief-${id + 1}`,
                        generosity_mean: 0.5,
                        exploration_mean: 0.5,
                        curiosity_mean: 0.5,
                        conformity_mean: 0.5,
                        food_multiplier: 1,
                        material_multiplier: 1,
                      },
                    ],
                  },
                }));
                setStatus("editing");
              }}
              type="button"
            >
              <Icon name="plus" size={14} />
              Add country
            </button>
          </div>
          <div className="country-editor-list">
            {scenario.countries.map((country, index) => (
              <article className="country-editor" key={country.id}>
                <div className="country-editor-heading">
                  <span className="country-number">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <label className="workspace-field grow">
                    <span>Name</span>
                    <input
                      onChange={(event) =>
                        updateCountry(index, { name: event.target.value })
                      }
                      type="text"
                      value={country.name}
                    />
                  </label>
                  <button
                    aria-label={`Remove ${country.name}`}
                    className="icon-button"
                    disabled={scenario.countries.length <= 1}
                    onClick={() => {
                      setDraft((current) => ({
                        ...current,
                        scenario: {
                          ...(current.scenario ?? { seas: [] }),
                          countries:
                            current.scenario?.countries.filter(
                              (_, countryIndex) => countryIndex !== index,
                            ) ?? [],
                        },
                      }));
                      setStatus("editing");
                    }}
                    type="button"
                  >
                    <Icon name="close" size={15} />
                  </button>
                </div>
                <div className="country-field-grid">
                  <NumberField
                    label="Population"
                    min={0}
                    onChange={(population) =>
                      updateCountry(index, { population })
                    }
                    value={country.population}
                  />
                  <label className="workspace-field">
                    <span>Belief</span>
                    <input
                      onChange={(event) =>
                        updateCountry(index, { religion: event.target.value })
                      }
                      type="text"
                      value={country.religion}
                    />
                  </label>
                  {(["X", "Y", "Width", "Height"] as const).map(
                    (label, regionIndex) => (
                      <NumberField
                        key={label}
                        label={`Region ${label}`}
                        min={0}
                        onChange={(value) => {
                          const region = [...country.region] as [
                            number,
                            number,
                            number,
                            number,
                          ];
                          region[regionIndex] = value;
                          updateCountry(index, { region });
                        }}
                        value={country.region[regionIndex] ?? 0}
                      />
                    ),
                  )}
                  {([
                    ["Food ×", "food_multiplier"],
                    ["Material ×", "material_multiplier"],
                    ["Curiosity", "curiosity_mean"],
                    ["Exploration", "exploration_mean"],
                    ["Generosity", "generosity_mean"],
                    ["Conformity", "conformity_mean"],
                  ] as const).map(([label, key]) => (
                    <NumberField
                      key={key}
                      label={label}
                      min={0}
                      onChange={(value) =>
                        updateCountry(index, { [key]: value })
                      }
                      step={0.05}
                      value={numberValue(country[key], 1)}
                    />
                  ))}
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="workspace-panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Geography</span>
              <h2>Sea barriers</h2>
            </div>
            <button
              className="quiet-button"
              onClick={() => {
                setDraft((current) => ({
                  ...current,
                  scenario: {
                    ...(current.scenario ?? { countries: [] }),
                    seas: [...(current.scenario?.seas ?? []), [0, 0, 4, 4]],
                  },
                }));
                setStatus("editing");
              }}
              type="button"
            >
              <Icon name="plus" size={14} />
              Add sea
            </button>
          </div>
          <p className="panel-copy">
            Rectangles are combined into coastlines. Overlap several to cut
            bays and channels.
          </p>
          <div className="sea-list">
            {scenario.seas.length === 0 ? (
              <span className="empty-state">No sea barriers in this world.</span>
            ) : (
              scenario.seas.map((sea, seaIndex) => (
                <div className="sea-row" key={`${seaIndex}-${sea.join("-")}`}>
                  {(["X", "Y", "W", "H"] as const).map((label, valueIndex) => (
                    <NumberField
                      key={label}
                      label={label}
                      min={0}
                      onChange={(value) => {
                        setDraft((current) => {
                          const seas = [...(current.scenario?.seas ?? [])];
                          const rectangle = [...(seas[seaIndex] ?? sea)] as [
                            number,
                            number,
                            number,
                            number,
                          ];
                          rectangle[valueIndex] = value;
                          seas[seaIndex] = rectangle;
                          return {
                            ...current,
                            scenario: {
                              ...(current.scenario ?? { countries: [] }),
                              seas,
                            },
                          };
                        });
                        setStatus("editing");
                      }}
                      value={sea[valueIndex] ?? 0}
                    />
                  ))}
                  <button
                    aria-label={`Remove sea ${seaIndex + 1}`}
                    className="icon-button"
                    onClick={() => {
                      setDraft((current) => ({
                        ...current,
                        scenario: {
                          ...(current.scenario ?? { countries: [] }),
                          seas:
                            current.scenario?.seas.filter(
                              (_, index) => index !== seaIndex,
                            ) ?? [],
                        },
                      }));
                      setStatus("editing");
                    }}
                    type="button"
                  >
                    <Icon name="close" size={14} />
                  </button>
                </div>
              ))
            )}
          </div>
        </section>
      </div>

      <div className="workspace-action-bar">
        <div className={`validation-message status-${status}`}>
          <Icon
            name={status === "valid" ? "spark" : "activity"}
            size={15}
          />
          <span>
            {message ??
              "Edits affect starting conditions only; agent behaviour remains emergent."}
          </span>
        </div>
        <button
          className="secondary-action"
          disabled={!serviceAvailable || status === "validating" || status === "launching"}
          onClick={() => void validate()}
          type="button"
        >
          Validate
        </button>
        <button
          className="primary-action"
          disabled={!serviceAvailable || status === "validating" || status === "launching"}
          onClick={() => void launch()}
          type="button"
        >
          <Icon name="play" size={15} />
          {status === "launching" ? "Opening run…" : "Create run"}
        </button>
      </div>
    </main>
  );
}
