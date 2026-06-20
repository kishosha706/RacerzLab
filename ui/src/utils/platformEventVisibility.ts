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

export function isClearPlatformDiagnostic(event: PlatformEventItem): boolean {
  const scope = platformEventScope(event);
  return scope === "internal"
    && event.severity === "info"
    && !event.is_visible_default;
}

export function filterPlatformEvents(
  events: PlatformEventItem[],
  mode: PlatformEventVisibilityMode,
): PlatformEventItem[] {
  return events.filter((event) => isPlatformEventVisibleInMode(event, mode) && !isClearPlatformDiagnostic(event));
}

export function isMutedPlatformEvent(
  event: PlatformEventItem,
  mode: PlatformEventVisibilityMode,
): boolean {
  if (mode === "actionable") return false;
  const scope = platformEventScope(event);
  return scope === "internal";
}

export function platformEventScopeLabel(event: PlatformEventItem): string {
  switch (platformEventScope(event)) {
    case "actionable":
      return "Actionable";
    case "watch":
      return "Watch";
    case "internal":
      return "Proxy / Internal";
    default:
      return "Actionable";
  }
}

export function platformEventVisibilityModeLabel(mode: PlatformEventVisibilityMode): string {
  switch (mode) {
    case "proxy":
      return "Proxy / Internal";
    case "all":
      return "All";
    default:
      return "Actionable";
  }
}
