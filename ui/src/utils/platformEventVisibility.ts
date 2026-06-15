import type {
  PlatformEventDisplayScope,
  PlatformEventItem,
  PlatformEventVisibilityMode,
} from "../types/telemetry";

export function platformEventScope(event: PlatformEventItem): PlatformEventDisplayScope {
  return event.display_scope ?? (event.is_visible_default ? "actionable" : "internal");
}

export function isPlatformEventVisibleInMode(
  event: PlatformEventItem,
  mode: PlatformEventVisibilityMode,
): boolean {
  const scope = platformEventScope(event);
  if (mode === "all") return true;
  if (mode === "proxy") return scope === "actionable" || scope === "watch" || scope === "internal";
  return (scope === "actionable" || scope === "watch") && Boolean(event.is_visible_default);
}

export function filterPlatformEvents(
  events: PlatformEventItem[],
  mode: PlatformEventVisibilityMode,
): PlatformEventItem[] {
  return events.filter((event) => isPlatformEventVisibleInMode(event, mode));
}

export function isMutedPlatformEvent(
  event: PlatformEventItem,
  mode: PlatformEventVisibilityMode,
): boolean {
  if (mode === "actionable") return false;
  const scope = platformEventScope(event);
  return scope === "internal" || scope === "debug";
}

export function platformEventScopeLabel(event: PlatformEventItem): string {
  switch (platformEventScope(event)) {
    case "actionable":
      return "Actionable";
    case "watch":
      return "Watch";
    case "internal":
      return "Proxy / Internal";
    case "debug":
      return "Debug";
    default:
      return "Actionable";
  }
}
