import { describe, expect, it } from "vitest";
import { buildLabel } from "./format";

const SHA = "0123456789abcdef0123456789abcdef01234567";

describe("buildLabel", () => {
  it("shortens a full commit to 7 characters", () => {
    expect(buildLabel({ status: "ok", sha: SHA })).toBe("сборка 0123456");
  });
  it("keeps the -dirty suffix", () => {
    expect(buildLabel({ status: "ok", sha: `${SHA}-dirty` })).toBe("сборка 0123456-dirty");
  });
  it("shows unknown as is", () => {
    expect(buildLabel({ status: "ok", sha: "unknown" })).toBe("сборка unknown");
  });
});
