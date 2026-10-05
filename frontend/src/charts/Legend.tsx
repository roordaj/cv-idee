import type { ReactNode } from 'react';
import { NO_DATA_PATTERN } from '../lib/semantics.ts';

import { CYCLE_LEGEND, type LegendItem } from './legendItems.ts';

function Swatch({ item }: { item: LegendItem }): ReactNode {
  const color = item.color ?? '#3d4452';
  switch (item.swatch) {
    case 'box':
      return <span style={{ width: 12, height: 12, borderRadius: 3, background: color }} />;
    case 'line':
      return <span style={{ width: 16, height: 3, borderRadius: 2, background: color }} />;
    case 'dashed':
      return <span style={{ width: 16, height: 0, borderTop: `2px dashed ${color}` }} />;
    case 'hatch':
      return (
        <span style={{ width: 14, height: 12, borderRadius: 3, background: NO_DATA_PATTERN }} />
      );
    case 'change':
      return (
        <span style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center' }}>
          <span style={{ width: 10, height: 6, background: '#1d2433', borderRadius: 2 }} />
          <span style={{ width: 2, height: 12, background: '#3d4452' }} />
        </span>
      );
  }
}

export interface LegendProps {
  items?: readonly LegendItem[];
  /** Keys to hide (e.g. 'change' when there are no changes in range). */
  hide?: readonly string[];
  label?: string;
}

export function Legend({ items = CYCLE_LEGEND, hide = [], label = 'Legenda' }: LegendProps) {
  return (
    <ul
      aria-label={label}
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '6px 16px',
        listStyle: 'none',
        margin: 0,
        padding: 0,
        fontSize: 12,
        color: '#5b6475',
      }}
    >
      {items
        .filter((i) => !hide.includes(i.key))
        .map((i) => (
          <li key={i.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <Swatch item={i} />
            {i.label}
          </li>
        ))}
    </ul>
  );
}
