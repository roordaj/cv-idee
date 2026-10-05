import { scaleLinear, scaleTime } from 'd3-scale';
import { useId } from 'react';
import { formatTime } from '../lib/format.ts';
import { CHART_COLORS } from '../lib/semantics.ts';
import { cycleColor, type TimelineData } from './common.ts';

const W = 600;

export function MiniTimeline({ data }: { data: TimelineData }) {
  const hatch = `mh-${useId().replace(/:/g, '')}`;
  const t0 = new Date(data.range.start);
  const t1 = data.range.end ? new Date(data.range.end) : new Date(t0.getTime() + 6 * 3600_000);
  const x = scaleTime().domain([t0, t1]).range([0, W]);
  const X = (iso: string) => x(new Date(iso));
  const ty = scaleLinear().domain([30, 75]).range([78, 34]);
  const { series } = data;
  const sx = new Date(series.start).getTime();
  let d = '';
  let pen = false;
  series.flow_temperature.forEach((v, i) => {
    if (v == null) {
      pen = false;
      return;
    }
    d += `${pen ? 'L' : 'M'}${x(new Date(sx + i * series.step_s * 1000)).toFixed(1)} ${ty(v).toFixed(1)}`;
    pen = true;
  });
  const span = t1.getTime() - t0.getTime();
  const ticks = [0, 1 / 3, 2 / 3, 1].map((f) => new Date(t0.getTime() + f * span));
  return (
    <svg
      viewBox={`0 0 ${String(W)} 100`}
      width="100%"
      role="img"
      aria-label={`Mini-tijdlijn met ${String(data.cycles.length)} cycli`}
      style={{ display: 'block', fontFamily: 'inherit' }}
    >
      <defs>
        <pattern
          id={hatch}
          width={6}
          height={6}
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(45)"
        >
          <rect width={2} height={6} fill={CHART_COLORS.noDataStripe} />
        </pattern>
      </defs>
      {data.gaps.map((g) => (
        <rect
          key={g.start}
          data-testid="mini-gap"
          x={X(g.start)}
          y={0}
          width={(g.end ? X(g.end) : W) - X(g.start)}
          height={82}
          rx={6}
          fill={`url(#${hatch})`}
        />
      ))}
      {data.cycles.map((c) => (
        <rect
          key={c.number}
          x={X(c.start)}
          y={2}
          width={Math.max(2.5, (c.end ? X(c.end) : W) - X(c.start))}
          height={18}
          rx={2}
          fill={cycleColor(c)}
        />
      ))}
      <path d={d} fill="none" stroke={CHART_COLORS.flow} strokeWidth={2} strokeLinejoin="round" />
      {data.changes.map((c) => (
        <g key={c.id}>
          <title>{`Wijziging ${c.id} om ${formatTime(new Date(c.at))}`}</title>
          <line
            x1={X(c.at)}
            x2={X(c.at)}
            y1={0}
            y2={82}
            stroke="#3d4452"
            strokeWidth={1.5}
            opacity={0.6}
          />
          <path d={`M${String(X(c.at) - 3)} 0h6l-3 6z`} fill="#1d2433" />
        </g>
      ))}
      {ticks.map((t, i) => (
        <text
          key={t.getTime()}
          x={x(t)}
          y={96}
          textAnchor={i === 0 ? 'start' : i === 3 ? 'end' : 'middle'}
          fontSize={11}
          fill="#8a92a3"
        >
          {formatTime(t)}
        </text>
      ))}
    </svg>
  );
}
