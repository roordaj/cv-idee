import { CalendarDays, Check, CircleAlert, Loader2, TriangleAlert } from 'lucide-react';
import { useState, type FormEvent, type KeyboardEvent } from 'react';
import type { components } from '../../api/schema';
import {
  useCreatePeriod,
  useDeletePeriod,
  useInstallation,
  useUpdatePeriod,
} from '../../api/hooks/installation.ts';
import { Button } from '../../components/Button.tsx';
import { Dialog } from '../../components/Dialog.tsx';
import { ICON_SIZE } from '../../components/icons.ts';
import { Toggle } from '../../components/Toggle.tsx';
import { cx, toneVars } from '../../components/tone.ts';
import { formatDayMonth } from '../../lib/format.ts';
import styles from './Quality.module.css';
import { PERIOD_HELP, PERIOD_KINDS, PERIOD_LABEL, PERIOD_TONE, type PeriodKind } from './labels.ts';

type Period = components['schemas']['SpecialPeriod'];
type Exclusions = components['schemas']['PeriodExclusions'];
type RoomOverride = components['schemas']['RoomComfortOverride'];

const DAY_MS = 86_400_000;
const pad = (n: number) => String(n).padStart(2, '0');

function dateInput(d: Date): string {
  return `${String(d.getFullYear())}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
function timeInput(d: Date): string {
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function toDate(date: string, time: string): Date | null {
  if (!date) return null;
  const d = new Date(`${date}T${time || '00:00'}`);
  return Number.isNaN(d.getTime()) ? null : d;
}

export interface PeriodErrors {
  kind?: string;
  start?: string;
  end?: string;
}

function validatePeriod(
  v: { kind: PeriodKind | null; start: Date | null; end: Date | null; ongoing: boolean },
  others: readonly Period[],
  now = new Date(),
): { errors: PeriodErrors; warnings: string[] } {
  const errors: PeriodErrors = {};
  const warnings: string[] = [];
  if (!v.kind) errors.kind = 'Kies een soort periode';
  if (!v.start) errors.start = 'Vul een begintijd in';
  if (!v.ongoing) {
    if (!v.end) errors.end = 'Vul een eindtijd in';
    else if (v.start && v.end.getTime() <= v.start.getTime())
      errors.end = 'De eindtijd moet na de begintijd liggen';
  }
  if (v.start && !errors.start) {
    if (v.start.getTime() > now.getTime() + 365 * DAY_MS)
      warnings.push('Deze periode begint over meer dan een jaar.');
    const endMs = v.ongoing || !v.end ? now.getTime() : v.end.getTime();
    if (!errors.end && endMs - v.start.getTime() > 60 * DAY_MS)
      warnings.push(
        'Lange periode: in deze tijd worden geen normaalgedrag en vergelijkingen opgebouwd.',
      );
    for (const o of others) {
      const oStart = new Date(o.start).getTime();
      const oEnd = o.end ? new Date(o.end).getTime() : Infinity;
      const myEnd = v.ongoing || !v.end ? Infinity : v.end.getTime();
      if (v.start.getTime() < oEnd && oStart < myEnd) {
        warnings.push(
          `Overlapt met '${PERIOD_LABEL[o.kind]} ${formatDayMonth(new Date(o.start))}'. Dat mag; beide gelden dan.`,
        );
      }
    }
  }
  return { errors, warnings };
}

export interface PeriodDialogProps {
  open: boolean;
  onClose: () => void;
  /** Existing period to edit; omit to create. */
  period?: Period | undefined;
  allPeriods: readonly Period[];
  onSaved?: (id: string) => void;
}

export function PeriodDialog(props: PeriodDialogProps) {
  // Remount the form state each time the dialog opens or another period is chosen.
  return (
    <PeriodDialogInner
      key={`${props.open ? 'open' : 'closed'}-${props.period?.id ?? 'new'}`}
      {...props}
    />
  );
}

function PeriodDialogInner({ open, onClose, period, allPeriods, onSaved }: PeriodDialogProps) {
  const editing = period !== undefined;
  const initialStart = period ? new Date(period.start) : new Date();
  const initialEnd = period ? (period.end ? new Date(period.end) : null) : new Date();
  const [kind, setKind] = useState<PeriodKind | null>(period?.kind ?? null);
  const [startDate, setStartDate] = useState(dateInput(initialStart));
  const [startTime, setStartTime] = useState(period ? timeInput(initialStart) : '00:00');
  const [endDate, setEndDate] = useState(initialEnd ? dateInput(initialEnd) : '');
  const [endTime, setEndTime] = useState(initialEnd ? timeInput(initialEnd) : '23:59');
  const [ongoing, setOngoing] = useState(editing && period.end == null);
  const [description, setDescription] = useState(period?.description ?? '');
  const [excluded, setExcluded] = useState<Exclusions>(
    period?.excluded_from ?? { normal_behaviour: true, comparisons: true, ch_conclusions: true },
  );
  const [submitted, setSubmitted] = useState(false);
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const [confirmDelete, setConfirmDelete] = useState(false);
  const installation = useInstallation();
  const [roomOverrides, setRoomOverrides] = useState<RoomOverride[]>(period?.room_overrides ?? []);

  const create = useCreatePeriod();
  const update = useUpdatePeriod();
  const remove = useDeletePeriod();
  const busy = create.isPending || update.isPending || remove.isPending;
  const failed = create.isError || update.isError || remove.isError;

  const start = toDate(startDate, startTime);
  const end = ongoing ? null : toDate(endDate, endTime);
  const { errors, warnings } = validatePeriod(
    { kind, start, end, ongoing },
    allPeriods.filter((p) => p.id !== period?.id),
  );
  const invalidRoomOverride = roomOverrides.some(
    (item) =>
      item.kind === 'temporary_target' &&
      (!Number.isFinite(item.target_temperature_c) || (item.target_temperature_c ?? 0) <= 0),
  );
  const show = (field: keyof PeriodErrors) =>
    submitted || touched.has(field) ? errors[field] : undefined;
  const touch = (field: string) => {
    setTouched((prev) => new Set(prev).add(field));
  };

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    setSubmitted(true);
    if (errors.kind || errors.start || errors.end || !kind || !start || invalidRoomOverride) return;
    const body = {
      kind,
      start: start.toISOString(),
      end: end ? end.toISOString() : null,
      description: description.trim(),
      excluded_from: excluded,
      room_overrides: roomOverrides,
    };
    const done = (saved: { id: string }) => {
      onSaved?.(saved.id);
      onClose();
    };
    if (period) update.mutate({ periodId: period.id, body }, { onSuccess: done });
    else create.mutate(body, { onSuccess: done });
  };

  const onRadioKey = (event: KeyboardEvent) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
    event.preventDefault();
    const idx = kind ? PERIOD_KINDS.indexOf(kind) : -1;
    const step = event.key === 'ArrowRight' ? 1 : -1;
    const next = PERIOD_KINDS[(idx + step + PERIOD_KINDS.length) % PERIOD_KINDS.length];
    if (next) setKind(next);
  };

  const formId = 'period-form';
  const tone = kind ? PERIOD_TONE[kind] : 'blue';

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={editing ? 'Periode bewerken' : 'Periode markeren'}
      subtitle="Telt standaard niet mee voor normaal gedrag en vergelijkingen"
      icon={<CalendarDays size={ICON_SIZE} aria-hidden="true" />}
      tone={tone}
      isDirty={!editing && (kind !== null || description !== '')}
      dangerAction={
        editing ? (
          <Button
            variant="danger"
            disabled={busy}
            onClick={() => {
              if (!confirmDelete) {
                setConfirmDelete(true);
                window.setTimeout(() => {
                  setConfirmDelete(false);
                }, 5000);
                return;
              }
              remove.mutate(period.id, { onSuccess: onClose });
            }}
          >
            {confirmDelete ? 'Zeker weten? Verwijderen' : 'Verwijderen'}
          </Button>
        ) : undefined
      }
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Annuleren
          </Button>
          <Button
            type="submit"
            form={formId}
            disabled={busy}
            iconStart={
              busy ? (
                <Loader2 size={16} aria-hidden="true" />
              ) : (
                <Check size={ICON_SIZE} aria-hidden="true" />
              )
            }
          >
            {editing ? 'Opslaan' : 'Markeren'}
          </Button>
        </>
      }
    >
      <form id={formId} className={styles.form} onSubmit={submit} noValidate>
        <div className={styles.form}>
          <span className={styles.label} id="period-kind-label">
            Soort
          </span>
          <div
            role="radiogroup"
            aria-labelledby="period-kind-label"
            className={styles.chips}
            onKeyDown={onRadioKey}
          >
            {PERIOD_KINDS.map((k) => (
              <button
                key={k}
                type="button"
                role="radio"
                aria-checked={kind === k}
                tabIndex={kind === k || (kind === null && k === PERIOD_KINDS[0]) ? 0 : -1}
                className={cx(styles.chip, kind === k && styles.chipOn)}
                style={toneVars(PERIOD_TONE[k])}
                onClick={() => {
                  setKind(k);
                  touch('kind');
                }}
              >
                {PERIOD_LABEL[k]}
              </button>
            ))}
          </div>
          {show('kind') ? (
            <div role="alert" className={styles.error}>
              <CircleAlert size={14} aria-hidden="true" />
              {show('kind')}
            </div>
          ) : null}
          {kind ? (
            <p className={styles.help} style={toneVars(PERIOD_TONE[kind])}>
              {PERIOD_LABEL[kind]}: {PERIOD_HELP[kind]}
            </p>
          ) : null}
        </div>
        <div className={styles.pair}>
          <div className={styles.field}>
            Van
            <div className={styles.dt}>
              <input
                type="date"
                aria-label="Begindatum"
                className={cx(styles.input, show('start') && styles.invalid)}
                value={startDate}
                aria-invalid={show('start') ? 'true' : undefined}
                onChange={(e) => {
                  setStartDate(e.target.value);
                }}
                onBlur={() => {
                  touch('start');
                }}
              />
              <input
                type="time"
                aria-label="Begintijd"
                className={styles.input}
                value={startTime}
                onChange={(e) => {
                  setStartTime(e.target.value);
                }}
              />
            </div>
            {show('start') ? (
              <span role="alert" className={styles.error}>
                <CircleAlert size={14} aria-hidden="true" />
                {show('start')}
              </span>
            ) : null}
          </div>
          <div className={styles.field}>
            Tot
            <div className={styles.dt}>
              <input
                type="date"
                aria-label="Einddatum"
                className={cx(styles.input, show('end') && styles.invalid)}
                value={endDate}
                disabled={ongoing}
                aria-invalid={show('end') ? 'true' : undefined}
                onChange={(e) => {
                  setEndDate(e.target.value);
                }}
                onBlur={() => {
                  touch('end');
                }}
              />
              <input
                type="time"
                aria-label="Eindtijd"
                className={styles.input}
                value={endTime}
                disabled={ongoing}
                onChange={(e) => {
                  setEndTime(e.target.value);
                }}
              />
            </div>
            {ongoing ? <span>Tot je de periode beëindigt</span> : null}
            {show('end') ? (
              <span role="alert" className={styles.error}>
                <CircleAlert size={14} aria-hidden="true" />
                {show('end')}
              </span>
            ) : null}
          </div>
        </div>
        <label className={styles.checkbox}>
          <input
            type="checkbox"
            checked={ongoing}
            onChange={(e) => {
              setOngoing(e.target.checked);
            }}
          />
          Loopt nog (geen einddatum)
        </label>
        <label className={styles.field}>
          Omschrijving (optioneel)
          <input
            className={styles.input}
            maxLength={140}
            value={description}
            onChange={(e) => {
              setDescription(e.target.value);
            }}
          />
          {description.length > 100 ? (
            <span style={{ textAlign: 'right', color: '#8a92a3' }}>{description.length}/140</span>
          ) : null}
        </label>
        {installation.data?.rooms.length ? (
          <div className={styles.form}>
            <span className={styles.label}>Comfortverwachting per ruimte tijdens deze periode</span>
            {installation.data.rooms.map((room) => {
              const override = roomOverrides.find((item) => item.room_key === room.key);
              const choice = override?.kind ?? 'normal_schedule';
              return (
                <div key={room.key} className={styles.form}>
                  <label className={styles.field}>
                    {room.name}
                    <select
                      className={styles.input}
                      aria-label={`Comfort tijdens periode · ${room.name}`}
                      value={choice}
                      onChange={(event) => {
                        const kind = event.target.value as RoomOverride['kind'] | 'normal_schedule';
                        setRoomOverrides((items) => [
                          ...items.filter((item) => item.room_key !== room.key),
                          ...(kind === 'normal_schedule'
                            ? []
                            : [
                                {
                                  room_key: room.key,
                                  kind,
                                  ...(kind === 'temporary_target'
                                    ? { target_temperature_c: override?.target_temperature_c ?? 20 }
                                    : {}),
                                } as RoomOverride,
                              ]),
                        ]);
                      }}
                    >
                      <option value="normal_schedule">Normaal rooster volgen</option>
                      <option value="no_expectation">Geen comfortverwachting</option>
                      <option value="temporary_target">Tijdelijk comfortdoel</option>
                    </select>
                  </label>
                  {choice === 'temporary_target' ? (
                    <label className={styles.field}>
                      Tijdelijk doel (°C)
                      <input
                        className={styles.input}
                        type="number"
                        min="0.1"
                        step="0.1"
                        aria-label={`Tijdelijk doel · ${room.name}`}
                        value={override?.target_temperature_c ?? 20}
                        onChange={(event) => {
                          setRoomOverrides((items) =>
                            items.map((item) =>
                              item.room_key === room.key
                                ? { ...item, target_temperature_c: Number(event.target.value) }
                                : item,
                            ),
                          );
                        }}
                      />
                    </label>
                  ) : null}
                </div>
              );
            })}
            <p className={styles.note}>
              De tijdelijke verwachting geldt alleen voor de analyse van deze periode. De
              thermostaat wordt niet aangepast.
            </p>
          </div>
        ) : null}
        <div className={styles.form}>
          <span className={styles.label}>Niet meetellen voor</span>
          <Toggle
            label="Normaal gedrag en referentie"
            checked={excluded.normal_behaviour}
            onChange={(v) => {
              setExcluded({ ...excluded, normal_behaviour: v });
            }}
          />
          <Toggle
            label="Voor/na-vergelijkingen van wijzigingen"
            checked={excluded.comparisons}
            onChange={(v) => {
              setExcluded({ ...excluded, comparisons: v });
            }}
          />
          <Toggle
            label="Bevindingen (cv-conclusies over deze periode)"
            checked={excluded.ch_conclusions}
            onChange={(v) => {
              setExcluded({ ...excluded, ch_conclusions: v });
            }}
          />
          <p className={styles.note}>
            De gegevens blijven altijd zichtbaar in grafieken en tabellen.
          </p>
        </div>
        {warnings.map((w) => (
          <div key={w} role="status" className={styles.warn}>
            <TriangleAlert size={14} aria-hidden="true" />
            {w}
          </div>
        ))}
        {submitted && invalidRoomOverride ? (
          <div role="alert" className={styles.error}>
            <CircleAlert size={14} aria-hidden="true" />
            Een tijdelijk comfortdoel moet hoger zijn dan 0 °C.
          </div>
        ) : null}
        {failed ? (
          <div role="alert" className={styles.error}>
            <CircleAlert size={14} aria-hidden="true" />
            Opslaan is mislukt. Probeer het opnieuw.
          </div>
        ) : null}
      </form>
    </Dialog>
  );
}
