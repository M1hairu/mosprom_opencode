import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OfflineBanner, TabBar } from "./components";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.restoreAllMocks();
});

describe("TabBar", () => {
  it("rejects more than 5 tabs", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const tabs = ["a", "b", "c", "d", "e", "f"].map((id) => ({ id, label: id, icon: null }));
    expect(() => act(() => root.render(<TabBar tabs={tabs} active="a" onSelect={() => {}} />))).toThrow(/не больше 5/);
  });
});

describe("OfflineBanner", () => {
  it("shows while the network is down and hides when it comes back", () => {
    let online = true;
    vi.spyOn(navigator, "onLine", "get").mockImplementation(() => online);
    act(() => root.render(<OfflineBanner />));
    expect(host.textContent).toBe("");

    online = false;
    act(() => window.dispatchEvent(new Event("offline")));
    expect(host.querySelector('[role="status"]')?.textContent).toMatch(/^Нет сети/);

    online = true;
    act(() => window.dispatchEvent(new Event("online")));
    expect(host.textContent).toBe("");
  });
});
