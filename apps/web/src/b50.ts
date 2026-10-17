import { locale, t } from "./i18n";
import { modeLabels, type ScoresResponse } from "./types";

// Only CORS-enabled images enter the canvas; missing artwork uses a placeholder.
function loadImage(url: string | null): Promise<HTMLImageElement | null> {
  if (!url) return Promise.resolve(null);
  return new Promise((resolve) => {
    const image = new Image();
    const finish = (value: HTMLImageElement | null) => {
      clearTimeout(timer);
      image.onload = null;
      image.onerror = null;
      resolve(value);
    };
    const timer = setTimeout(() => finish(null), 8000);
    image.crossOrigin = "anonymous";
    image.onload = () => finish(image);
    image.onerror = () => finish(null);
    image.src = url;
  });
}

export async function renderB50(data: ScoresResponse): Promise<Blob> {
  const scores = data.scores.slice(0, 50);
  const images = await Promise.all(
    [data.player.avatar_url, ...scores.map((score) => score.cover_url)].map(
      loadImage,
    ),
  );
  const canvas = document.createElement("canvas");
  canvas.width = 1600;
  canvas.height = 370 + Math.ceil(scores.length / 2) * 136;
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

  ctx.fillStyle = "#101116";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  text("RARVERSE  /  RARSU", 40, 48, 20, "#c9b2ff");
  text("BEST 50", 1350, 52, 34, "#c9b2ff");
  artwork(images[0], 40, 80, 112);
  text(data.player.username, 180, 120, 36, "#f1eff7", 1130);
  text(
    `${modeLabels[data.mode]}  ·  ${data.player.country}  ·  #${data.player.user_id}`,
    180,
    160,
    21,
    "#a49bb4",
  );
  text(
    `${number(data.player.pp)} pp   /   ${t("globalRank")} ${data.player.global_rank === null ? "—" : `#${number(data.player.global_rank, 0)}`}   /   ${number(data.player.hit_accuracy)}%`,
    40,
    238,
    26,
  );
  text(t("scoreCount", { count: scores.length }), 40, 278, 19, "#a49bb4");

  scores.forEach((score, index) => {
    const x = 40 + (index % 2) * 772;
    const y = 300 + Math.floor(index / 2) * 136;
    ctx.fillStyle = "#1c1b25";
    ctx.beginPath();
    ctx.roundRect(x, y, 748, 122, 14);
    ctx.fill();
    artwork(images[index + 1], x + 12, y + 12, 98);
    text(String(index + 1).padStart(2, "0"), x + 120, y + 29, 17, "#c9b2ff");
    text(score.beatmap_title, x + 155, y + 30, 21, "#f1eff7", 420);
    text(
      `${score.artist} · ${score.version}`,
      x + 120,
      y + 56,
      16,
      "#a49bb4",
      460,
    );
    text(
      `${number(score.star_rating)}★  ${score.mods.join(" ") || "NM"}`,
      x + 120,
      y + 81,
      16,
      "#c9b2ff",
      460,
    );
    text(
      `${number(score.accuracy * 100)}%  ·  ${number(score.max_combo, 0)}× combo`,
      x + 120,
      y + 106,
      17,
      "#d0cbd8",
      460,
    );
    text(score.rank, x + 600, y + 38, 22, "#e6d79e", 130);
    text(`${number(score.pp)} pp`, x + 590, y + 88, 22, "#c9b2ff", 146);
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

export function saveB50(blob: Blob, data: ScoresResponse) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  // biome-ignore lint/suspicious/noControlCharactersInRegex: Strip invalid filename characters.
  const name = data.player.username.replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_");
  link.download = `${name}-${data.mode}-B50.png`;
  document.body.append(link);
  link.click();
  link.remove();
  // Give browsers time to begin reading the download before releasing the blob.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
