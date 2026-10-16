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
