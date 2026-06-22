type PlatformReadoutPanel = {
  row: {
    label: string;
    yAxisUnit?: string;
  };
  layout: {
    top: number;
    height: number;
  };
  channels: Array<{
    name: string;
    label: string;
    color: string;
    readoutLabel: string;
    cursorValue: number | null;
    low: number | null;
    high: number | null;
    avg: number | null;
  }>;
};

type PlatformChartPanelReadoutProps = {
  panels: PlatformReadoutPanel[];
  gridLeft: number;
  hasExplicitReadoutContext: boolean;
  readoutSource: string;
  readoutSourceLabel: string;
  locationSummary: string | null;
  eventTitle: string | null;
  lockedSummary: string | null;
};

export function fmtReadout(value: number | null | undefined, digits = 2, unit?: string): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value.toFixed(digits)}${unit ? ` ${unit}` : ""}`;
}

function panelDigits(unit?: string): number {
  return unit === "in" ? 2 : 3;
}

export function PlatformChartPanelReadout({
  panels,
  gridLeft,
  hasExplicitReadoutContext,
  readoutSource,
  readoutSourceLabel,
  locationSummary,
  eventTitle,
  lockedSummary,
}: PlatformChartPanelReadoutProps) {
  return (
    <div className="balance-panel-readout-layer" aria-live="polite">
      {panels.map((panel, panelIndex) => {
        const digits = panelDigits(panel.row.yAxisUnit);
        return (
          <div
            className="balance-panel-readout"
            key={panel.row.label}
            style={{
              top: panel.layout.top,
              height: panel.layout.height,
              left: gridLeft + 8,
            }}
          >
            <div className="balance-panel-cursor-readout">
              {hasExplicitReadoutContext ? (
                <>
                  <span
                    className={`cursor-source-badge source-${readoutSource.toLowerCase()}`}
                    title={readoutSource === "Locked" ? "Press Esc to unlock hover" : undefined}
                    aria-label={readoutSource === "Locked" ? "Locked cursor. Press Escape to unlock hover." : undefined}
                  >
                    {readoutSourceLabel}
                  </span>
                  {panelIndex === 0 && locationSummary && (
                    <span className="balance-selected-context">{locationSummary}</span>
                  )}
                  {panel.channels.map((channel) => (
                    <span className="balance-channel-current" key={channel.name} style={{ color: channel.color }}>
                      <span>{channel.readoutLabel}</span>
                      <strong>{fmtReadout(channel.cursorValue, digits)}</strong>
                    </span>
                  ))}
                  {panelIndex === 0 && eventTitle && (
                    <span className="balance-selected-context">Event {eventTitle}</span>
                  )}
                  {panelIndex === 0 && lockedSummary && (
                    <span className="balance-selected-context">{lockedSummary}</span>
                  )}
                </>
              ) : (
                <span className="balance-cursor-helper">Cursor: hover or scrub</span>
              )}
            </div>
            <div className="balance-panel-stat-readout" aria-label={`${panel.row.label} visible low high average statistics`}>
              {panel.channels.map((channel) => (
                <span className="balance-channel-stat-row" key={channel.name} style={{ color: channel.color }}>
                  <span className="balance-stat-channel">{channel.label}</span>
                  <span className="balance-stat-icon balance-stat-low" title="Lowest visible value" aria-label="Lowest visible value">▼</span>
                  <span>{fmtReadout(channel.low, digits)}</span>
                  <span className="balance-stat-icon balance-stat-high" title="Highest visible value" aria-label="Highest visible value">▲</span>
                  <span>{fmtReadout(channel.high, digits)}</span>
                  <span className="balance-stat-icon balance-stat-avg" title="Average visible value" aria-label="Average visible value">◆</span>
                  <span>{fmtReadout(channel.avg, digits)}</span>
                </span>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
