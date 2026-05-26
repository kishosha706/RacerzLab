type MetricCardProps = {
  label: string;
  value: string;
  tone?: "neutral" | "good" | "warn" | "danger";
};

export function MetricCard({ label, value, tone = "neutral" }: MetricCardProps) {
  return (
    <section className={`metric-card tone-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </section>
  );
}
