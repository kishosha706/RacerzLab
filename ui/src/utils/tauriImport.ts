/**
 * Tauri native file import helpers.
 *
 * Uses @tauri-apps/plugin-dialog for native file/folder pickers.
 * Falls back to browser file input when not running in Tauri.
 */

import { open } from "@tauri-apps/plugin-dialog";
import { isTauri } from "../utils/env";

export interface NativeImportResult {
  filePath: string | null;
  cancelled: boolean;
}

/**
 * Open a native file picker for .ibt/.sto telemetry files.
 * Returns the selected file path, or null if cancelled.
 */
export async function pickTelemetryFile(): Promise<NativeImportResult> {
  if (!isTauri()) {
    return { filePath: null, cancelled: false };
  }
  try {
    const selected = await open({
      multiple: false,
      filters: [
        {
          name: "iRacing Telemetry",
          extensions: ["ibt", "sto"],
        },
      ],
      title: "Import iRacing Telemetry",
    });
    if (selected === null) {
      return { filePath: null, cancelled: true };
    }
    return { filePath: selected as string, cancelled: false };
  } catch {
    return { filePath: null, cancelled: false };
  }
}

/**
 * Open a native file picker for track map files.
 */
export async function pickTrackMapFile(): Promise<NativeImportResult> {
  if (!isTauri()) {
    return { filePath: null, cancelled: false };
  }
  try {
    const selected = await open({
      multiple: false,
      filters: [
        {
          name: "Track Map File",
          extensions: ["mt2"],
        },
      ],
      title: "Import Track Map",
    });
    if (selected === null) {
      return { filePath: null, cancelled: true };
    }
    return { filePath: selected as string, cancelled: false };
  } catch {
    return { filePath: null, cancelled: false };
  }
}

/**
 * Open a native folder picker for telemetry directory scanning.
 */
export async function pickTelemetryFolder(): Promise<NativeImportResult> {
  if (!isTauri()) {
    return { filePath: null, cancelled: false };
  }
  try {
    const selected = await open({
      multiple: false,
      directory: true,
      title: "Select Telemetry Folder",
    });
    if (selected === null) {
      return { filePath: null, cancelled: true };
    }
    return { filePath: selected as string, cancelled: false };
  } catch {
    return { filePath: null, cancelled: false };
  }
}
