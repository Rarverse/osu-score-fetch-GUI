import { t } from "./i18n";

export function gradeLabel(rank: string): string {
  return rank === "SSH" ? "SS" : rank === "SH" ? "S" : rank;
}

export function gradeTitle(rank: string): string {
  return rank === "SSH" || rank === "SH"
    ? t("silverGrade", { grade: gradeLabel(rank) })
    : gradeLabel(rank);
}

export function starBackground(rating: number | null): string | undefined {
  // Keep the official purple/blue/black colours readable on a dark UI.
  return rating !== null && Number.isFinite(rating) && rating >= 6.5
    ? "#f1eff7"
    : undefined;
}

// Official osu-web colour stops and gamma, independently interpolated here:
// https://github.com/ppy/osu-web/blob/master/resources/js/utils/beatmap-helper.ts
const difficultyStops: [number, string][] = [
  [0.1, "#4290fb"],
  [1.25, "#4fc0ff"],
  [2, "#4fffd5"],
  [2.5, "#7cff4f"],
  [3.3, "#f6f05c"],
  [4.2, "#ff8068"],
  [4.9, "#ff4e6f"],
  [5.8, "#c645b8"],
  [6.7, "#6563de"],
  [7.7, "#18158e"],
  [9, "#000000"],
];

const difficultyChannels = difficultyStops.map(([, color]) =>
  [1, 3, 5].map((offset) =>
    Number.parseInt(color.slice(offset, offset + 2), 16) ** 2.2,
  ),
);

export function starColor(rating: number | null): string {
  if (rating === null || !Number.isFinite(rating) || rating < 0.1)
    return "#aaaaaa";
  const stops = difficultyStops;
  const upper = stops.findIndex(([value]) => rating <= value);
  if (upper === 0) return stops[0][1];
  if (upper < 0) return stops[stops.length - 1][1];
  const [low] = stops[upper - 1];
  const [high] = stops[upper];
  const ratio = (rating - low) / (high - low);
  const channels = difficultyChannels[upper - 1].map((a, index) => {
    const b = difficultyChannels[upper][index];
    return Math.round((a * (1 - ratio) + b * ratio) ** (1 / 2.2))
      .toString(16)
      .padStart(2, "0");
  });
  return `#${channels.join("")}`;
}
