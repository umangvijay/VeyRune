import { act, useEffect, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import LandingPage from "../src/app/page";
import type { SceneStatus } from "../src/components/CyanotypeScene";

type SceneProps = { onStatus: (status: SceneStatus) => void };
const scene = vi.hoisted(() => ({ props: null as SceneProps | null, mounts: 0 }));
vi.mock("next/dynamic", () => ({ default: () => function TestScene(props: SceneProps) {
  scene.props = props;
  const { onStatus } = props;
  useEffect(() => { scene.mounts += 1; onStatus("ready"); }, [onStatus]);
  return null;
} }));
vi.mock("@/components/PublicNavbar", () => ({ default: () => null }));
vi.mock("next/link", () => ({ default: ({ children, ...props }: { children: ReactNode; href: string }) => <a {...props}>{children}</a> }));

let root: Root;
let host: HTMLDivElement;
const button = (label: string) => Array.from(host.querySelectorAll("button")).find(el => el.getAttribute("aria-label") === label || el.textContent?.trim() === label)!;
async function click(label: string) { await act(async () => button(label).click()); }

beforeEach(async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  scene.mounts = 0;
  window.localStorage.clear();
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => root.render(<LandingPage />));
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});

describe("landing controls", () => {
  it("resumes the selected speed after pause", async () => {
    await click("0.5×");
    await click("Pause scene");
    expect(host.textContent).toContain("PAUSED");
    await click("Play scene");
    expect(button("0.5×").getAttribute("aria-pressed")).toBe("true");
  });

  it("recovers from a lost scene without hiding the hero or enabling dead controls", async () => {
    await click("Planet");
    expect(host.querySelector(".is-inspecting")).not.toBeNull();
    await act(async () => scene.props!.onStatus("fallback"));
    expect(host.querySelector(".is-inspecting")).toBeNull();
    expect(button("Planet").disabled).toBe(true);
    expect(button("Pause scene").disabled).toBe(true);
    expect(host.textContent).toContain("Showing the still illustration");
    await click("Retry 3D scene");
    expect(scene.mounts).toBe(2);
    expect(button("Planet").disabled).toBe(false);
  });

  it("returns to overview with Escape", async () => {
    await click("Blueprint");
    await act(async () => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
    expect(button("Blueprint").getAttribute("aria-pressed")).toBe("false");
  });
});
