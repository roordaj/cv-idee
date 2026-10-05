import { Plug, Search, X } from 'lucide-react';
import { useId, useMemo, useState, type KeyboardEvent } from 'react';
import { useHaEntities } from '../../api/hooks/signals.ts';
import { Button } from '../../components/Button.tsx';
import { Dialog } from '../../components/Dialog.tsx';
import { ErrorCallout } from '../../components/ErrorCallout.tsx';
import { ICON_SIZE } from '../../components/icons.ts';
import { SegmentedControl } from '../../components/SegmentedControl.tsx';
import { Skeleton, SkeletonGroup } from '../../components/Skeleton.tsx';
import { Pill } from '../../components/Tag.tsx';
import { cx } from '../../components/tone.ts';
import styles from './Signals.module.css';
import { fitsUnit, isUnavailable, normalise, type HaEntity, type Signal } from './signalFormat.ts';

const MAX_OPTIONS = 200;

export interface EntityPickerProps {
  open: boolean;
  signal: Signal;
  /** Entity currently chosen in the panel. */
  current: string | null;
  /** All signals, for "Al gekoppeld aan …". */
  signals: readonly Signal[];
  onClose: () => void;
  onPick: (entity: HaEntity) => void;
}

type Filter = 'fit' | 'all';

/** Searchable Home Assistant entity picker (docs/design/aanvullingen.md §3b). */
export function EntityPicker({
  open,
  signal,
  current,
  signals,
  onClose,
  onPick,
}: EntityPickerProps) {
  const listId = useId();
  const entities = useHaEntities();
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<Filter>('fit');
  const [active, setActive] = useState(0);
  const unit = signal.unit;

  const linkedTo = useMemo(() => {
    const map = new Map<string, string>();
    for (const s of signals) if (s.entity_id && s.id !== signal.id) map.set(s.entity_id, s.name);
    return map;
  }, [signals, signal.id]);

  const matches = useMemo(() => {
    const words = normalise(query).split(/\s+/).filter(Boolean);
    return (entities.data ?? [])
      .filter((e) => filter === 'all' || fitsUnit(unit, e))
      .filter((e) => {
        const haystack = normalise(`${e.id} ${e.friendly_name ?? ''}`);
        return words.every((w) => haystack.includes(w));
      })
      .sort((a, b) => {
        const fit = Number(fitsUnit(unit, b)) - Number(fitsUnit(unit, a));
        return fit || (a.friendly_name ?? a.id).localeCompare(b.friendly_name ?? b.id, 'nl');
      });
  }, [entities.data, query, filter, unit]);

  const shown = matches.slice(0, MAX_OPTIONS);
  const activeEntity = shown[Math.min(active, shown.length - 1)];
  const optionId = (index: number) => `${listId}-${String(index)}`;

  const choose = (entity: HaEntity | undefined) => {
    if (entity) onPick(entity);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    const last = shown.length - 1;
    const move = (to: number) => {
      event.preventDefault();
      setActive(Math.max(0, Math.min(last, to)));
    };
    switch (event.key) {
      case 'ArrowDown':
        move(active + 1);
        break;
      case 'ArrowUp':
        move(active - 1);
        break;
      case 'PageDown':
        move(active + 10);
        break;
      case 'PageUp':
        move(active - 10);
        break;
      case 'Home':
        if (event.ctrlKey) move(0);
        break;
      case 'End':
        if (event.ctrlKey) move(last);
        break;
      case 'Enter':
        event.preventDefault();
        choose(activeEntity);
        break;
      case 'Escape':
        if (query) {
          event.stopPropagation();
          setQuery('');
        }
        break;
      default:
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Entiteit kiezen"
      subtitle={`voor ${signal.name}${unit ? ` · verwacht ${unit}` : ''}`}
      icon={<Plug size={ICON_SIZE} aria-hidden="true" />}
      tone="teal"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Annuleren
          </Button>
          <Button
            disabled={!activeEntity}
            onClick={() => {
              choose(activeEntity);
            }}
          >
            Kiezen
          </Button>
        </>
      }
    >
      <div className={styles.pickerBody}>
        <div className={styles.searchWrap}>
          <Search size={16} className={styles.searchIcon} aria-hidden="true" />
          <input
            className={cx(styles.input, styles.search)}
            role="combobox"
            aria-label="Zoek op naam of entity_id"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={activeEntity ? optionId(shown.indexOf(activeEntity)) : undefined}
            placeholder="Zoek op naam of entity_id, bijv. aanvoer of remeha"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={onKeyDown}
          />
          {query ? (
            <button
              type="button"
              className={styles.clear}
              aria-label="Zoekopdracht wissen"
              onClick={() => {
                setQuery('');
              }}
            >
              <X size={16} aria-hidden="true" />
            </button>
          ) : null}
        </div>
        <div className={styles.filterRow}>
          <SegmentedControl
            label="Filter"
            value={filter}
            onChange={(next) => {
              setFilter(next);
              setActive(0);
            }}
            options={[
              { value: 'fit', label: unit ? `Passend (${unit})` : 'Passend' },
              { value: 'all', label: 'Alle entiteiten' },
            ]}
          />
          {entities.data ? <span>{matches.length} gevonden</span> : null}
        </div>
        {entities.isPending ? (
          <SkeletonGroup>
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} height={52} radius={12} />
            ))}
          </SkeletonGroup>
        ) : entities.isError ? (
          <ErrorCallout
            subject="de entiteiten uit Home Assistant"
            onRetry={() => {
              void entities.refetch();
            }}
          />
        ) : (
          <ul id={listId} role="listbox" aria-label="Entiteiten" className={styles.list}>
            {shown.length === 0 ? (
              <li className={styles.empty} role="presentation">
                {query ? (
                  <span>
                    Niets gevonden voor ‘{query}’. Controleer of de entiteit in Home Assistant
                    bestaat en niet is uitgeschakeld.
                  </span>
                ) : (
                  <>
                    <span>Geen entiteiten met eenheid {unit ?? ''} gevonden.</span>
                    <button
                      type="button"
                      className={styles.link}
                      onClick={() => {
                        setFilter('all');
                      }}
                    >
                      Toon alle entiteiten
                    </button>
                  </>
                )}
              </li>
            ) : (
              shown.map((entity, index) => {
                const other = linkedTo.get(entity.id);
                return (
                  <li
                    key={entity.id}
                    id={optionId(index)}
                    role="option"
                    aria-selected={entity.id === current}
                    className={cx(
                      styles.option,
                      entity === activeEntity && styles.optionActive,
                      entity.id === current && styles.optionChosen,
                    )}
                    onMouseEnter={() => {
                      setActive(index);
                    }}
                    onClick={() => {
                      choose(entity);
                    }}
                  >
                    <span className={styles.optionTop}>
                      <span className={styles.optionName}>{entity.friendly_name ?? entity.id}</span>
                      <span className={styles.optionValue}>
                        {isUnavailable(entity) ? (
                          <Pill size="sm">Niet beschikbaar</Pill>
                        ) : (
                          `${entity.state ?? ''}${entity.unit ? ` ${entity.unit}` : ''}`
                        )}
                      </span>
                    </span>
                    <span className={styles.optionId}>
                      {entity.id}
                      {other ? (
                        <Pill tone="amber" size="sm">
                          Al gekoppeld aan {other}
                        </Pill>
                      ) : null}
                    </span>
                  </li>
                );
              })
            )}
            {matches.length > MAX_OPTIONS ? (
              <li className={styles.more} role="presentation">
                Maak je zoekopdracht specifieker om meer te zien (nog {matches.length - MAX_OPTIONS}
                ).
              </li>
            ) : null}
          </ul>
        )}
        <p className={styles.keys}>↑↓ kiezen · Enter selecteren · Esc sluiten</p>
      </div>
    </Dialog>
  );
}
