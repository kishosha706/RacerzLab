/**
 * Environment detection helpers.
 */

/**
 * Check if the app is running inside a Tauri webview.
 */
export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/**
 * Check if the app is running in a browser (dev mode).
 */
export function isBrowser(): boolean {
  return !isTauri();
}
