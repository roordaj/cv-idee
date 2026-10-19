import { scaleLinear, scaleTime } from 'd3-scale';
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { formatDateLong, formatDayMonth, formatTime } from '../lib/format.ts';
import { CHART_COLORS, FLOW_SETPOINT_DASH } from '../lib/semantics.ts';
import { Pill } from '../components/Tag.tsx';
import { cycleColor, MODE_FILL, PERIOD_LABEL, type TimelineData } from './common.ts';
import styles from './TimelineChart.module.css';

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
const CHANGE_TONES = {
  improved: 'green',
  worsened: 'rose',
  trade_off: 'rose',
  not_attributable: 'amber',
  insufficient_evidence: 'slate',
  pending: 'slate',
} as const;

type ChangeMarker = TimelineData['changes'][number];
type ChangeGroup = { key: string; changes: ChangeMarker[]; x: number };

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

function changeLabel(change: TimelineData['changes'][number]): string {
  return `Wijziging ${change.id}, ${formatDateLong(new Date(change.at))} ${formatTime(new Date(change.at))}: ${change.parameter} van ${change.old_value} naar ${change.new_value}. Open wijziging.`;
}

function actorLabel(actor: string): string {
  if (actor === 'user') return 'gebruiker';
  if (actor === 'installer') return 'installateur';
  return 'anders';
}

