import { describe, expect, it } from "vitest";
import { isSoftwareRenderer } from "./LaserCanvas";

// The hero scene must not start on a software rasterizer: in the headless browser of make e2e it
// held the main thread for ~20 s per second of the page and starved the build label and the links.
describe("isSoftwareRenderer", () => {
  it("knows the software rasterizers", () => {
    expect(isSoftwareRenderer("ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)")).toBe(true);
    expect(isSoftwareRenderer("llvmpipe (LLVM 15.0.7, 256 bits)")).toBe(true);
    expect(isSoftwareRenderer("Microsoft Basic Render Driver Software")).toBe(true);
  });
  it("keeps the scene on real GPUs and when the name is unknown", () => {
    expect(isSoftwareRenderer("ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)")).toBe(false);
    expect(isSoftwareRenderer("Apple GPU")).toBe(false);
    expect(isSoftwareRenderer("")).toBe(false);
  });
});
