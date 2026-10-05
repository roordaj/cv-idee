import { scaleLinear } from 'd3-scale';
import { formatNumber } from '../lib/format.ts';
import { PALETTE, type Tone } from '../lib/semantics.ts';

export interface BeforeAfterBarsProps {
  label: string;
  before: number;
  after: number;
  unit?: string;
  decimals?: number;
  /** Tone of the "after" bar (judgement colour). */
  afterTone?: Tone;
}

export function BeforeAfterBars({
  label,
  before,
  after,
  unit = '',
  decimals = 1,
  afterTone = 'orange',
}: BeforeAfterBarsProps) {
  const max = Math.max(before, after, 0) || 1;
  const w = scaleLinear().domain([0, max]).range([0, 300]);
  const rows = [
    { name: 'Voor', value: before, fill: PALETTE.slate.base },
    { name: 'Na', value: after, fill: PALETTE[afterTone].base },
  ];
  const fmt = (v: number) => `${formatNumber(v, decimals)}${unit ? ` ${unit}` : ''}`;
  return (
    <svg
      viewBox="0 0 440 64"
      width="100%"
      role="img"
      aria-label={`${label}: voor ${fmt(before)}, na ${fmt(after)}`}
      style={{ display: 'block', fontFamily: 'inherit' }}
    >
      {rows.map((r, i) => (
        <g key={r.name} transform={`translate(0 ${String(i * 32)})`}>
          <text x={0} y={19} fontSize={12} fontWeight={600} fill="#3d4452">
            {r.name}
          </text>
          <rect x={40} y={6} width={Math.max(2, w(r.value))} height={20} rx={5} fill={r.fill} />
          <text
            x={40 + Math.max(2, w(r.value)) + 8}
            y={20}
            fontSize={12}
            fontWeight={700}
            fill="#1d2433"
          >
            {fmt(r.value)}
          </text>
        </g>
      ))}
    </svg>
  );
}
