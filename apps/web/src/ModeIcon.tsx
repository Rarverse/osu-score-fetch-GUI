import type { ReactNode } from "react";
import type { Ruleset } from "./types";

export default function ModeIcon({ mode }: { mode: Ruleset }) {
  return (
    <svg className="mode-icon" viewBox="0 0 24 24" aria-hidden="true">
      {shape(mode)}
    </svg>
  );
}

function shape(mode: Ruleset): ReactNode {
  switch (mode) {
    case "osu":
      return (
        <>
          <circle
            cx="12"
            cy="12"
            r="7.25"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          />
          <circle cx="12" cy="12" r="2.2" fill="currentColor" />
        </>
      );
    case "taiko":
      return (
        <>
          <ellipse
            cx="12"
            cy="13.5"
            rx="8"
            ry="4.2"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          />
          <ellipse cx="12" cy="11" rx="8" ry="3" fill="currentColor" />
        </>
      );
    case "fruits":
      return (
        <>
          <circle cx="12" cy="13.5" r="5.5" fill="currentColor" />
          <path
            d="M12 8.2c1.6-2.4 4.4-3 6.2-2.2"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
          />
        </>
      );
    case "mania":
      return (
        <>
          <rect
            x="3"
            y="7"
            width="3.2"
            height="12"
            rx="1"
            fill="currentColor"
          />
          <rect
            x="8"
            y="4"
            width="3.2"
            height="15"
            rx="1"
            fill="currentColor"
          />
          <rect
            x="13"
            y="8"
            width="3.2"
            height="11"
            rx="1"
            fill="currentColor"
          />
          <rect
            x="18"
            y="5.5"
            width="3.2"
            height="13.5"
            rx="1"
            fill="currentColor"
          />
        </>
      );
    default: {
      const unexpected: never = mode;
      throw new Error(`Unknown mode: ${String(unexpected)}`);
    }
  }
}
