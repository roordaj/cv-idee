import { useState } from 'react';
import type { components } from '../../api/schema';
import { useRoomComfortAnalysis, useUpdateInstallation } from '../../api/hooks/installation.ts';
import { Button } from '../../components/Button.tsx';
import { Card } from '../../components/Card.tsx';
import { Callout } from '../../components/Callout.tsx';
import { formatNumber } from '../../lib/format.ts';
import {
  initialComfort,
  initialComfortWindow,
  validateComfortSchedule,
  WEEKDAYS,
  type ComfortWindow,
  type RoomComfort,
} from './comfortSchedule.ts';
import type { InstallationProfile } from './specFormat.ts';
import styles from './Installation.module.css';

type Room = InstallationProfile['rooms'][number];
type Result = components['schemas']['RoomComfortResult'];
const temp = (v: number | null | undefined) =>
  v == null ? 'Onbekend' : `${formatNumber(v, 1)} °C`;
const hours = (v: number | null | undefined) =>
  v == null ? 'Onbekend' : `${formatNumber(v, 1)} uur`;

function scheduleLabel(value: RoomComfort): string {
  if (value.status === 'not_configured') return 'Niet ingesteld';
  if (value.status === 'no_expectation') return 'Geen comfortverwachting';
  return (
    (value.windows ?? [])
      .map(
        (w) =>
          `${w.weekdays.map((d) => WEEKDAYS[d]?.short).join(', ')} ${w.start_time}–${w.end_time}: ${temp(w.target_temperature_c)}`,
      )
      .join(' · ') || 'Geen tijdvakken'
  );
}

export function RoomComfortPanel({ profile }: { profile: InstallationProfile }) {
  const analysis = useRoomComfortAnalysis();
  const update = useUpdateInstallation();
  const [roomKey, setRoomKey] = useState(profile.rooms[0]?.key ?? '');
  const [draft, setDraft] = useState<RoomComfort | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selected = profile.rooms.find((r) => r.key === roomKey);
  const current = selected?.comfort ?? initialComfort();
  const value = draft ?? current;
  const resultByRoom = new Map((analysis.data?.rooms ?? []).map((r) => [r.room_key, r]));

  const save = () => {
    if (!selected || !draft) return;
    const validation = validateComfortSchedule(draft);
    if (validation) {
      setError(validation);
      return;
    }
    setError(null);
    const rooms = profile.rooms.map((room) =>
      room.key === selected.key ? { ...room, comfort: draft } : room,
    );
    update.mutate(
      {
        boiler: profile.boiler,
        circuits: profile.circuits,
        zones: profile.zones,
        rooms,
        specifications: profile.specifications,
        revision: profile.revision,
      },
      {
        onSuccess: () => {
          setDraft(null);
        },
        onError: () => {
          setError('Opslaan is niet gelukt. Controleer de verbinding en probeer opnieuw.');
        },
      },
    );
  };

  const edit = (next: RoomComfort) => {
    setDraft(next);
    setError(null);
  };
  const setWindow = (index: number, patch: Partial<ComfortWindow>) => {
    const windows = [...(value.windows ?? [])];
    const window = windows[index];
    if (!window) return;
    windows[index] = { ...window, ...patch };
    edit({ ...value, status: 'scheduled', windows });
  };

  return (
    <section className={styles.roomComfortSection} aria-labelledby="room-comfort-title">
      <div className={styles.comfortHead}>
        <h2 id="room-comfort-title" className={styles.h3}>
          Comfort per ruimte
        </h2>
        <span>Elke ruimte afzonderlijk</span>
      </div>
      {profile.rooms.length === 0 ? (
        <p>Er zijn nog geen ruimtes in het installatieprofiel.</p>
      ) : (
        <>
          <div className={styles.roomCards}>
            {profile.rooms.map((room) => (
              <RoomCard key={room.key} room={room} result={resultByRoom.get(room.key)} />
            ))}
          </div>
          <Card className={styles.comfortEditor}>
            <h3 className={styles.h3}>Comfortrooster bewerken</h3>
            <label className={styles.field}>
              Ruimte
              <select
                className={styles.input}
                value={roomKey}
                onChange={(e) => {
                  setRoomKey(e.target.value);
                  setDraft(null);
                  setError(null);
                }}
              >
                {profile.rooms.map((r) => (
                  <option key={r.key} value={r.key}>
                    {r.name}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              Verwachting
              <select
                className={styles.input}
                value={value.status}
                onChange={(e) => {
                  edit({
                    ...value,
                    status: e.target.value as RoomComfort['status'],
                    windows: value.windows?.length ? value.windows : [initialComfortWindow()],
                  });
                }}
              >
                <option value="not_configured">Niet ingesteld</option>
                <option value="scheduled">Terugkerend rooster</option>
                <option value="no_expectation">Geen comfortverwachting</option>
              </select>
            </label>
            {value.status === 'scheduled' ? (
              <>
                {(value.windows ?? []).map((w, i) => (
                  <fieldset className={styles.window} key={i}>
                    <legend>{w.kind === 'night' ? 'Nachtverlaging' : 'Comforttijdvak'}</legend>
                    <label className={styles.field}>
                      Soort
                      <select
                        className={styles.input}
                        value={w.kind}
                        onChange={(e) => {
                          setWindow(i, { kind: e.target.value as 'comfort' | 'night' });
                        }}
                      >
                        <option value="comfort">Comfortdoel</option>
                        <option value="night">Nachtverlaging</option>
                      </select>
                    </label>
                    <div className={styles.weekdays}>
                      {WEEKDAYS.map((d) => (
                        <label key={d.value}>
                          <input
                            type="checkbox"
                            checked={w.weekdays.includes(d.value)}
                            onChange={(e) => {
                              setWindow(i, {
                                weekdays: e.target.checked
                                  ? [...w.weekdays, d.value].sort()
                                  : w.weekdays.filter((v) => v !== d.value),
                              });
                            }}
                          />
                          {d.short}
                        </label>
                      ))}
                    </div>
                    <div className={styles.windowFields}>
                      <label className={styles.field}>
                        Van
                        <input
                          className={styles.input}
                          type="time"
                          value={w.start_time}
                          onChange={(e) => {
                            setWindow(i, { start_time: e.target.value });
                          }}
                        />
                      </label>
                      <label className={styles.field}>
                        Tot
                        <input
                          className={styles.input}
                          type="time"
                          value={w.end_time}
                          onChange={(e) => {
                            setWindow(i, { end_time: e.target.value });
                          }}
                        />
                      </label>
                      <label className={styles.field}>
                        Doel (°C)
                        <input
                          className={styles.input}
                          type="number"
                          min="0.1"
                          step="0.1"
                          value={w.target_temperature_c}
                          onChange={(e) => {
                            setWindow(i, { target_temperature_c: Number(e.target.value) });
                          }}
                        />
                      </label>
                    </div>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => {
                        edit({
                          ...value,
                          windows: (value.windows ?? []).filter((_, n) => n !== i),
                        });
                      }}
                    >
                      Tijdvak verwijderen
                    </Button>
                  </fieldset>
                ))}
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    edit({
                      ...value,
                      windows: [
                        ...(value.windows ?? []),
                        { ...initialComfortWindow(), weekdays: [] },
                      ],
                    });
                  }}
                >
                  Tijdvak toevoegen
                </Button>
              </>
            ) : null}
            <p className={styles.note}>
              Tijden zijn lokaal voor Europe/Amsterdam. Opslaan wijzigt alleen het analyseprofiel;
              de app bedient geen thermostaat.
            </p>
            {error ? (
              <Callout tone="warning" title="Rooster niet opgeslagen">
                {error}
              </Callout>
            ) : null}
            {update.isError && !error ? (
              <Callout tone="warning">Opslaan is niet gelukt.</Callout>
            ) : null}
            <Button disabled={!draft || update.isPending} onClick={save}>
              {update.isPending ? 'Opslaan…' : 'Rooster opslaan'}
            </Button>
          </Card>
        </>
      )}
    </section>
  );
}

