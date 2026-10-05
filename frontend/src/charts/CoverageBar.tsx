import { useId } from 'react';
import { formatPercent } from '../lib/format.ts';
import { CHART_COLORS, PALETTE } from '../lib/semantics.ts';

export interface CoverageBarProps {
  /** Share of time with data, 0-100. */
  coveragePct: number;
  label?: string;
}

export function CoverageBar({ coveragePct, label = 'Dekking' }: CoverageBarProps) {
  const hatch = `cov-${useId().replace(/:/g, '')}`;
  const pct = Math.min(100, Math.max(0, coveragePct));
  return (
    <svg
      viewBox="0 0 400 14"
      width="100%"
      role="img"
      aria-label={`${label}: ${formatPercent(pct)} met gegevens, ${formatPercent(100 - pct)} onbekend`}
      style={{ display: 'block' }}
    >
      <defs>
        <pattern
          id={hatch}
          width={6}
          height={6}
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(45)"
        >
          <rect width={6} height={6} fill={CHART_COLORS.noDataBackground} />
          <rect width={2} height={6} fill={CHART_COLORS.noDataStripe} />
        </pattern>
      </defs>
      <rect width={400} height={14} rx={7} fill={`url(#${hatch})`} />
      <rect
        data-testid="coverage-fill"
        width={(pct / 100) * 400}
        height={14}
        rx={7}
        fill={PALETTE.green.base}
      />
    </svg>
  );
}
