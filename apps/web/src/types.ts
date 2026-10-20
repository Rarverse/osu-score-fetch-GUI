export type Ruleset = "osu" | "taiko" | "fruits" | "mania";
export type QueryMode = Ruleset | "auto";

export const modeLabels: Record<Ruleset, string> = {
  osu: "osu!",
  taiko: "osu!taiko",
  fruits: "osu!catch",
  mania: "osu!mania",
};

export interface Player {
  user_id: number;
  username: string;
  country: string;
  avatar_url: string;
  pp: number | null;
  global_rank: number | null;
  hit_accuracy: number | null;
  play_time?: number | null;
}

export interface Score {
  score_id: number | null;
  beatmap_id: number | null;
  beatmap_title: string;
  artist: string;
  version: string;
  cover_url: string | null;
  star_rating: number | null;
  accuracy: number;
  pp: number | null;
  rank: string;
  mods: string[];
  max_combo: number;
  played_at: string | null;
}

export interface ScoresResponse {
  player: Player;
  mode: Ruleset;
  type: "best";
  scores: Score[];
  fetched_at: string;
}

export interface ErrorResponse {
  error: { code: string; message: string };
}
