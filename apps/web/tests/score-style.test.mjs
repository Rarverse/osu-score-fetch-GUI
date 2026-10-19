import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";

const styleModule = { exports: {} };
runInNewContext(
  ts.transpileModule(
    readFileSync(new URL("../src/score-style.ts", import.meta.url), "utf8"),
    {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    },
  ).outputText,
  {
    module: styleModule,
    exports: styleModule.exports,
    require: () => ({ t: (_key, { grade }) => `Silver ${grade}` }),
  },
);
const { starColor, starBackground, gradeLabel, gradeTitle } =
  styleModule.exports;

test("API silver grades display official S/SS letters and names", () => {
  assert.equal(gradeLabel("SH"), "S");
  assert.equal(gradeTitle("SH"), "Silver S");
  assert.equal(gradeLabel("SSH"), "SS");
  assert.equal(gradeTitle("SSH"), "Silver SS");
  for (const grade of ["SS", "S", "A", "B", "C", "D", "F"])
    assert.equal(gradeLabel(grade), grade);
});

test("official star colour stops, gamma interpolation and high-star foregrounds", () => {
  for (const [rating, color] of [
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
    [9, "#f6f05c"],
    [9.9, "#ff8068"],
    [10.6, "#ff4e6f"],
    [11.5, "#c645b8"],
    [12.4, "#6563de"],
    [20, "#6563de"],
  ])
    assert.equal(starColor(rating), color, `${rating} stars`);
  assert.equal(starColor(3.75), "#fbc262");
  for (const rating of [null, -1, 0, NaN, Infinity])
    assert.equal(starColor(rating), "#aaaaaa");
});

test("dark high-star text keeps official colours on a light backing", () => {
  assert.equal(starColor(7.7), "#18158e");
  for (const rating of [6.5, 7.7, 8.99])
    assert.equal(starBackground(rating), "#f1eff7");
  for (const rating of [null, 0, 4.2, 6.49, 9, 12.4])
    assert.equal(starBackground(rating), undefined);
});
