import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";

function compile(name) {
  return ts.transpileModule(
    readFileSync(new URL(`../src/${name}.ts`, import.meta.url), "utf8"),
    {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    },
  ).outputText;
}

function loadRenderer({ failImages = false } = {}) {
  const labels = [];
  const imageSources = [];
  const drawings = [];
  const downloads = [];
  let activeImages = 0;
  let maxActiveImages = 0;
  const context = {
    fillStyle: "",
    font: "",
    measureText: (value) => ({ width: value.length * 8 }),
    fillText(value, x, y) {
      labels.push({
        value,
        color: this.fillStyle,
        x,
        y,
        baseline: this.textBaseline,
        align: this.textAlign,
      });
    },
    drawImage: (...args) => drawings.push(args),
  };
  for (const method of [
    "save",
    "beginPath",
    "roundRect",
    "clip",
    "fillRect",
    "restore",
    "fill",
  ])
    context[method] = () => {};
  const canvas = {
    width: 0,
    height: 0,
    getContext: () => context,
    toBlob: (callback) => callback(new Blob(["png"], { type: "image/png" })),
  };
  const imageModule = { exports: {} };
  runInNewContext(compile("images"), {
    module: imageModule,
    exports: imageModule.exports,
  });
  const styleModule = { exports: {} };
  runInNewContext(compile("score-style"), {
    module: styleModule,
    exports: styleModule.exports,
    require: () => ({ t: (key) => key }),
  });
  const renderer = { exports: {} };
  runInNewContext(compile("b50"), {
    module: renderer,
    exports: renderer.exports,
    require: (name) => {
      if (name === "./images") return imageModule.exports;
      if (name === "./score-style") return styleModule.exports;
      if (name === "./types") return { modeLabels: { mania: "osu!mania" } };
      if (name === "./i18n") return { locale: "en-US", t: (key) => key };
      throw new Error(`Unexpected module: ${name}`);
    },
    Image: class {
      naturalWidth = 100;
      naturalHeight = 100;
      set src(value) {
        imageSources.push(value);
        activeImages++;
        maxActiveImages = Math.max(maxActiveImages, activeImages);
        queueMicrotask(() => {
          activeImages--;
          if (failImages) this.onerror?.();
          else this.onload?.();
        });
      }
    },
    document: {
      createElement: (tag) => {
        if (tag === "canvas") return canvas;
        assert.equal(tag, "a");
        return {
          click() {
            downloads.push(this.download);
          },
          remove() {},
        };
      },
      body: { append() {} },
    },
    URL: { createObjectURL: () => "blob:test", revokeObjectURL() {} },
    setTimeout: (callback, delay) => {
      if (delay === 60_000) return 0;
      return setTimeout(callback, delay);
    },
    clearTimeout,
  });
  return {
    ...renderer.exports,
    labels,
    imageSources,
    drawings,
    downloads,
    canvas,
    maxActiveImages: () => maxActiveImages,
  };
}

function fixture(count) {
  return {
    player: {
      username: "Player:Test",
      user_id: 2,
      avatar_url: "https://a.ppy.sh/2",
      country: "CN",
      pp: 1000,
      global_rank: 100,
      hit_accuracy: 99,
    },
    mode: "mania",
    fetched_at: "2026-10-19T00:00:00Z",
    scores: Array.from({ length: count }, (_, index) => ({
      beatmap_title: `Song ${index + 1}`,
      artist: "Artist",
      version: "4K",
      cover_url: "https://assets.ppy.sh/beatmaps/1/covers/list@2x.jpg",
      rank: ["SS", "SSH", "S", "SH", "A", "B", "C", "D", "F"][index % 9],
      mods: [],
      pp: 100,
      accuracy: 0.99,
      star_rating: 4,
      max_combo: 1000,
    })),
  };
}

for (const limit of [20, 50]) {
  test(`B${limit} exports matching heading, rows, artwork and filename`, async () => {
    const renderer = loadRenderer();
    const data = fixture(50);
    const blob = await renderer.renderBestScores(data, limit);
    assert.equal(blob.type, "image/png");
    assert.equal(renderer.canvas.height, 370 + Math.ceil(limit / 2) * 136);
    assert.ok(renderer.labels.some(({ value }) => value === `BEST ${limit}`));
    assert.equal(
      renderer.labels.filter(({ value }) => value.startsWith("Song ")).length,
      limit,
    );
    assert.equal(renderer.drawings.length, limit + 1);
    assert.equal(renderer.imageSources.length, 2); // One avatar and one reused cover.
    for (const source of renderer.imageSources)
      assert.ok(source.startsWith("/api/v1/images?url="));
    renderer.saveBestScores(blob, data, limit);
    assert.deepEqual(renderer.downloads, [`Player_Test-mania-B${limit}.png`]);
  });
}

