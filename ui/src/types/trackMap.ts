export interface TrackMapPoint {
  index: number;
  x: number;
  y: number;
  z: number | null;
  x_m: number | null;
  y_m: number | null;
  z_m: number | null;
  distance_m: number | null;
  distance_ft: number | null;
  lap_pct: number | null;
  heading_rad: number | null;
  curvature_1_per_m: number | null;
  radius_m: number | null;
  section_name: string | null;
  section_type: "straight" | "corner" | "unknown" | null;
  kind: "centerline" | "left_boundary" | "right_boundary" | "unknown";
}

export interface TrackMapMarker {
  marker_id: string;
  name: string;
  distance_m: number;
  distance_ft: number;
  lap_pct: number;
  x: number;
  y: number;
  z: number | null;
  heading_rad: number | null;
  source: "mt2" | "telemetry" | "fallback";
}

export interface TrackMapSection {
  section_id: string;
  name: string;
  section_type: "straight" | "corner" | "unknown";
  start_marker: string;
  end_marker: string;
  start_distance_m: number;
  end_distance_m: number;
  start_distance_ft: number;
  end_distance_ft: number;
  start_lap_pct: number;
  end_lap_pct: number;
  length_m: number;
  length_ft: number;
  wraps_start_finish: boolean;
}

export interface TrackMapBounds {
  min_x_m: number;
  max_x_m: number;
  min_y_m: number;
  max_y_m: number;
  width_m: number;
  height_m: number;
  min_x_ft: number;
  max_x_ft: number;
  min_y_ft: number;
  max_y_ft: number;
  width_ft: number;
  height_ft: number;
}

export interface TrackMapOrigin {
  lat: number | null;
  lng: number | null;
  alt: number | null;
  gps_supported: boolean;
}

export interface TrackMapMetadata {
  format: string;
  version: number | null;
  track_name: string;
  model_name: string | null;
  closed: boolean;
  clockwise_flag: boolean;
  x_over: boolean;
  z_rotation_rad: number;
  distance_m: number;
  distance_ft: number;
  distance_miles: number;
  point_record: string[];
  units: Record<string, string>;
  origin: TrackMapOrigin;
  has_boundaries: boolean;
  has_sections: boolean;
  has_markers: boolean;
  warnings: string[];
}

export interface TrackMap {
  map_id: string;
  source_file: string | null;
  file_size_bytes: number;
  sha256: string;
  metadata: TrackMapMetadata;
  bounds: TrackMapBounds;
  points: TrackMapPoint[];
  markers: TrackMapMarker[];
  sections: TrackMapSection[];
  status: "parsed" | "partial" | "unsupported";
  supported: boolean;
  partial: boolean;
  warnings: string[];
}

export interface TrackMapIndexEntry {
  map_id: string;
  track_key: string;
  layout_key: string;
  display_name: string;
  source_filename: string;
  local_path: string;
  cache_path: string;
  source_type: "mt2" | "telemetry" | "fallback";
  status: string;
  supported: boolean;
  partial: boolean;
  points_count: number;
  markers_count: number;
  sections_count: number;
  distance_ft: number;
  match_aliases: string[];
  warnings: string[];
  match_confidence?: string;
  match_score?: number;
}

export interface TrackMapOverlayMarker {
  marker_id: string;
  kind: "platform_event" | "delta_annotation" | "insight" | "tire_shock" | "notebook_finding" | "target_zone";
  label: string;
  description?: string;
  lap_pct: number;
  distance_ft?: number;
  x: number | null;
  y: number | null;
  heading_rad: number | null;
  severity?: string;
  symbol?: string;
  color?: string;
  source_id?: string;
  source_type?: string;
  related_channels?: string[];
  confidence?: string;
  start_pct?: number;
  end_pct?: number;
  points?: Array<{ x: number; y: number; pct: number }>;
}

export interface TrackMapTargetZone {
  start_pct: number;
  end_pct: number;
  start_distance_ft?: number;
  end_distance_ft?: number;
  points?: Array<{ x: number; y: number; pct: number }>;
  label?: string;
}

export interface TrackMapPackage {
  run_id: string;
  lap: number | null;
  map: TrackMap | null;
  match: TrackMapIndexEntry | null;
  overlays: TrackMapOverlayMarker[];
  sections: TrackMapSection[];
  markers: TrackMapMarker[];
  target_zone: TrackMapTargetZone | null;
  warnings: string[];
}
