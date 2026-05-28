/** Small badge indicating a value is a proxy/estimate. */
type ProxyBadgeProps = {
  label?: string;
  /** If true, shows "ESTIMATE" instead of "PROXY" */
  isEstimate?: boolean;
  /** Optional tooltip/disclaimer text */
  disclaimer?: string;
};

export function ProxyBadge({ label, isEstimate, disclaimer }: ProxyBadgeProps) {
  const text = label ?? (isEstimate ? "ESTIMATE" : "PROXY");
  const cls = isEstimate ? "proxy-badge estimate-badge" : "proxy-badge";
  return (
    <span className={cls} title={disclaimer ?? (isEstimate ? "Derived value — not a direct measurement" : "Proxy value — inferred from related channels")}>
      {text}
    </span>
  );
}

