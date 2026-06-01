type ProxyBadgeProps = {
  kind: "proxy" | "estimate";
  title?: string;
};

export function ProxyBadge({ kind, title }: ProxyBadgeProps) {
  const isEstimate = kind === "estimate";
  const text = isEstimate ? "EST" : "PROXY";
  const ariaLabel = isEstimate ? "Estimate value" : "Proxy value";
  const defaultTitle = isEstimate
    ? "Estimate value - derived, not a direct measurement"
    : "Proxy value - inferred from related channels";
  const cls = isEstimate ? "proxy-badge estimate-badge" : "proxy-badge";
  return (
    <span className={cls} aria-label={ariaLabel} title={title ?? defaultTitle}>
      {text}
    </span>
  );
}
