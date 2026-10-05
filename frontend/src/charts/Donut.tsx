import { formatPercent } from '../lib/format.ts';

export interface DonutSlice {
  key: string;
  label: string;
  value: number;
  color: string;
}

export interface DonutProps {
  slices: readonly DonutSlice[];
  centerLabel?: string;
  size?: number;
}

const R = 50;
const TAU = Math.PI * 2;

function arc(a0: number, a1: number): string {
  const p = (a: number) =>
    `${(60 + R * Math.sin(a)).toFixed(2)} ${(60 - R * Math.cos(a)).toFixed(2)}`;
  return `M${p(a0)}A${String(R)} ${String(R)} 0 ${a1 - a0 > Math.PI ? '1' : '0'} 1 ${p(a1)}`;
}

export function Donut({ slices, centerLabel, size = 140 }: DonutProps) {
  const total = slices.reduce((s, x) => s + x.value, 0);
  const starts = slices.map((_, i) => slices.slice(0, i).reduce((a, b) => a + b.value, 0));
  const desc = slices
    .map((s) => `${s.label} ${formatPercent(total ? (s.value / total) * 100 : 0)}`)
    .join(', ');
  return (
    <svg
      viewBox="0 0 120 120"
      width={size}
      height={size}
      role="img"
      aria-label={`Verdeling: ${desc}`}
      style={{ display: 'block', fontFamily: 'inherit' }}
    >
      {total === 0 && (
        <circle cx={60} cy={60} r={R} fill="none" stroke="#eef0f3" strokeWidth={18} />
      )}
      {slices.map((s, i) => {
        if (s.value <= 0 || total === 0) return null;
        const a0 = ((starts[i] ?? 0) / total) * TAU;
        const a1 = Math.min((((starts[i] ?? 0) + s.value) / total) * TAU, a0 + TAU - 0.001);
        return (
          <path
            key={s.key}
            data-testid={`donut-${s.key}`}
            d={arc(a0, a1)}
            fill="none"
            stroke={s.color}
            strokeWidth={18}
          >
            <title>{`${s.label}: ${formatPercent((s.value / total) * 100)}`}</title>
          </path>
        );
      })}
      {centerLabel && (
        <text x={60} y={65} textAnchor="middle" fontSize={16} fontWeight={800} fill="#1d2433">
          {centerLabel}
        </text>
      )}
    </svg>
  );
}
