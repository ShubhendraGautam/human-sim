import type { ReactNode, SVGProps } from "react";

export type IconName =
  | "activity"
  | "brain"
  | "chevron"
  | "close"
  | "download"
  | "food"
  | "globe"
  | "health"
  | "layers"
  | "material"
  | "minus"
  | "pause"
  | "person"
  | "play"
  | "plus"
  | "reset"
  | "seed"
  | "spark"
  | "step"
  | "users"
  | "waves";

interface IconProps extends SVGProps<SVGSVGElement> {
  name: IconName;
  size?: number;
}

export function Icon({
  name,
  size = 18,
  className,
  ...props
}: IconProps) {
  const paths: Record<IconName, ReactNode> = {
    activity: (
      <path d="M3 12h4l2.2-6 4.1 12 2.2-6H21" />
    ),
    brain: (
      <>
        <path d="M9.5 4.5A3.5 3.5 0 0 0 6 8v.4A3.8 3.8 0 0 0 4 12a3.8 3.8 0 0 0 2 3.6v.4a3.5 3.5 0 0 0 3.5 3.5c1 0 1.8-.4 2.5-1V5.5c-.7-.7-1.5-1-2.5-1Z" />
        <path d="M14.5 4.5A3.5 3.5 0 0 1 18 8v.4a3.8 3.8 0 0 1 2 3.6 3.8 3.8 0 0 1-2 3.6v.4a3.5 3.5 0 0 1-3.5 3.5c-1 0-1.8-.4-2.5-1V5.5c.7-.7 1.5-1 2.5-1Z" />
        <path d="M8 9.5c1.7 0 3 1.3 3 3M16 14.5c-1.7 0-3-1.3-3-3" />
      </>
    ),
    chevron: <path d="m9 18 6-6-6-6" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    download: (
      <>
        <path d="M12 3v12m0 0 4-4m-4 4-4-4" />
        <path d="M5 19h14" />
      </>
    ),
    food: (
      <>
        <path d="M5 21V10m0-7v4c0 1.7 1.3 3 3 3s3-1.3 3-3V3M8 3v18" />
        <path d="M16 21v-8c0-1.7 1.3-3 3-3V3c-3 1.5-4 4-4 7v3h4" />
      </>
    ),
    globe: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18M12 3c2.3 2.5 3.5 5.5 3.5 9S14.3 18.5 12 21c-2.3-2.5-3.5-5.5-3.5-9S9.7 5.5 12 3Z" />
      </>
    ),
    health: (
      <path d="M20.4 5.6a5.4 5.4 0 0 0-7.6 0L12 6.4l-.8-.8a5.4 5.4 0 0 0-7.6 7.6L12 21l8.4-7.8a5.4 5.4 0 0 0 0-7.6Z" />
    ),
    layers: (
      <>
        <path d="m12 3 9 5-9 5-9-5 9-5Z" />
        <path d="m3 12 9 5 9-5M3 16l9 5 9-5" />
      </>
    ),
    material: (
      <>
        <path d="m12 2 8 5v10l-8 5-8-5V7l8-5Z" />
        <path d="m4 7 8 5 8-5M12 12v10" />
      </>
    ),
    minus: <path d="M5 12h14" />,
    pause: (
      <>
        <path d="M9 5v14" />
        <path d="M15 5v14" />
      </>
    ),
    person: (
      <>
        <circle cx="12" cy="8" r="4" />
        <path d="M4.5 21a7.5 7.5 0 0 1 15 0" />
      </>
    ),
    play: <path d="m8 5 11 7-11 7V5Z" />,
    plus: <path d="M12 5v14M5 12h14" />,
    reset: (
      <>
        <path d="M4 4v6h6" />
        <path d="M5.4 15a8 8 0 1 0 .5-7.2L4 10" />
      </>
    ),
    seed: (
      <>
        <path d="M12 21V10" />
        <path d="M12 14c-4.5 0-7-2.3-7-6 4.5 0 7 2.3 7 6ZM12 11c4.5 0 7-2.3 7-6-4.5 0-7 2.3-7 6Z" />
      </>
    ),
    spark: (
      <path d="m12 3 1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5L12 3Zm7 13 .7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16Z" />
    ),
    step: (
      <>
        <path d="m6 5 9 7-9 7V5Z" />
        <path d="M18 5v14" />
      </>
    ),
    users: (
      <>
        <circle cx="9" cy="8" r="4" />
        <path d="M2 21a7 7 0 0 1 14 0M16 5.2a4 4 0 0 1 0 7.6M22 21a7 7 0 0 0-5-6.7" />
      </>
    ),
    waves: (
      <>
        <path d="M2 7c2.5 2 4.5 2 7 0s4.5-2 7 0 4.5 2 6 0" />
        <path d="M2 12c2.5 2 4.5 2 7 0s4.5-2 7 0 4.5 2 6 0" />
        <path d="M2 17c2.5 2 4.5 2 7 0s4.5-2 7 0 4.5 2 6 0" />
      </>
    ),
  };

  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.7"
      {...props}
    >
      {paths[name]}
    </svg>
  );
}
