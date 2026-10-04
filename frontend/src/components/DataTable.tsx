import type { KeyboardEvent, ReactNode } from 'react';
import styles from './DataTable.module.css';
import { cx } from './tone.ts';

export interface DataTableColumn<Row> {
  key: string;
  header: string;
  render: (row: Row) => ReactNode;
  align?: 'left' | 'right';
  /** Muted cell text (e.g. row number). */
  muted?: boolean;
  /** Bold cell text (e.g. start time). */
  strong?: boolean;
}

export interface DataTableProps<Row> {
  columns: readonly DataTableColumn<Row>[];
  rows: readonly Row[];
  getRowKey: (row: Row) => string;
  /** Accessible table caption; visually hidden unless `showCaption`. */
  caption: string;
  showCaption?: boolean;
  /** Makes rows selectable (click, Enter or Space). */
  onRowSelect?: (row: Row) => void;
  selectedKey?: string | null;
  className?: string;
}

export function DataTable<Row>({
  columns,
  rows,
  getRowKey,
  caption,
  showCaption = false,
  onRowSelect,
  selectedKey = null,
  className,
}: DataTableProps<Row>) {
  const onKeyDown = (event: KeyboardEvent<HTMLTableRowElement>, row: Row) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onRowSelect?.(row);
    }
  };

  return (
    <div className={cx(styles.wrapper, className)}>
      <table className={styles.table}>
        <caption className={showCaption ? styles.caption : 'visually-hidden'}>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={column.align === 'right' ? styles.right : undefined}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const key = getRowKey(row);
            const selected = key === selectedKey;
            const interactive = onRowSelect !== undefined;
            return (
              <tr
                key={key}
                className={cx(interactive && styles.interactive, selected && styles.selected)}
                {...(interactive
                  ? {
                      tabIndex: 0,
                      'aria-selected': selected,
                      onClick: () => {
                        onRowSelect(row);
                      },
                      onKeyDown: (event: KeyboardEvent<HTMLTableRowElement>) => {
                        onKeyDown(event, row);
                      },
                    }
                  : {})}
              >
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={cx(
                      column.align === 'right' && styles.right,
                      column.muted && styles.muted,
                      column.strong && styles.strong,
                    )}
                  >
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
