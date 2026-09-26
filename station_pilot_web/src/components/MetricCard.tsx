import { ArrowDownRight, ArrowRight, ArrowUpRight, type LucideIcon } from "lucide-react";
import { formatNumber } from "../lib/format";

export interface MetricDelta {
  /** Variation en % par rapport à la période de comparaison. */
  percentage: number;
  /** Libellé de la période comparée, ex. « vs juillet 2026 ». */
  label: string;
  /** `false` quand une hausse est une mauvaise nouvelle (dépenses). */
  higherIsBetter?: boolean;
}

interface MetricCardProps {
  label: string;
  value: string;
  detail?: string;
  tone?: "green" | "red" | "blue" | "amber" | "neutral";
  icon?: LucideIcon;
  delta?: MetricDelta;
}

export function MetricCard({ label, value, detail, tone = "neutral", icon: Icon, delta }: MetricCardProps) {
  return (
    <div className={`metric-card tone-${tone}`}>
      <div className="metric-top">
        <span>{label}</span>
        {Icon && <Icon size={18} aria-hidden="true" />}
      </div>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
      {delta && <DeltaBadge {...delta} />}
    </div>
  );
}

function DeltaBadge({ percentage, label, higherIsBetter = true }: MetricDelta) {
  const flat = !Number.isFinite(percentage) || Math.abs(percentage) < 0.05;
  const rising = percentage > 0;
  const tone = flat ? "flat" : rising === higherIsBetter ? "up" : "down";
  const Icon = flat ? ArrowRight : rising ? ArrowUpRight : ArrowDownRight;

  return (
    <span className={`metric-delta ${tone}`}>
      <Icon size={13} aria-hidden="true" />
      {flat ? "stable" : `${rising ? "+" : "−"}${formatNumber(Math.abs(percentage), 1)} %`}
      <small>{label}</small>
    </span>
  );
}
