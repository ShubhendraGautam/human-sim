import type { WorldEvent } from "../api/contracts";

/**
 * Turning the engine's event log into something a reader can follow.
 *
 * The engine records what happened in its own vocabulary: a kind and the ids
 * involved. This file is the only place that vocabulary becomes English, and
 * it deliberately adds nothing. `communicate` becomes "spoke with", not "had
 * a conversation about the harvest" — the second is a story the model never
 * told, and putting invented detail beside real records would make the whole
 * feed untrustworthy.
 */

export type EventImportance = "landmark" | "notable" | "routine";

interface EventShape {
  label: string;
  /** Present tense, reads as "<who> <verb> <whom>". */
  verb: string;
  importance: EventImportance;
  /** Whether the second actor is the one the verb lands on. */
  directed: boolean;
}

const SHAPES: Record<string, EventShape> = {
  birth: {
    label: "Birth",
    verb: "was born to",
    importance: "notable",
    directed: true,
  },
  death: {
    label: "Death",
    verb: "died",
    importance: "notable",
    directed: false,
  },
  conception: {
    label: "Conception",
    verb: "conceived with",
    importance: "routine",
    directed: true,
  },
  pregnancy_loss: {
    label: "Pregnancy loss",
    verb: "lost a pregnancy",
    importance: "notable",
    directed: false,
  },
  bond_formed: {
    label: "Pair bond",
    verb: "bonded with",
    importance: "notable",
    directed: true,
  },
  bond_ended_death: {
    label: "Bond ended",
    verb: "was widowed by",
    importance: "notable",
    directed: true,
  },
  bond_ended_separation: {
    label: "Separation",
    verb: "separated from",
    importance: "notable",
    directed: true,
  },
  bond_ended_distrust: {
    label: "Bond soured",
    verb: "broke faith with",
    importance: "notable",
    directed: true,
  },
  communicate: {
    label: "Speech",
    verb: "spoke with",
    importance: "routine",
    directed: true,
  },
  share: {
    label: "Sharing",
    verb: "shared food with",
    importance: "routine",
    directed: true,
  },
  care: {
    label: "Care",
    verb: "cared for",
    importance: "routine",
    directed: true,
  },
  teach: {
    label: "Teaching",
    verb: "taught something to",
    importance: "landmark",
    directed: true,
  },
  teach_policy: {
    label: "Policy teaching",
    verb: "passed a policy to",
    importance: "landmark",
    directed: true,
  },
  invent: {
    label: "Invention",
    verb: "worked something out",
    importance: "landmark",
    directed: false,
  },
  hunt_killed: {
    label: "Hunt",
    verb: "brought down an animal",
    importance: "notable",
    directed: false,
  },
  hunt_failed: {
    label: "Hunt failed",
    verb: "lost an animal",
    importance: "routine",
    directed: false,
  },
  build_vessel: {
    label: "Vessel built",
    verb: "built a vessel",
    importance: "landmark",
    directed: false,
  },
  landfall: {
    label: "Landfall",
    verb: "reached the far shore",
    importance: "landmark",
    directed: false,
  },
  drowned: {
    label: "Lost at sea",
    verb: "was lost at sea",
    importance: "landmark",
    directed: false,
  },
  wrecked_ashore: {
    label: "Wrecked ashore",
    verb: "made shore from a failing hull",
    importance: "landmark",
    directed: false,
  },
  infection: {
    label: "Infection",
    verb: "was infected",
    importance: "routine",
    directed: false,
  },
  became_infectious: {
    label: "Turned infectious",
    verb: "became infectious",
    importance: "routine",
    directed: false,
  },
  infection_recovery: {
    label: "Recovery",
    verb: "recovered",
    importance: "routine",
    directed: false,
  },
  vertical_infection: {
    label: "Infected at birth",
    verb: "was born infected",
    importance: "notable",
    directed: false,
  },
};

const UNKNOWN: EventShape = {
  label: "Event",
  verb: "was involved in something",
  importance: "routine",
  directed: false,
};

export function eventShape(kind: string): EventShape {
  return SHAPES[kind] ?? UNKNOWN;
}

export function eventImportance(kind: string): EventImportance {
  return eventShape(kind).importance;
}

/** The kinds a reader can filter down to, in the order they are offered. */
export const IMPORTANCE_ORDER: EventImportance[] = [
  "landmark",
  "notable",
  "routine",
];

export function describeEvent(event: WorldEvent): string {
  const shape = eventShape(event.kind);
  const [actor, target] = event.actors;
  const subject = actor === undefined ? "Someone" : `#${actor}`;
  // When there is an utterance, show the word itself. This is the one place
  // the feed quotes rather than summarises, because the sounds are the whole
  // point: they were invented by someone and copied by everyone else, and no
  // two runs produce the same ones.
  if (event.said !== undefined && event.said !== "") {
    const gloss = event.about === undefined ? "" : ` (${event.about})`;
    const target_text = target === undefined ? "" : ` to #${target}`;
    return event.coined === true
      ? `${subject} coined \u201c${event.said}\u201d${gloss}${target_text}`
      : `${subject} said \u201c${event.said}\u201d${gloss}${target_text}`;
  }
  if (shape.directed && target !== undefined) {
    return `${subject} ${shape.verb} #${target}`;
  }
  return `${subject} ${shape.verb}`;
}

/**
 * Collapse a burst of identical routine events into one line.
 *
 * Forty conversations in one tick is a true record and a useless notification
 * list. Grouping keeps the count — which is the informative part — without
 * burying a landfall under it. Landmarks are never grouped, because each one
 * is worth its own line.
 */
export interface EventGroup {
  key: string;
  kind: string;
  tick: number;
  year: number;
  count: number;
  sample: WorldEvent;
  importance: EventImportance;
}

export function groupEvents(events: WorldEvent[]): EventGroup[] {
  const groups: EventGroup[] = [];
  const index = new Map<string, EventGroup>();
  for (const event of events) {
    const importance = eventImportance(event.kind);
    if (importance === "landmark") {
      groups.push({
        key: `${event.tick}-${event.kind}-${event.actors.join("-")}`,
        kind: event.kind,
        tick: event.tick,
        year: event.year,
        count: 1,
        sample: event,
        importance,
      });
      continue;
    }
    const key = `${event.tick}-${event.kind}`;
    const existing = index.get(key);
    if (existing === undefined) {
      const group: EventGroup = {
        key,
        kind: event.kind,
        tick: event.tick,
        year: event.year,
        count: 1,
        sample: event,
        importance,
      };
      index.set(key, group);
      groups.push(group);
    } else {
      existing.count += 1;
    }
  }
  return groups;
}
