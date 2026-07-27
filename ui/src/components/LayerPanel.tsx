import type { RunFrame, RunManifest } from "../api/contracts";
import { compact, percent, titleCase } from "../lib/format";
import { Icon, type IconName } from "./Icon";
import type {
  AgentColorMode,
  CanvasLayerSettings,
} from "./WorldCanvas";

interface LayerPanelProps {
  manifest: RunManifest;
  frame: RunFrame;
  layers: CanvasLayerSettings;
  onToggle: (
    layer: Exclude<keyof CanvasLayerSettings, "colorMode">,
    visible: boolean,
  ) => void;
  onColorMode: (mode: AgentColorMode) => void;
}

interface LayerRowProps {
  checked: boolean;
  icon: IconName;
  label: string;
  meta?: string;
  onChange: (checked: boolean) => void;
}

function LayerRow({
  checked,
  icon,
  label,
  meta,
  onChange,
}: LayerRowProps) {
  return (
    <label className="layer-row">
      <span className={`layer-icon layer-icon-${icon}`}>
        <Icon name={icon} size={15} />
      </span>
      <span className="layer-copy">
        <span>{label}</span>
        {meta === undefined ? null : <small>{meta}</small>}
      </span>
      <input
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        type="checkbox"
      />
      <span className="toggle" aria-hidden="true" />
    </label>
  );
}

function ColorLegend({
  manifest,
  mode,
}: {
  manifest: RunManifest;
  mode: AgentColorMode;
}) {
  const entries: [string, string][] =
    mode === "country"
      ? manifest.scenario.countries.map((country, index) => [
          ["#f5bd68", "#65c6c2", "#cf8dff", "#8fcf78"][index % 4] ??
            "#d8ded8",
          country.name,
        ])
      : mode === "brain"
        ? [
            ["#89a9ff", "Deliberative"],
            ["#f5bd68", "Exploratory"],
            ["#b5c3b5", "Habitual"],
            ["#d08ce8", "Social"],
          ]
        : mode === "seafaring"
          ? [
              ["#63c9f0", "Holds a vessel"],
              ["#3f7f96", "Knows seafaring"],
              ["#6f7a72", "Neither"],
            ]
          : [
              ["#f06f63", "Low"],
              ["#f2bd69", "Moderate"],
              ["#a8df9b", "High"],
            ];
  return (
    <div className="color-legend" aria-label={`${titleCase(mode)} legend`}>
      {entries.map(([color, label]) => (
        <span key={label}>
          <i style={{ backgroundColor: color }} />
          {label}
        </span>
      ))}
    </div>
  );
}

export function LayerPanel({
  manifest,
  frame,
  layers,
  onToggle,
  onColorMode,
}: LayerPanelProps) {
  const infectious = frame.metrics.disease_population.infectious ?? 0;
  const foodFraction = frame.metrics.resource_fraction;
  const materialFraction =
    frame.metrics.total_materials /
    Math.max(
      1,
      manifest.world.material_capacity.reduce(
        (sum, value) => sum + value,
        0,
      ),
    );

  return (
    <aside className="side-panel layer-panel" aria-label="Map layers">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Observe</span>
          <h2>World layers</h2>
        </div>
        <Icon name="layers" size={18} />
      </div>

      <div className="layer-list">
        <LayerRow
          checked={layers.terrain}
          icon="globe"
          label="Terrain"
          meta={`${manifest.world.width} × ${manifest.world.height} cells`}
          onChange={(checked) => onToggle("terrain", checked)}
        />
        <LayerRow
          checked={layers.countries}
          icon="layers"
          label="Countries"
          meta={`${manifest.scenario.countries.length} founder regions`}
          onChange={(checked) => onToggle("countries", checked)}
        />
        <LayerRow
          checked={layers.food}
          icon="food"
          label="Food"
          meta={`${percent(foodFraction)} capacity`}
          onChange={(checked) => onToggle("food", checked)}
        />
        <LayerRow
          checked={layers.materials}
          icon="material"
          label="Materials"
          meta={`${percent(materialFraction)} remaining`}
          onChange={(checked) => onToggle("materials", checked)}
        />
        <LayerRow
          checked={layers.disease}
          icon="activity"
          label="Disease"
          meta={`${compact(infectious)} infectious`}
          onChange={(checked) => onToggle("disease", checked)}
        />
        <LayerRow
          checked={layers.agents}
          icon="users"
          label="People"
          meta={`${compact(frame.metrics.population)} living`}
          onChange={(checked) => onToggle("agents", checked)}
        />
        <LayerRow
          checked={layers.vessels}
          icon="waves"
          label="Vessels"
          meta={`${compact(frame.metrics.vessels)} afloat`}
          onChange={(checked) => onToggle("vessels", checked)}
        />
      </div>

      <div className="panel-section color-section">
        <span className="field-label">Color people by</span>
        <div className="segmented-control segmented-full">
          {(
            ["country", "brain", "health", "seafaring"] as
              AgentColorMode[]
          ).map(
            (mode) => (
              <button
                aria-pressed={layers.colorMode === mode}
                className={layers.colorMode === mode ? "active" : ""}
                key={mode}
                onClick={() => onColorMode(mode)}
                type="button"
              >
                {titleCase(mode)}
              </button>
            ),
          )}
        </div>
        <ColorLegend manifest={manifest} mode={layers.colorMode} />
      </div>

      <div className="panel-note">
        <Icon name="spark" size={14} />
        <p>
          Layers are observations only. They never change agent decisions.
        </p>
      </div>
    </aside>
  );
}
