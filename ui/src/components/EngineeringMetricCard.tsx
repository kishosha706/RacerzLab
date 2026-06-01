/** Reusable metric card for engineering panels. */
import { ProxyBadge } from "./ProxyBadge";
import { RiskBar } from "./RiskBar";
import { ValueDisplay } from "./ValueDisplay";
import { isMissingValue, displayUnavailable, getChannelUiMeta } from "../utils/channelMeta";

type MetricCardProps = {
  title: string;
  value: string | number | null | undefined;
  subtitle?: string;
  isProxy?: boolean;
  /** Channel name for metadata lookup (label, unit, disclaimer) */
  channelName?: string;
  riskValue?: number | null;
  children?: React.ReactNode;
  className?: string;
  color?: string;
  missingReason?: string;
};

export function EngineeringMetricCard({
  title, value, subtitle, isProxy, channelName, riskValue, children, className, color, missingReason,
}: MetricCardProps) {
  const meta = channelName ? getChannelUiMeta(channelName) : null;
  const showProxy = isProxy || meta?.isProxy || false;
  const showEstimate = !showProxy && (meta?.isEstimate || false);
  const disclaimer = meta?.warning ?? undefined;
  const isMissing = value == null || value === "" || (typeof value === "number" && (Number.isNaN(value) || !Number.isFinite(value))) || isMissingValue(value);
  return (
    <div className={`engineering-metric-card${className ? ` ${className}` : ""}${isMissing ? " metric-card-missing" : ""}`}
      style={color ? { borderLeftColor: isMissing ? "#475569" : color } : undefined}>
      <div className="metric-card-header">
        <span className="metric-card-title">{title}</span>
        {showProxy && !isMissing && <ProxyBadge kind="proxy" title={disclaimer} />}
        {showEstimate && !isMissing && <ProxyBadge kind="estimate" title={disclaimer} />}
      </div>
      <div className="metric-card-value" style={color && !isMissing ? { color } : undefined}>
        <ValueDisplay value={value} missingReason={missingReason} fallback={displayUnavailable(missingReason)} />
      </div>
      {subtitle && !isMissing && <div className="metric-card-subtitle">{subtitle}</div>}
      {riskValue != null && !isMissing && <RiskBar value={riskValue} />}
      {children}
    </div>
  );
}
