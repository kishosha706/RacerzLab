export type TrackMapTurnBounds = {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  width: number;
  height: number;
};

export type TrackMapTurnLabelLayout = {
  labelX: number;
  labelY: number;
  leaderEndX: number;
  leaderEndY: number;
  markerRadius: number;
  fontSize: number;
  textAnchor: "start" | "middle" | "end";
};

type TrackMapTurnLayoutOptions = {
  labelOffsetRatio: number;
  fontSizeRatio: number;
  markerRadiusRatio: number;
};

export function layoutTrackMapTurnLabel(
  point: { x: number; y: number },
  bounds: TrackMapTurnBounds,
  options: TrackMapTurnLayoutOptions,
): TrackMapTurnLabelLayout {
  const centerX = (bounds.minX + bounds.maxX) / 2;
  const centerY = (bounds.minY + bounds.maxY) / 2;
  const deltaX = point.x - centerX;
  const deltaY = point.y - centerY;
  const distance = Math.hypot(deltaX, deltaY);
  const unitX = distance > 0 ? deltaX / distance : Math.SQRT1_2;
  const unitY = distance > 0 ? deltaY / distance : -Math.SQRT1_2;
  const maxDimension = Math.max(bounds.width, bounds.height);
  const labelOffset = maxDimension * options.labelOffsetRatio;

  return {
    labelX: point.x + unitX * labelOffset,
    labelY: point.y + unitY * labelOffset,
    leaderEndX: point.x + unitX * labelOffset * 0.72,
    leaderEndY: point.y + unitY * labelOffset * 0.72,
    markerRadius: maxDimension * options.markerRadiusRatio,
    fontSize: maxDimension * options.fontSizeRatio,
    textAnchor: unitX > 0.25 ? "start" : unitX < -0.25 ? "end" : "middle",
  };
}
