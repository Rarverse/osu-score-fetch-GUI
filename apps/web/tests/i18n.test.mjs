import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";

const source = ts.transpileModule(
  readFileSync(new URL("../src/i18n.ts", import.meta.url), "utf8"),
  {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  },
).outputText;

function loadLanguage(globals = {}) {
  const module = { exports: {} };
  runInNewContext(source, { module, exports: module.exports, ...globals });
  return module.exports;
}

test("language paths override browser preferences, including trailing slashes", () => {
  for (const [path, expected, browserLanguage, locale] of [
    ["/en", "en", "zh-CN", "en-US"],
    ["/en/", "en", "zh-CN", "en-US"],
    ["/zh", "zh", "en-US", "zh-CN"],
    ["/zh/", "zh", "en-US", "zh-CN"],
  ]) {
    const url = new URL(`${path}?example=1#results`, "https://example.com");
    const result = loadLanguage({
      navigator: { languages: [browserLanguage] },
      location: { pathname: url.pathname },
    });
    assert.equal(result.language, expected);
    assert.equal(result.locale, locale);
    assert.equal(
      result.t("queryFailed"),
      loadLanguage({ navigator: { languages: [expected] } }).t("queryFailed"),
    );
  }
});

test("root and unrecognized paths preserve browser language detection", () => {
  const { detectLanguage } = loadLanguage();
  for (const path of ["/", "/fr", "/english", "/zh-other", "/en/other"]) {
    assert.equal(detectLanguage(["fr-FR", "zh-CN", "en-US"], path), "zh");
    assert.equal(detectLanguage(["en-GB", "zh-CN"], path), "en");
    assert.equal(detectLanguage(["zh_TW"], path), "zh");
    assert.equal(detectLanguage(["fr-FR"], path), "en");
    assert.equal(detectLanguage([], path), "en");
  }
  assert.equal(loadLanguage().language, "en");
});