function RoomCard({ room, result }: { room: Room; result: Result | undefined }) {
  const comfort = room.comfort ?? initialComfort();
  return (
    <Card className={styles.roomMetricCard}>
      <h3 className={styles.roomName}>{room.name}</h3>
      <p className={styles.roomSub}>{scheduleLabel(comfort)}</p>
      <dl className={styles.roomMetrics}>
        <dt>Comfortdoel</dt>
        <dd>{comfort.status === 'scheduled' ? scheduleLabel(comfort) : 'Onbekend'}</dd>
        <dt>Actueel setpoint</dt>
        <dd>{temp(result?.current_setpoint_c)}</dd>
        <dt>Kamertemperatuur</dt>
        <dd>{temp(result?.current_temperature_c)}</dd>
        <dt>Comfortverlies</dt>
        <dd>{hours(result?.comfort_loss_target_hours)}</dd>
        <dt>Opwarmtijd gemiddeld</dt>
        <dd>
          {result?.warmup_mean_minutes == null
            ? 'Onbekend'
            : `${formatNumber(result.warmup_mean_minutes, 1)} min`}
        </dd>
        <dt>Overshoot</dt>
        <dd>{hours(result?.overshoot_target_hours)}</dd>
        <dt>Dekking</dt>
        <dd>
          {result?.coverage_pct == null ? 'Onbekend' : `${formatNumber(result.coverage_pct, 1)}%`}
        </dd>
        <dt>Bron</dt>
        <dd>
          {result?.target_source === 'configured_schedule'
            ? 'Ingesteld rooster'
            : result?.target_source === 'special_period'
              ? 'Bijzondere periode'
              : 'Niet ingesteld'}
        </dd>
      </dl>
      {!result || result.availability !== 'available' ? (
        <p className={styles.note}>
          {!result
            ? 'Analyse nog niet beschikbaar.'
            : result.availability === 'limited'
              ? 'Beperkte gegevens; conclusies kunnen onvolledig zijn.'
              : 'Geen bruikbare meetgegevens voor deze ruimte.'}
        </p>
      ) : null}
      {result?.missing_signals.length ? (
        <p className={styles.note}>Ontbrekende signalen: {result.missing_signals.join(', ')}</p>
      ) : null}
    </Card>
  );
}
