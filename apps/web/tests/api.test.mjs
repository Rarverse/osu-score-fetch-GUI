import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
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

const code = compile("api");
const messages = compile("i18n");

function loadApi(overrides = {}) {
  const context = {
    Headers,
    DOMException,
    AbortController,
    setTimeout,
    clearTimeout,
    crypto: webcrypto,
    localStorage: { getItem: () => null, setItem: () => {} },
    ...overrides,
  };
  const translationModule = { exports: {} };
  runInNewContext(messages, {
    ...context,
    module: translationModule,
    exports: translationModule.exports,
  });
  const apiModule = { exports: {} };
  runInNewContext(code, {
    ...context,
    module: apiModule,
    exports: apiModule.exports,
    require: (name) => {
      assert.equal(name, "./i18n");
      return translationModule.exports;
    },
  });
  return apiModule.exports;
}

test("HTTP browsers without randomUUID can query and reuse their visitor ID", async () => {
  const ids = [];
  const api = loadApi({
    crypto: { getRandomValues: webcrypto.getRandomValues.bind(webcrypto) },
    fetch: async (_url, { headers }) => {
      ids.push(headers.get("X-Visitor-Id"));
      return new Response(
        JSON.stringify({ error: { code: "NOT_CONFIGURED" } }),
        {
          status: 503,
        },
      );
    },
  });
  for (let index = 0; index < 2; index++) {
    await assert.rejects(
      api.getScores("player", 20, "mania", new AbortController().signal),
      (error) => error.code === "NOT_CONFIGURED",
    );
  }
  assert.match(
    ids[0],
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  );
  assert.equal(ids[0], ids[1]);
});

test("HTTP-date Retry-After is respected", async () => {
  const api = loadApi({
    fetch: async () =>
      new Response(JSON.stringify({ error: { code: "UPSTREAM_BUSY" } }), {
        status: 503,
        headers: {
          "Retry-After": new Date(Date.now() + 120_000).toUTCString(),
        },
      }),
  });
  await assert.rejects(
    api.getScores("player", 20, "mania", new AbortController().signal),
    (error) =>
      error.isBusy && error.retryAfter >= 119 && error.retryAfter <= 120,
  );
});

for (const phase of ["headers", "body"]) {
  test(`timeout aborts stalled ${phase} and releases timer`, async () => {
    let expire;
    let cleared = false;
    const api = loadApi({
      setTimeout: (callback, delay) => {
        assert.equal(delay, 90_000);
        expire = callback;
        return 1;
      },
      clearTimeout: () => {
        cleared = true;
      },
      fetch: async (_url, { signal }) => {
        const pending = () =>
          new Promise((_resolve, reject) => {
            signal.addEventListener("abort", () =>
              reject(new DOMException("Aborted", "AbortError")),
            );
          });
        if (phase === "headers") return pending();
        return { ok: true, json: pending, headers: new Headers() };
      },
    });
    const request = api.getScores(
      "player",
      20,
      "mania",
      new AbortController().signal,
    );
    await new Promise((resolve) => setImmediate(resolve));
    expire();
    await assert.rejects(
      request,
      (error) => error.code === "REQUEST_TIMEOUT" && !error.isBusy,
    );
    assert.equal(cleared, true);
  });
}

test("user cancellation aborts fetch and clears its deadline", async () => {
  let cleared = false;
  const controller = new AbortController();
  const api = loadApi({
    setTimeout: () => 1,
    clearTimeout: () => {
      cleared = true;
    },
    fetch: (_url, { signal }) =>
      new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () =>
          reject(new DOMException("Aborted", "AbortError")),
        );
      }),
  });
  const request = api.getScores("player", 20, "mania", controller.signal);
  controller.abort();
  await assert.rejects(request, (error) => error.name === "AbortError");
  assert.equal(cleared, true);
});

test("automatic mode omits mode and shares resolved cache without manual queries poisoning it", async () => {
  const urls = [];
  const api = loadApi({
    fetch: async (url) => {
      urls.push(url);
      const mode =
        new URL(url, "http://localhost").searchParams.get("mode") || "taiko";
      return new Response(
        JSON.stringify({
          player: { username: "Player", user_id: 123 },
          mode,
          scores: [],
        }),
        {
          headers: { "X-Cache-TTL": "60" },
        },
      );
    },
  });
  const signal = new AbortController().signal;
  await api.getScores("Player", 20, "mania", signal);
  const automatic = await api.getScores("Player", 20, "auto", signal);
  assert.equal(automatic.data.mode, "taiko");
  assert.equal(
    new URL(urls[1], "http://localhost").searchParams.has("mode"),
    false,
  );
  assert.equal(
    (await api.getScores("123", 20, "taiko", signal)).cache,
    "MEMORY",
  );
  assert.equal(
    (await api.getScores("123", 20, "auto", signal)).cache,
    "MEMORY",
  );
  await api.getScores("123", 50, "taiko", signal);
  assert.equal(urls.length, 3);
  assert.match(urls[2], /limit=50&mode=taiko/);
});

for (const ttl of [30, 180]) {
  test(`browser scores remain cached for the server's ${ttl}-second window`, async () => {
    let now = 100_000;
    let calls = 0;
    const api = loadApi({
      Date: { now: () => now },
      fetch: async () => {
        calls++;
        return new Response(
          JSON.stringify({
            player: { username: "Player", user_id: 123 },
            mode: "mania",
            scores: [],
          }),
          { headers: { "X-Cache-TTL": String(ttl) } },
        );
      },
    });
    const signal = new AbortController().signal;
    await api.getScores("Player", 20, "mania", signal);
    now += (ttl - 1) * 1000;
    assert.equal(
      (await api.getScores("123", 20, "mania", signal)).cache,
      "MEMORY",
    );
    assert.equal(calls, 1);
    now += 1000;
    assert.notEqual(
      (await api.getScores("Player", 20, "mania", signal)).cache,
      "MEMORY",
    );
    assert.equal(calls, 2);
  });
}

for (const ttl of [30, 600]) {
  test(`refresh deadline preserves server TTL ${ttl} across browser cache hits`, async () => {
    let now = 100_000;
    const api = loadApi({
      Date: { now: () => now },
      fetch: async () =>
        new Response(
          JSON.stringify({
            player: { username: "Player", user_id: 123 },
            mode: "mania",
            scores: [],
          }),
          { headers: { "X-Cache-TTL": String(ttl), "X-Cache": "HIT" } },
        ),
    });
    const signal = new AbortController().signal;
    const first = await api.getScores("Player", 20, "mania", signal);
    assert.equal(first.refreshAt, now + ttl * 1000);
    now += 10_000;
    const cached = await api.getScores("123", 20, "mania", signal);
    assert.equal(cached.cache, "MEMORY");
    assert.equal(cached.refreshAt, first.refreshAt);
  });
}

for (const ttl of [null, "", "invalid", "-1", "0"]) {
  test(`refresh deadline handles TTL ${JSON.stringify(ttl)}`, async () => {
    const api = loadApi({
      Date: { now: () => 100_000 },
      fetch: async () =>
        new Response(
          JSON.stringify({
            player: { username: "Player", user_id: 123 },
            mode: "mania",
            scores: [],
          }),
          { headers: ttl === null ? {} : { "X-Cache-TTL": ttl } },
        ),
    });
    const result = await api.getScores(
      "Player",
      20,
      "mania",
      new AbortController().signal,
    );
    assert.equal(result.refreshAt, ttl === "0" ? 100_000 : null);
  });
}
