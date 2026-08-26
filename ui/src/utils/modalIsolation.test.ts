import { describe, expect, it } from "vitest";

import { isolateCockpitForPriorityModal } from "./modalIsolation";

describe("Priority modal cockpit isolation", () => {
  it("isolates the full shell, observes late surfaces, and restores prior attributes", async () => {
    document.body.innerHTML = `
      <div class="cockpit-shell">
        <a class="shell-skip-link">Skip</a>
        <header aria-hidden="false">Context</header>
        <div class="cockpit-body">
          <nav>Workspaces</nav>
          <button data-priority-modal-layer="true">Backdrop</button>
          <aside data-priority-modal-layer="true">Priority dialog</aside>
          <main inert>Workspace</main>
        </div>
        <footer>Timeline</footer>
      </div>
    `;
    const shell = document.querySelector<HTMLElement>(".cockpit-shell");
    const body = document.querySelector<HTMLElement>(".cockpit-body");
    if (!shell || !body) throw new Error("test shell missing");

    const release = isolateCockpitForPriorityModal(shell);
    const modalLayers = [...document.querySelectorAll<HTMLElement>("[data-priority-modal-layer]")];
    expect(modalLayers.every((element) => !element.hasAttribute("inert"))).toBe(true);
    expect(document.querySelector("header")?.getAttribute("aria-hidden")).toBe("true");
    expect(document.querySelector("nav")?.hasAttribute("inert")).toBe(true);
    expect(document.querySelector("footer")?.hasAttribute("inert")).toBe(true);

    const lateSurface = document.createElement("section");
    lateSurface.textContent = "Late compare basket";
    shell.append(lateSurface);
    await Promise.resolve();
    expect(lateSurface.hasAttribute("inert")).toBe(true);
    expect(lateSurface.getAttribute("aria-hidden")).toBe("true");

    release();
    expect(document.querySelector("header")?.getAttribute("aria-hidden")).toBe("false");
    expect(document.querySelector("nav")?.hasAttribute("inert")).toBe(false);
    expect(document.querySelector("main")?.hasAttribute("inert")).toBe(true);
    expect(lateSurface.hasAttribute("inert")).toBe(false);
  });
});
