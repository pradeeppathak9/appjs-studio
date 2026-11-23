import { describe, expect, it } from "vitest";
import { findVariables, variableProblems } from "./vars";

describe("{{variable}} detection", () => {
  it("finds names in order, once, across prompt and negative prompt", () => {
    expect(findVariables("A {{mood}} photo of {{ subject }} in {{mood}} light", "no {{ban_1}}")).toEqual([
      "mood",
      "subject",
      "ban_1",
    ]);
  });

  it("ignores things that aren't placeholders", () => {
    expect(findVariables("{{}} {{a-b}} {single} {{ok}}", null)).toEqual(["ok"]);
  });

  it("reports undeclared and unused variables", () => {
    expect(variableProblems(["mood", "subject"], ["mood", "style"])).toEqual({
      undeclared: ["subject"],
      unused: ["style"],
    });
  });
});
