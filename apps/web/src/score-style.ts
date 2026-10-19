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
  // The official dark blue/purple spectrum needs a light backing on a dark UI.
  return rating !== null && rating >= 6.5 && rating < 9 ? "#f1eff7" : undefined;
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
const highStarTextStops: [number, string][] = [
  [9, "#f6f05c"],
  [9.9, "#ff8068"],
  [10.6, "#ff4e6f"],
  [11.5, "#c645b8"],
  [12.4, "#6563de"],
];

export function starColor(rating: number | null): string {
  if (rating === null || !Number.isFinite(rating) || rating < 0.1)
    return "#aaaaaa";
  // 9★+ badges are black on osu-web; use their official foreground on our dark UI.
  const stops = rating >= 9 ? highStarTextStops : difficultyStops;
  const upper = stops.findIndex(([value]) => rating <= value);
  if (upper === 0) return stops[0][1];
  if (upper < 0) return stops[stops.length - 1][1];
  const [low, start] = stops[upper - 1];
  const [high, end] = stops[upper];
  const ratio = (rating - low) / (high - low);
  const channels = [1, 3, 5].map((offset) => {
    const a = Number.parseInt(start.slice(offset, offset + 2), 16);
    const b = Number.parseInt(end.slice(offset, offset + 2), 16);
    return Math.round((a ** 2.2 * (1 - ratio) + b ** 2.2 * ratio) ** (1 / 2.2))
      .toString(16)
      .padStart(2, "0");
  });
  return `#${channels.join("")}`;
}
