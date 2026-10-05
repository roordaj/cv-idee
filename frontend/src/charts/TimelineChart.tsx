import { scaleLinear, scaleTime } from 'd3-scale';
import { useId, type KeyboardEvent } from 'react';
import { formatTime } from '../lib/format.ts';
import { CHART_COLORS, FLOW_SETPOINT_DASH } from '../lib/semantics.ts';
import { cycleColor, MODE_FILL, PERIOD_LABEL, type TimelineData } from './common.ts';

export interface TimelineChartProps {
  data: TimelineData;
  selectedCycle?: number | null;
  onSelectCycle?: (cycleNumber: number) => void;
  onSelectChange?: (changeId: string) => void;
}

const W = 1120;
const L = 120;
const R0 = W - 8;
const CHANGE_LANE = 26;

function ts(iso: string): number {
  return new Date(iso).getTime();
}

function onActivate(fn: () => void) {
  return (e: KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fn();
    }
  };
}

export function TimelineChart({
  data,
  selectedCycle = null,
  onSelectCycle,
  onSelectChange,
}: TimelineChartProps) {
  const uid = useId().replace(/:/g, '');
  const hatch = `hatch-${uid}`;
  const t0 = ts(data.range.start);
  const t1 = data.range.end ? ts(data.range.end) : t0 + 6 * 3600_000;
  const off = data.changes.length > 0 ? CHANGE_LANE : 0;
  const H = 410 + off;
  const x = scaleTime()
    .domain([new Date(t0), new Date(t1)])
    .range([L, R0]);
  const X = (iso: string | number) => x(new Date(iso));
  const ty = scaleLinear()
    .domain([25, 75])
    .range([300 + off, 124 + off]);
  const my = scaleLinear()
    .domain([0, 100])
    .range([380 + off, 334 + off]);

  const { series } = data;
  const step = series.step_s * 1000;
  const sx = ts(series.start);
  const line = (values: (number | null)[], scale: (v: number) => number) => {
    let d = '';
    let pen = false;
    values.forEach((v, i) => {
      if (v == null) {
        pen = false;
        return;
      }
      d += `${pen ? 'L' : 'M'}${X(sx + i * step).toFixed(1)} ${scale(v).toFixed(1)}`;
      pen = true;
    });
    return d;
  };

  const ticks = x.ticks(6);
  const lbl = (y: number, text: string) => (
    <text x={0} y={y + off} fontSize={12} fontWeight={600} fill="#3d4452">
      {text}
    </text>
  );
  const sel = data.cycles.find((c) => c.number === selectedCycle);
  const cycleEnd = (c: (typeof data.cycles)[number]) => (c.end ? ts(c.end) : t1);
  const fillOf = (f: string) => (f === 'HATCH' ? `url(#${hatch})` : f);

  return (
    <svg
      viewBox={`0 0 ${String(W)} ${String(H)}`}
      width="100%"
      role="group"
      aria-label={`Tijdlijn met ${String(data.cycles.length)} cycli en ${String(data.changes.length)} wijzigingen`}
      style={{ display: 'block', fontFamily: 'inherit' }}
    >
      <title>{`Tijdlijn: ${String(data.cycles.length)} cycli, ${String(data.changes.length)} wijzigingen in beeld`}</title>
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
      {data.changes.length > 0 && (
        <text x={0} y={14} fontSize={12} fontWeight={600} fill="#3d4452">
          Wijzigingen
        </text>
      )}
      {lbl(29, 'Modus')}
      {lbl(59, 'Warmtevraag')}
      {lbl(91, 'Brander')}
      {lbl(140, 'Temperatuur')}
      {lbl(352, 'Modulatie')}

      {ticks.map((t) => (
        <g key={t.getTime()}>
          <line x1={x(t)} x2={x(t)} y1={10 + off} y2={384 + off} stroke="#eef0f3" />
          <text x={x(t)} y={402 + off} textAnchor="middle" fontSize={12} fill="#8a92a3">
            {formatTime(t)}
          </text>
        </g>
      ))}
      {[30, 40, 50, 60, 70].map((v) => (
        <g key={v}>
          <line x1={L} x2={R0} y1={ty(v)} y2={ty(v)} stroke="#eef0f3" />
          <text x={L - 8} y={ty(v) + 4} textAnchor="end" fontSize={11} fill="#8a92a3">
            {`${String(v)}°`}
          </text>
        </g>
      ))}

      {data.periods.map((p) => {
        const a = Math.max(X(p.start), L);
        const b = Math.min(p.end ? X(p.end) : R0, R0);
        const name = PERIOD_LABEL[p.kind] ?? p.kind;
        return (
          <g key={p.id}>
            <rect
              x={a}
              y={10 + off}
              width={Math.max(0, b - a)}
              height={374}
              fill="#fcf3dc"
              opacity={0.5}
            >
              <title>{name}</title>
            </rect>
            <text x={a + 4} y={22 + off} fontSize={10} fontWeight={700} fill="#8a6206">
              {name}
            </text>
          </g>
        );
      })}

      {data.modes.map((s) => (
        <rect
          key={s.start}
          x={X(s.start) + 1}
          y={16 + off}
          width={Math.max(0, X(s.end) - X(s.start) - 2)}
          height={18}
          rx={5}
          fill={fillOf(MODE_FILL[s.mode])}
        />
      ))}
      {data.heat_demand.map((s) => (
        <rect
          key={s.start}
          x={X(s.start) + 1}
          y={51 + off}
          width={Math.max(0, X(s.end) - X(s.start) - 2)}
          height={10}
          rx={5}
          fill={
            s.heat_demand === 'yes'
              ? '#5b6475'
              : s.heat_demand === 'unknown'
                ? `url(#${hatch})`
                : '#eef0f3'
          }
        />
      ))}

      {data.changes.map((c) => {
        const cx = X(c.at);
        const w = c.id.length * 7 + 16;
        const go = () => {
          onSelectChange?.(c.id);
        };
        const label = `Wijziging ${c.id}, ${formatTime(new Date(c.at))}: ${c.parameter} van ${c.old_value} naar ${c.new_value}. Open wijziging.`;
        return (
          <g
            key={c.id}
            role="button"
            tabIndex={0}
            aria-label={label}
            onClick={go}
            onKeyDown={onActivate(go)}
            style={{ cursor: 'pointer' }}
          >
            <title>{`${c.id} · ${formatTime(new Date(c.at))} · door ${c.actor}: ${c.parameter} ${c.old_value} → ${c.new_value}`}</title>
            <line
              x1={cx}
              x2={cx}
              y1={19}
              y2={384 + off}
              stroke="#3d4452"
              strokeWidth={1.5}
              opacity={0.6}
            />
            <rect x={cx - w / 2} y={1} width={w} height={18} rx={9} fill="#1d2433" />
            <text x={cx} y={14} textAnchor="middle" fontSize={11} fontWeight={700} fill="#fff">
              {c.id}
            </text>
            <rect x={cx - 8} y={0} width={16} height={384 + off} fill="transparent" />
          </g>
        );
      })}

      {data.cycles.map((c) => {
        const a = X(c.start);
        const go = () => {
          onSelectCycle?.(c.number);
        };
        return (
          <rect
            key={c.number}
            data-testid={`cycle-${String(c.number)}`}
            role="button"
            tabIndex={0}
            aria-label={`Cyclus ${String(c.number)}, ${formatTime(new Date(c.start))}${c.short_during_demand ? ', kort tijdens vraag' : ''}`}
            aria-pressed={c.number === selectedCycle}
            x={a}
            y={78 + off}
            width={Math.max(3, X(cycleEnd(c)) - a)}
            height={22}
            rx={3}
            fill={cycleColor(c)}
            style={{ cursor: 'pointer' }}
            onClick={go}
            onKeyDown={onActivate(go)}
          />
        );
      })}

      {data.gaps.map((g) => {
        const a = X(g.start);
        const b = g.end ? X(g.end) : R0;
        const mid = (a + b) / 2;
        return (
          <g key={g.start} data-testid="data-gap">
            <rect
              x={a}
              y={112 + off}
              width={b - a}
              height={272}
              rx={8}
              fill={`url(#${hatch})`}
              opacity={0.6}
            />
            <text
              x={mid}
              y={200 + off}
              textAnchor="middle"
              fontSize={11}
              fontWeight={700}
              fill="#3d4452"
            >
              Geen gegevens
            </text>
            <text x={mid} y={214 + off} textAnchor="middle" fontSize={11} fill="#5b6475">
              telt als onbekend
            </text>
          </g>
        );
      })}

      <path
        d={line(series.modulation_pct, my)}
        fill="none"
        stroke={CHART_COLORS.modulation}
        strokeWidth={1.5}
        strokeLinejoin="round"
      />
      <path
        d={line(series.flow_setpoint, ty)}
        fill="none"
        stroke={CHART_COLORS.flowSetpoint}
        strokeWidth={1.5}
        strokeDasharray={FLOW_SETPOINT_DASH}
      />
      <path
        d={line(series.return_temperature, ty)}
        fill="none"
        stroke={CHART_COLORS.return}
        strokeWidth={1.75}
        strokeLinejoin="round"
      />
      <path
        d={line(series.flow_temperature, ty)}
        fill="none"
        stroke={CHART_COLORS.flow}
        strokeWidth={2.25}
        strokeLinejoin="round"
      />

      {sel && (
        <rect
          data-testid="cycle-selection"
          x={X(sel.start) - 4}
          y={10 + off}
          width={Math.max(8, X(cycleEnd(sel)) - X(sel.start) + 8)}
          height={374}
          rx={6}
          fill="rgba(124,92,214,.08)"
          stroke={CHART_COLORS.selection}
          strokeWidth={2}
          pointerEvents="none"
        />
      )}
    </svg>
  );
}
