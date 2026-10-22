import { locale, t } from "./i18n";
import { imageUrl } from "./images";
import { gradeLabel, starBackground, starColor } from "./score-style";
import { modeLabels, type ScoresResponse } from "./types";

const rankColors: Record<string, string> = {
  SS: "#e8cf84",
  S: "#e8cf84",
  SSH: "#d2dfe6",
  SH: "#d2dfe6",
  A: "#9fbea3",
  B: "#94b0da",
  C: "#c9a0dc",
  D: "#e7a06c",
  F: "#e7808c",
};

export interface ExportProgress {
  stage: "images" | "rendering";
  completed: number;
  total: number;
}

// Same-origin cached artwork keeps the canvas exportable without upstream CORS.
function loadImage(url: string | null): Promise<HTMLImageElement | null> {
  if (!url) return Promise.resolve(null);
  return new Promise((resolve) => {
    const image = new Image();
    const finish = (loaded: boolean) => {
      clearTimeout(timer);
      image.onload = null;
      image.onerror = null;
      // Missing or unavailable artwork must not prevent exporting the scores.
      resolve(loaded ? image : null);
    };
    // Allow for server-side pacing and reuse the page's same-origin image cache.
    const timer = setTimeout(() => finish(false), 90_000);
    image.onload = () => finish(true);
    image.onerror = () => finish(false);
    image.src = imageUrl(url);
  });
}

