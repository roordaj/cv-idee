import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { TimelineData } from './common.ts';
import {
  BeforeAfterBars,
  CoverageBar,
  Donut,
  Legend,
  MiniTimeline,
  StackedShareBar,
  TimelineChart,
} from './index.ts';

const base = Date.parse('2026-10-04T06:00:00Z');
const iso = (min: number) => new Date(base + min * 60_000).toISOString();

const cycle1: TimelineData['cycles'][number] = {
  number: 1,
  start: iso(10),
  end: iso(30),
  duration_s: 1200,
  duration_is_lower_bound: false,
  mode: 'ch',
  end_reason: 'demand_ended',
  max_flow_temperature: 55,
  flow_setpoint: 50,
  mean_modulation_pct: 40,
  short_during_demand: false,
  classification: 'normal',
};
const cycle2: TimelineData['cycles'][number] = {
  ...cycle1,
  number: 2,
  start: iso(40),
  end: iso(44),
  mode: 'dhw',
  end_reason: 'dhw_ended',
};

const data: TimelineData = {
  range: { start: iso(0), end: iso(360) },
  series: {
    start: iso(0),
    step_s: 300,
    flow_temperature: [40, 50, null, 55, 45],
    return_temperature: [35, 38, null, 40, 36],
    flow_setpoint: [50, 50, 50, 50, 50],
    modulation_pct: [20, 60, null, 80, 30],
  },
  modes: [
    { start: iso(0), end: iso(100), mode: 'ch' },
    { start: iso(100), end: iso(200), mode: 'unknown' },
  ],
  heat_demand: [{ start: iso(0), end: iso(100), heat_demand: 'yes' }],
  cycles: [cycle1, cycle2],
  gaps: [{ start: iso(250), end: iso(280) }],
  changes: [
    {
      id: 'W-08',
      at: iso(120),
      parameter: 'Maximale CV-aanvoer',
      old_value: '60',
      new_value: '70',
      actor: 'gebruiker',
      verdict: 'pending',
      verdict_text: 'Evaluatie loopt',
    },
  ],
  last_change_before: null,
  periods: [{ id: 'P-1', kind: 'maintenance', start: iso(300), end: iso(330) }],
};

describe('TimelineChart', () => {
  it('renders lanes, gap text, change flag and period band', () => {
    render(<TimelineChart data={data} />);
    for (const t of ['Wijzigingen', 'Modus', 'Warmtevraag', 'Brander', 'Temperatuur', 'Modulatie'])
      expect(screen.getByText(t)).toBeTruthy();
    expect(screen.getByText('Geen gegevens')).toBeTruthy();
    expect(screen.getByText('telt als onbekend')).toBeTruthy();
    expect(screen.getAllByText('Onderhoud').length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: /Wijziging W-08/ })).toHaveLength(1);
  });

  it('calls back on cycle click and highlights the selection', () => {
    const onSelect = vi.fn();
    const { rerender } = render(<TimelineChart data={data} onSelectCycle={onSelect} />);
    expect(screen.queryByTestId('cycle-selection')).toBeNull();
    fireEvent.click(screen.getByTestId('cycle-2'));
    expect(onSelect).toHaveBeenCalledWith(2);
    rerender(<TimelineChart data={data} selectedCycle={2} onSelectCycle={onSelect} />);
    expect(screen.getByTestId('cycle-selection')).toBeTruthy();
  });

  it('colours cycles by kind and calls back on change click', () => {
    const onChange = vi.fn();
    const withShort = { ...data, cycles: [{ ...cycle1, short_during_demand: true }, cycle2] };
    render(<TimelineChart data={withShort} onSelectChange={onChange} />);
    expect(screen.getByTestId('cycle-1').getAttribute('fill')).toBe('#e0475b');
    expect(screen.getByTestId('cycle-2').getAttribute('fill')).toBe('#3b7ddd');
    fireEvent.click(screen.getByRole('button', { name: /Wijziging W-08/ }));
    expect(onChange).toHaveBeenCalledWith('W-08');
  });

  it('omits the change lane without changes and renders no gap', () => {
    render(<TimelineChart data={{ ...data, changes: [], gaps: [] }} />);
    expect(screen.queryByText('Wijzigingen')).toBeNull();
    expect(screen.queryByTestId('data-gap')).toBeNull();
  });
});

describe('other charts', () => {
  it('MiniTimeline renders gap and change marker', () => {
    render(<MiniTimeline data={data} />);
    expect(screen.getByTestId('mini-gap')).toBeTruthy();
    expect(screen.getByText(/Wijziging W-08 om/)).toBeTruthy();
  });
  it('BeforeAfterBars has an aria label', () => {
    render(<BeforeAfterBars label="Starts per uur" before={4} after={2.5} />);
    expect(screen.getByRole('img', { name: /voor 4,0, na 2,5/ })).toBeTruthy();
  });
  it('CoverageBar scales the fill', () => {
    render(<CoverageBar coveragePct={50} />);
    expect(screen.getByTestId('coverage-fill').getAttribute('width')).toBe('200');
  });
  it('Donut and StackedShareBar render slices', () => {
    const slices = [
      { key: 'a', label: 'CV', value: 3, color: '#ea6a2f' },
      { key: 'b', label: 'Tapwater', value: 1, color: '#3b7ddd' },
    ];
    render(
      <>
        <Donut slices={slices} centerLabel="75%" />
        <StackedShareBar slices={slices} />
      </>,
    );
    expect(screen.getByTestId('donut-a')).toBeTruthy();
    expect(screen.getByTestId('share-b').getAttribute('width')).toBe('100');
  });
  it('Legend lists items and can hide some', () => {
    render(<Legend hide={['change']} />);
    expect(screen.getByText('Gewenste aanvoer')).toBeTruthy();
    expect(screen.queryByText('Wijziging')).toBeNull();
  });
});