test("rank grades use distinct colors, including silver hidden grades", async () => {
  const renderer = loadRenderer();
  await renderer.renderBestScores(fixture(9), 20);
  const color = (rank) =>
    renderer.labels.find(({ value }) => value === rank).color;
  assert.equal(color("SS"), color("S"));
  assert.equal(
    renderer.labels.some(({ value }) => ["SH", "SSH"].includes(value)),
    false,
  );
  const silverSS = renderer.labels.filter(({ value }) => value === "SS")[1];
  const silverS = renderer.labels.filter(({ value }) => value === "S")[1];
  assert.equal(silverSS.color, "#d2dfe6");
  assert.equal(silverS.color, silverSS.color);
  assert.equal(
    new Set([silverS.color, ...["S", "A", "B", "C", "D", "F"].map(color)]).size,
    7,
  );
});

test("brand and BEST label share the same vertical centre with balanced margins", async () => {
  const renderer = loadRenderer();
  await renderer.renderBestScores(fixture(1), 20);
  const brand = renderer.labels.find(
    ({ value }) => value === "Raru Score Fetcher",
  );
  const best = renderer.labels.find(({ value }) => value === "BEST 20");
  assert.equal(brand.y, best.y);
  assert.equal(brand.baseline, "middle");
  assert.equal(best.baseline, "middle");
  assert.equal(best.align, "right");
  assert.equal(best.x, renderer.canvas.width - brand.x);
});

test("stars follow official colours while mod labels keep their own colour", async () => {
  const renderer = loadRenderer();
  const data = fixture(3);
  data.scores.forEach((score, index) => {
    score.star_rating = [2, 4.9, 9][index];
    score.mods = ["HD"];
  });
  await renderer.renderBestScores(data, 20);
  const stars = renderer.labels.filter(({ value }) => value.endsWith("★"));
  assert.deepEqual(
    stars.map(({ color }) => color),
    ["#4fffd5", "#ff4e6f", "#000000"],
  );
  assert.ok(
    renderer.labels
      .filter(({ value }) => value === "HD")
      .every(({ color }) => color === "#c9b2ff"),
  );
});

test("distinct artwork loads with at most two requests and reports progress", async () => {
  const renderer = loadRenderer();
  const data = fixture(50);
  data.scores.forEach((score, index) => {
    score.cover_url = `https://assets.ppy.sh/beatmaps/${index + 1}/covers/list@2x.jpg`;
  });
  const progress = [];
  await renderer.renderBestScores(data, 50, (update) => progress.push(update));
  assert.equal(renderer.maxActiveImages(), 2);
  assert.equal(renderer.imageSources.length, 51);
  assert.equal(new Set(renderer.imageSources).size, 51);
  assert.deepEqual(
    progress.map(({ stage, completed, total }) => [stage, completed, total]),
    [
      ...Array.from({ length: 52 }, (_, index) => ["images", index, 51]),
      ["rendering", 51, 51],
    ],
  );
});

test("fewer scores preserve the requested B50 title without adding empty rows", async () => {
  const renderer = loadRenderer();
  await renderer.renderBestScores(fixture(3), 50);
  assert.equal(renderer.drawings.length, 4);
  assert.equal(renderer.canvas.height, 370 + 2 * 136);
  assert.ok(renderer.labels.some(({ value }) => value === "BEST 50"));
});

test("failed artwork blocks an incomplete export and a later attempt can retry", async () => {
  const renderer = loadRenderer({ failImages: true });
  await assert.rejects(
    renderer.renderBestScores(fixture(1), 20),
    /artworkFailed/,
  );
  assert.equal(renderer.downloads.length, 0);
  const retry = loadRenderer();
  assert.equal(
    (await retry.renderBestScores(fixture(1), 20)).type,
    "image/png",
  );
});

for (const [seconds, expected] of [
  [7265, "2h 1m"],
  [0, "0h 0m"],
  [null, "—"],
  [undefined, "—"],
]) {
  test(`play time renders above rank for ${seconds}`, async () => {
    const renderer = loadRenderer();
    const data = fixture(1);
    data.player.play_time = seconds;
    await renderer.renderBestScores(data, 20);
    const time = renderer.labels.find(
      ({ value }) => value === `playTime  ${expected}`,
    );
    const rank = renderer.labels.find(({ value }) =>
      value.includes("globalRank"),
    );
    assert.ok(time);
    assert.ok(time.y > 160 && time.y < rank.y);
  });
}