export async function renderBestScores(
  data: ScoresResponse,
  limit: number,
  onProgress?: (progress: ExportProgress) => void,
): Promise<Blob> {
  const scores = data.scores.slice(0, limit);
  const sources = [
    data.player.avatar_url,
    ...scores.map((score) => score.cover_url),
  ];
  const urls = [...new Set(sources.filter((url): url is string => !!url))];
  const loaded = new Map<string, HTMLImageElement | null>();
  let next = 0;
  onProgress?.({ stage: "images", completed: 0, total: urls.length });
  const worker = async () => {
    while (next < urls.length) {
      const url = urls[next++];
      loaded.set(url, await loadImage(url));
      onProgress?.({
        stage: "images",
        completed: loaded.size,
        total: urls.length,
      });
    }
  };
  // Avoid creating 51 competing requests, and load repeated covers only once.
  await Promise.all(Array.from({ length: Math.min(2, urls.length) }, worker));
  const images = sources.map((url) => (url ? (loaded.get(url) ?? null) : null));
  onProgress?.({
    stage: "rendering",
    completed: urls.length,
    total: urls.length,
  });
  const canvas = document.createElement("canvas");
  const columns = limit === 50 ? 5 : 2;
  const cardWidth = 748;
  const cardHeight = 140;
  const gap = 24;
  const headerScale = limit === 50 ? 1.5 : 1;
  const panelTop = 84;
  const panelHeight = 228 * headerScale;
  const panelBottom = panelTop + panelHeight;
  const headerCenter = panelTop + panelHeight / 2;
  const gridTop = panelBottom + 62;
  const rowHeight = cardHeight + 16;
  canvas.width = 80 + columns * cardWidth + (columns - 1) * gap;
  canvas.height = gridTop + Math.ceil(scores.length / columns) * rowHeight + 64;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error(t("downloadFailed"));
  const number = (value: number | null, digits = 2) =>
    value === null
      ? "—"
      : value.toLocaleString(locale, { maximumFractionDigits: digits });
  const text = (
    value: string,
    x: number,
    y: number,
    size: number,
    color = "#f1eff7",
    width = 1400,
  ) => {
    ctx.font = `600 ${size}px system-ui, sans-serif`;
    ctx.fillStyle = color;
    let fitted = value;
    if (ctx.measureText(fitted).width > width) {
      const characters = Array.from(value);
      while (
        characters.length &&
        ctx.measureText(`${characters.join("")}…`).width > width
      )
        characters.pop();
      fitted = `${characters.join("")}…`;
    }
    ctx.fillText(fitted, x, y);
  };
  const artwork = (
    image: HTMLImageElement | null,
    x: number,
    y: number,
    size: number,
  ) => {
    ctx.save();
    ctx.beginPath();
    ctx.roundRect(x, y, size, size, 12);
    ctx.clip();
    ctx.fillStyle = "#393048";
    ctx.fillRect(x, y, size, size);
    if (image) {
      const crop = Math.min(image.naturalWidth, image.naturalHeight);
      ctx.drawImage(
        image,
        (image.naturalWidth - crop) / 2,
        (image.naturalHeight - crop) / 2,
        crop,
        crop,
        x,
        y,
        size,
        size,
      );
    } else {
      text("♪", x + size / 3, y + size * 0.67, size / 2, "#c9b2ff");
    }
    ctx.restore();
  };

  const background = ctx.createLinearGradient(
    0,
    0,
    canvas.width,
    canvas.height,
  );
  background.addColorStop(0, "#241633");
  background.addColorStop(1, "#101e38");
  ctx.fillStyle = background;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.textBaseline = "middle";
  text("Raru Score Fetcher", 40, 42, 22, "#c9b2ff");
  ctx.textAlign = "right";
  text(`BEST ${limit}`, canvas.width - 40, 42, 34, "#c9b2ff");
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";

  const panel = ctx.createLinearGradient(
    40,
    panelTop,
    canvas.width - 40,
    panelBottom,
  );
  panel.addColorStop(0, "#30283ee8");
  panel.addColorStop(1, "#191a23e8");
  ctx.fillStyle = panel;
  ctx.strokeStyle = "#ac8ed140";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(40, panelTop, canvas.width - 80, panelHeight, 24);
  ctx.fill();
  ctx.stroke();
  const avatarSize = 112 * headerScale;
  const identityLeft = 72 + avatarSize + 24 * headerScale;
  const contentWidth = canvas.width - 144;
  const statsLeft = 72 + contentWidth * 0.4;
  const identityWidth = statsLeft - identityLeft - 32;
  artwork(images[0], 72, headerCenter - avatarSize / 2, avatarSize);
  ctx.textBaseline = "middle";
  text(
    data.player.username,
    identityLeft,
    headerCenter - 40 * headerScale,
    36 * headerScale,
    "#f1eff7",
    identityWidth,
  );
  text(
    `${modeLabels[data.mode]}  ·  ${data.player.country}  ·  #${data.player.user_id}`,
    identityLeft,
    headerCenter + 4 * headerScale,
    20 * headerScale,
    "#a49bb4",
    identityWidth,
  );
  const playTime = data.player.play_time;
  text(
    `${t("playTime")}  ${playTime == null ? "—" : `${Math.floor(playTime / 3600)}h ${Math.floor((playTime % 3600) / 60)}m`}`,
    identityLeft,
    headerCenter + 44 * headerScale,
    19 * headerScale,
    "#a49bb4",
    identityWidth,
  );
  const stats = [
    [t("performance"), `${number(data.player.pp)} pp`],
    [
      t("globalRank"),
      data.player.global_rank === null
        ? "—"
        : `#${number(data.player.global_rank, 0)}`,
    ],
    [t("accuracy"), `${number(data.player.hit_accuracy)}%`],
  ];
  const statWidth = (canvas.width - 72 - statsLeft) / stats.length;
  stats.forEach(([label, value], index) => {
    const x = statsLeft + (index + 0.5) * statWidth;
    ctx.textAlign = "center";
    text(
      label,
      x,
      headerCenter - 24 * headerScale,
      18 * headerScale,
      "#a49bb4",
      statWidth - 32,
    );
    text(
      value,
      x,
      headerCenter + 20 * headerScale,
      28 * headerScale,
      index === 0 ? "#dbc6ff" : "#f1eff7",
      statWidth - 32,
    );
  });
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
  text(t("bestPerformance"), 40, gridTop - 24, 22);
  ctx.textAlign = "right";
  text(
    t("scoreCount", { count: scores.length }),
    canvas.width - 40,
    gridTop - 24,
    18,
    "#a49bb4",
  );
  ctx.textAlign = "left";

  scores.forEach((score, index) => {
    const x = 40 + (index % columns) * (cardWidth + gap);
    const y = gridTop + Math.floor(index / columns) * rowHeight;
    ctx.fillStyle = "#1c1b25ed";
    ctx.beginPath();
    ctx.roundRect(x, y, cardWidth, cardHeight, 16);
    ctx.fill();
    ctx.strokeStyle = "#ffffff10";
    ctx.stroke();
    artwork(images[index + 1], x + 14, y + 21, 98);
    text(String(index + 1).padStart(2, "0"), x + 136, y + 32, 17, "#c9b2ff");
    text(score.beatmap_title, x + 171, y + 32, 21, "#f1eff7", 404);
    text(
      `${score.artist} · ${score.version}`,
      x + 136,
      y + 61,
      16,
      "#a49bb4",
      444,
    );
    const stars = `${number(score.star_rating)}★`;
    ctx.font = "600 16px system-ui, sans-serif";
    const starWidth = ctx.measureText(stars).width;
    const background = starBackground(score.star_rating);
    if (background) {
      ctx.fillStyle = background;
      ctx.beginPath();
      ctx.roundRect(x + 132, y + 74, starWidth + 8, 22, 4);
      ctx.fill();
    }
    text(stars, x + 136, y + 90, 16, starColor(score.star_rating));
    text(
      score.mods.join(" ") || "NM",
      x + 146 + starWidth,
      y + 90,
      16,
      "#c9b2ff",
      434 - starWidth,
    );
    text(
      `${number(score.accuracy * 100)}%  ·  ${number(score.max_combo, 0)}× combo`,
      x + 136,
      y + 120,
      17,
      "#d0cbd8",
      444,
    );
    ctx.textAlign = "right";
    text(
      gradeLabel(score.rank),
      x + cardWidth - 18,
      y + 44,
      34,
      rankColors[score.rank] ?? "#d0cbd8",
      130,
    );
    text(
      `${number(score.pp)} pp`,
      x + cardWidth - 18,
      y + 114,
      25,
      "#c9b2ff",
      146,
    );
    ctx.textAlign = "left";
  });
  text(t("srNote"), 40, canvas.height - 42, 16, "#a49bb4");
  text(
    t("updated", { date: new Date(data.fetched_at).toLocaleString(locale) }),
    40,
    canvas.height - 16,
    16,
    "#a49bb4",
  );
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error(t("downloadFailed")))),
      "image/png",
    );
  });
}

export function saveBestScores(
  blob: Blob,
  data: ScoresResponse,
  limit: number,
) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  // biome-ignore lint/suspicious/noControlCharactersInRegex: Strip invalid filename characters.
  const name = data.player.username.replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_");
  link.download = `${name}-${data.mode}-B${limit}.png`;
  document.body.append(link);
  link.click();
  link.remove();
  // Give browsers time to begin reading the download before releasing the blob.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
