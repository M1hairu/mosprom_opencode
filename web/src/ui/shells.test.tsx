import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { PhoneShell } from "./shells";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const TABS = [
  { id: "a", label: "A", icon: null },
  { id: "b", label: "B", icon: null },
  { id: "c", label: "C", icon: null },
] as const;

let host: HTMLDivElement;
let root: Root;
const render = (active: "a" | "b" | "c", text: string = active) =>
  act(() =>
    root.render(
      <MemoryRouter>
        <PhoneShell tabs={TABS} active={active} onSelect={() => undefined}>
          <p>{text}</p>
        </PhoneShell>
      </MemoryRouter>,
    ),
  );
const pane = () => host.querySelector("main > div") as HTMLElement;

beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

describe("PhoneShell tab change", () => {
  it("slides the new tab in from the side of its tab", () => {
    render("a");
    expect(pane().dataset.dir).toBe("none");
    render("c");
    expect(pane().dataset.dir).toBe("next");
    render("b");
    expect(pane().dataset.dir).toBe("back");
  });

  it("keeps the direction when the same tab re-renders", () => {
    render("a");
    render("b");
    const el = pane();
    render("b", "b again");
    expect(pane()).toBe(el);
    expect(pane().dataset.dir).toBe("next");
  });

  it("starts the new tab at the top", () => {
    render("a");
    const main = host.querySelector("main")!;
    main.scrollTop = 300;
    render("b");
    expect(main.scrollTop).toBe(0);
  });
});
