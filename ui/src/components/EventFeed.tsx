import { useMemo, useState } from "react";

import type { WorldEvent } from "../api/contracts";
import {
  IMPORTANCE_ORDER,
  describeEvent,
  eventShape,
  groupEvents,
  type EventImportance,
} from "../lib/events";
import { Icon } from "./Icon";

interface EventFeedPanelProps {
  events: WorldEvent[];
  dropped: boolean;
  year: number;
  onSelectAgent: (agentId: string | null) => void;
}

const FILTER_LABELS: Record<EventImportance, string> = {
  landmark: "Landmarks",
  notable: "Notable",
  routine: "Everything",
};

/**
 * Landmarks are things that happen a handful of times in a run — a first
 * crossing, a vessel, a drowning. Notable is the scale of one life. Routine
 * is every conversation and meal, which is most of the log by volume and the
 * least informative per line.
 */
const FILTER_INCLUDES: Record<EventImportance, EventImportance[]> = {
  landmark: ["landmark"],
  notable: ["landmark", "notable"],
  routine: ["landmark", "notable", "routine"],
};

export function EventFeedPanel({
  events,
  dropped,
  year,
  onSelectAgent,
}: EventFeedPanelProps) {
  const [filter, setFilter] = useState<EventImportance>("notable");

  const groups = useMemo(() => {
    const allowed = new Set(FILTER_INCLUDES[filter]);
    return groupEvents(
      events.filter((event) =>
        allowed.has(eventShape(event.kind).importance),
      ),
    ).slice(0, 60);
  }, [events, filter]);

  const landmarks = useMemo(
    () =>
      events.filter(
        (event) => eventShape(event.kind).importance === "landmark",
      ).length,
    [events],
  );

  return (
    <aside className="side-panel event-panel" aria-label="Recent events">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Notifications</span>
          <h2>What just happened</h2>
        </div>
        <span className="event-count" aria-label={`${landmarks} landmarks`}>
          {landmarks}
        </span>
      </div>

      <div className="segmented-control segmented-full">
        {IMPORTANCE_ORDER.map((level) => (
          <button
            aria-pressed={filter === level}
            className={filter === level ? "active" : ""}
            key={level}
            onClick={() => setFilter(level)}
            type="button"
          >
            {FILTER_LABELS[level]}
          </button>
        ))}
      </div>

      {dropped ? (
        <p className="event-gap" role="status">
          <Icon name="activity" size={13} />
          The run moved faster than this list could follow. Events between
          then and now happened but were not kept.
        </p>
      ) : null}

      <ol className="event-list">
        {groups.length === 0 ? (
          <li className="event-empty">
            Nothing at this level yet — year {year.toFixed(1)}.
          </li>
        ) : (
          groups.map((group) => {
            const shape = eventShape(group.kind);
            const actor = group.sample.actors[0];
            return (
              <li className={`event-row event-${group.importance}`}
                key={group.key}
              >
                <span className="event-year">
                  {group.year.toFixed(1)}
                </span>
                <span className="event-body">
                  <span className="event-label">{shape.label}</span>
                  {group.count > 1 ? (
                    <span className="event-text">
                      {group.count} of them this tick
                    </span>
                  ) : (
                    <button
                      className="event-text event-link"
                      disabled={actor === undefined}
                      onClick={() =>
                        onSelectAgent(actor === undefined ? null : actor)
                      }
                      type="button"
                    >
                      {describeEvent(group.sample)}
                    </button>
                  )}
                </span>
              </li>
            );
          })
        )}
      </ol>

      <div className="panel-note">
        <Icon name="spark" size={14} />
        <p>
          Written by the engine as things happen. Wording is a translation of
          the record, never an embellishment of it.
        </p>
      </div>
    </aside>
  );
}
