type AttributeSnapshot = {
  ariaHidden: string | null;
  inert: boolean;
};

const PRIORITY_MODAL_LAYER = "[data-priority-modal-layer=\"true\"]";

/**
 * Isolate every cockpit surface except the narrow-screen Priority modal.
 *
 * The modal remains inside `.cockpit-body` so it keeps its engineering-case and
 * selection contexts. A child-list observer also catches async shell surfaces
 * that mount while the dialog is open (timeline, map, workflow ribbon, etc.).
 */
export function isolateCockpitForPriorityModal(shell: HTMLElement): () => void {
  const snapshots = new Map<HTMLElement, AttributeSnapshot>();

  const isolate = (element: HTMLElement) => {
    if (!snapshots.has(element)) {
      snapshots.set(element, {
        ariaHidden: element.getAttribute("aria-hidden"),
        inert: element.hasAttribute("inert"),
      });
    }
    element.setAttribute("inert", "");
    element.setAttribute("aria-hidden", "true");
  };

  const restore = (element: HTMLElement, snapshot: AttributeSnapshot) => {
    if (!snapshot.inert) element.removeAttribute("inert");
    if (snapshot.ariaHidden == null) element.removeAttribute("aria-hidden");
    else element.setAttribute("aria-hidden", snapshot.ariaHidden);
  };

  const scan = () => {
    const body = Array.from(shell.children).find(
      (element): element is HTMLElement => (
        element instanceof HTMLElement && element.classList.contains("cockpit-body")
      ),
    );
    if (!body) return;

    for (const child of Array.from(shell.children)) {
      if (child instanceof HTMLElement && child !== body && !child.matches(PRIORITY_MODAL_LAYER)) {
        isolate(child);
      }
    }
    for (const child of Array.from(body.children)) {
      if (child instanceof HTMLElement && !child.matches(PRIORITY_MODAL_LAYER)) {
        isolate(child);
      }
    }
  };

  scan();
  const observer = new MutationObserver(scan);
  observer.observe(shell, { childList: true, subtree: true });

  return () => {
    observer.disconnect();
    for (const [element, snapshot] of snapshots) restore(element, snapshot);
    snapshots.clear();
  };
}