export function TimelineChart({
  data,
  selectedCycle = null,
  onSelectCycle,
  onSelectChange,
}: TimelineChartProps) {
  const uid = useId().replace(/:/g, '');
  const plotRef = useRef<HTMLDivElement>(null);
  const firstMenuActionRef = useRef<HTMLButtonElement>(null);
  const [plotWidth, setPlotWidth] = useState(() =>
    typeof window === 'undefined' ? W : window.innerWidth,
  );
  const [activeGroup, setActiveGroup] = useState<string | null>(null);
  const [menuGroup, setMenuGroup] = useState<string | null>(null);
  const [lastTappedGroup, setLastTappedGroup] = useState<string | null>(null);
  useEffect(() => {
    if (menuGroup) firstMenuActionRef.current?.focus();
  }, [menuGroup]);
  useEffect(() => {
    const plot = plotRef.current;
    if (!plot) return;
    if (typeof ResizeObserver === 'undefined') {
      setPlotWidth(plot.clientWidth || window.innerWidth);
      return;
    }
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setPlotWidth(entry.contentRect.width);
    });
    observer.observe(plot);
    return () => {
      observer.disconnect();
    };
  }, []);
  const hatch = `hatch-${uid}`;
  const t0 = ts(data.range.start);
  const t1 = data.range.end ? ts(data.range.end) : t0 + 6 * 3600_000;
  const off = data.changes.length > 0 ? CHANGE_LANE : 0;
  const H = 410 + off;
  const x = scaleTime()
    .domain([new Date(t0), new Date(t1)])
    .range([L, R0]);
  const X = (iso: string | number) => x(new Date(iso));
  const changes = [...data.changes].sort((a, b) => ts(a.at) - ts(b.at));
  const groups = changes.reduce<ChangeGroup[]>((result, change) => {
    const changeX = X(change.at);
    const previous = result[result.length - 1];
    const previousChange = previous?.changes[previous.changes.length - 1];
    if (
      previous &&
      previousChange &&
      Math.abs(changeX - X(previousChange.at)) * (plotWidth / W) < 40
    ) {
      previous.changes.push(change);
      previous.key = previous.changes.map((item) => item.id).join('|');
      previous.x =
        previous.changes.reduce((sum, item) => sum + X(item.at), 0) / previous.changes.length;
    } else {
      result.push({ key: change.id, changes: [change], x: changeX });
    }
    return result;
  }, []);
  const selectedGroup = groups.find((group) => group.key === activeGroup);
  const isNarrow = plotWidth < 600;
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
    <div
      ref={plotRef}
      className={styles.plot}
      style={{ paddingTop: selectedGroup ? 96 : 0 }}
      onMouseLeave={() => {
        if (!plotRef.current?.contains(document.activeElement)) {
          setActiveGroup(null);
          setMenuGroup(null);
        }
      }}
    >
      {selectedGroup && (
        <div
          id={`change-tooltip-${uid}`}
          role="group"
          aria-label={`Details van ${String(selectedGroup.changes.length)} ${selectedGroup.changes.length === 1 ? 'wijziging' : 'wijzigingen'}`}
          className={styles.tooltip}
          style={{
            left: Math.max(8, Math.min(plotWidth - 288, (selectedGroup.x / W) * plotWidth - 140)),
          }}
        >
          {selectedGroup.changes.map((change) => (
            <div className={styles.tooltipItem} key={change.id}>
              <div className={styles.meta}>
                {`${change.id} · ${formatDayMonth(new Date(change.at))} ${formatTime(new Date(change.at))} · door ${actorLabel(change.actor)}`}
              </div>
              <div className={styles.changeText}>
                {`${change.parameter}: ${change.old_value} → ${change.new_value}`}
              </div>
              <Pill tone={CHANGE_TONES[change.verdict]} size="sm">
                {change.verdict_text}
              </Pill>
              {selectedGroup.changes.length === 1 && (
                <button
                  type="button"
                  className={styles.action}
                  onClick={() => onSelectChange?.(change.id)}
                >
                  Klik om de wijziging te openen
                </button>
              )}
            </div>
          ))}
          {selectedGroup.changes.length > 1 && menuGroup === selectedGroup.key && (
            <div className={styles.actions} aria-label="Wijziging openen">
              {selectedGroup.changes.map((change, index) => (
                <button
                  type="button"
                  className={styles.action}
                  key={change.id}
                  ref={index === 0 ? firstMenuActionRef : undefined}
                  onClick={() => onSelectChange?.(change.id)}
                >
                  {`Open wijziging ${change.id} · ${change.parameter}`}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
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

        {changes.map((change) => {
          const changeX = X(change.at);
          const group = groups.find((item) =>
            item.changes.some((member) => member.id === change.id),
          );
          const active = group?.key === activeGroup;
          return (
            <line
              key={`${change.id}-line`}
              x1={changeX}
              x2={changeX}
              y1={19}
              y2={384 + off}
              stroke="#3d4452"
              strokeWidth={active ? 2 : 1.5}
              opacity={active ? 1 : 0.6}
              pointerEvents="none"
            />
          );
        })}
        {groups.map((group) => {
          const first = group.changes[0];
          if (!first) return null;
          const label =
            group.changes.length === 1
              ? changeLabel(first)
              : `${String(group.changes.length)} wijzigingen: ${group.changes.map(changeLabel).join(' ')}`;
          const activatePointer = () => {
            if (group.changes.length > 1) {
              setLastTappedGroup(null);
              setActiveGroup(group.key);
              setMenuGroup(group.key);
            } else if (isNarrow && lastTappedGroup !== group.key) {
              setLastTappedGroup(group.key);
              setActiveGroup(group.key);
              setMenuGroup(null);
            } else {
              setLastTappedGroup(null);
              onSelectChange?.(first.id);
            }
          };
          const activateKeyboard = () => {
            setLastTappedGroup(null);
            if (group.changes.length > 1) {
              setActiveGroup(group.key);
              setMenuGroup(group.key);
            } else {
              onSelectChange?.(first.id);
            }
          };
          const flagWidth = group.changes.length === 1 ? first.id.length * 7 + 16 : 100;
          return (
            <g
              key={group.key}
              role="button"
              tabIndex={0}
              aria-label={label}
              aria-expanded={activeGroup === group.key}
              aria-describedby={activeGroup === group.key ? `change-tooltip-${uid}` : undefined}
              data-testid={`change-marker-${first.id}`}
              className={styles.marker}
              onMouseEnter={() => {
                if (!isNarrow) setActiveGroup(group.key);
              }}
              onFocus={() => {
                setActiveGroup(group.key);
              }}
              onBlur={(event) => {
                if (!plotRef.current?.contains(event.relatedTarget)) {
                  setActiveGroup(null);
                  setMenuGroup(null);
                }
              }}
              onClick={activatePointer}
              onKeyDown={onActivate(activateKeyboard)}
            >
              {isNarrow ? (
                <>
                  <circle cx={group.x} cy={10} r={6} fill="#1d2433" />
                  <text
                    x={group.x}
                    y={13}
                    textAnchor="middle"
                    fontSize={8}
                    fontWeight={700}
                    fill="#fff"
                    pointerEvents="none"
                  >
                    W
                  </text>
                </>
              ) : (
                <>
                  <rect
                    x={group.x - flagWidth / 2}
                    y={1}
                    width={flagWidth}
                    height={18}
                    rx={9}
                    fill="#1d2433"
                  />
                  <text
                    x={group.x}
                    y={14}
                    textAnchor="middle"
                    fontSize={11}
                    fontWeight={700}
                    fill="#fff"
                    pointerEvents="none"
                  >
                    {group.changes.length === 1
                      ? first.id
                      : `${String(group.changes.length)} wijzigingen`}
                  </text>
                </>
              )}
              <rect x={group.x - 8} y={0} width={16} height={384 + off} fill="transparent" />
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
    </div>
  );
}
