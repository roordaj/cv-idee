import { scaleLinear } from 'd3-scale';
import { formatPercent } from '../lib/format.ts';
import type { DonutSlice } from './Donut.tsx';

export function StackedShareBar({ slices }: { slices: readonly DonutSlice[] }) {
  const total = slices.reduce((s, x) => s + x.value, 0) || 1;
  const x = scaleLinear().domain([0, total]).range([0, 400]);
  const starts = slices.map((_, i) => slices.slice(0, i).reduce((a, b) => a + b.value, 0));
  const desc = slices.map((s) => `${s.label} ${formatPercent((s.value / total) * 100)}`).join(', ');
  return (
    <svg
      viewBox="0 0 400 16"
      width="100%"
      role="img"
      aria-label={`Aandelen: ${desc}`}
      style={{ display: 'block' }}
    >
      {slices.map((s, i) => {
        const x0 = x(starts[i] ?? 0);
        return (
          <rect
            key={s.key}
            data-testid={`share-${s.key}`}
            x={x0}
            y={0}
            width={Math.max(0, x((starts[i] ?? 0) + s.value) - x0)}
            height={16}
            fill={s.color}
          >
            <title>{`${s.label}: ${formatPercent((s.value / total) * 100)}`}</title>
          </rect>
        );
      })}
    </svg>
  );
}
