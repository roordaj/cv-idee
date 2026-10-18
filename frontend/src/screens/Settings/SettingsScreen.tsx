import { Settings2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { getBasePath } from '../../lib/basePath';
import { ApiError, api, unwrap } from '../../api/client';
import { useSettings, useUpdateSettings } from '../../api/hooks/settings';
import { useSignals } from '../../api/hooks/signals';
import { useStatus } from '../../api/hooks/system';
import { useQuery } from '@tanstack/react-query';
import {
  Button,
  Callout,
  Card,
  Dialog,
  ErrorCallout,
  PageHeader,
  Pill,
  Skeleton,
  Toggle,
} from '../../components';
import { useExplain } from '../../content/useExplain';
import { SignalPanel } from '../Signals/SignalPanel';
import { display, GROUPS, parseNumber, validate, type Parameter, type Values } from './schema';
import styles from './Settings.module.css';

type Settings = NonNullable<ReturnType<typeof useSettings>['data']>;
function SettingsForm({ initial: source, reload }: { initial: Settings; reload: () => void }) {
  const [initial, setInitial] = useState(source);
  const navigate = useNavigate();
  const [destination, setDestination] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, string | boolean>>(() =>
    Object.fromEntries(
      Object.entries(initial.values).map(([k, v]) => [k, typeof v === 'boolean' ? v : display(v)]),
    ),
  );
  const [errors, setErrors] = useState<Record<string, string | null>>({});
  const [confirm, setConfirm] = useState(false);
  const [saved, setSaved] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const update = useUpdateSettings();
  const signals = useSignals();
  const status = useStatus();
  const explain = useExplain();
  const history = useQuery({
    queryKey: ['settings-history'],
    queryFn: async () => unwrap(await api().GET('/api/settings/history')),
  });
  const parameters = (initial.json_schema.properties ?? {}) as Record<string, Parameter>;
  const changed = Object.keys(parameters).filter(
    (k) =>
      draft[k] !==
      (typeof initial.values[k as keyof Values] === 'boolean'
        ? initial.values[k as keyof Values]
        : display(initial.values[k as keyof Values])),
  );
  const values = () =>
    Object.fromEntries(
      Object.entries(draft).map(([k, v]) => [k, typeof v === 'boolean' ? v : parseNumber(v)]),
    ) as Values;
  const check = () => {
    const next: Record<string, string | null> = {};
    for (const [k, p] of Object.entries(parameters))
      if (typeof draft[k] === 'string') next[k] = validate(k, draft[k], p);
    const v = values();
    if (v.repetition_days > v.repetition_window_days)
      next.repetition_days = 'Het eerste getal mag niet groter zijn dan de periode.';
    if (v.limited_weather_c < v.comparable_weather_c)
      next.limited_weather_c = 'Deze grens moet minstens gelijk zijn aan Vergelijkbaar weer.';
    setErrors(next);
    return !Object.values(next).some(Boolean);
  };
  const requestSave = () => {
    if (changed.length && check()) setConfirm(true);
  };
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        requestSave();
      }
    };
    const unload = (e: BeforeUnloadEvent) => {
      if (changed.length) {
        e.preventDefault();
      }
    };
    const leave = (e: MouseEvent) => {
      const link = e.target instanceof Element ? e.target.closest('a') : null;
      if (
        !changed.length ||
        !link ||
        e.metaKey ||
        e.ctrlKey ||
        e.shiftKey ||
        e.button !== 0 ||
        link.target === '_blank'
      )
        return;
      const url = new URL(link.href);
      if (
        url.origin !== window.location.origin ||
        (url.pathname === window.location.pathname && url.hash)
      )
        return;
      e.preventDefault();
      e.stopPropagation();
      const base = getBasePath();
      if (base && !url.pathname.startsWith(`${base}/`)) return;
      setDestination(url.pathname.slice(base.length) + url.search + url.hash);
    };
    document.addEventListener('click', leave, true);
    window.addEventListener('keydown', handler);
    window.addEventListener('beforeunload', unload);
    return () => {
      document.removeEventListener('click', leave, true);
      window.removeEventListener('keydown', handler);
      window.removeEventListener('beforeunload', unload);
    };
  });
  const save = () => {
    update.mutate(
      {
        revision: initial.revision,
        values: values(),
        onboarding_completed_at: initial.onboarding_completed_at,
      },
      {
        onSuccess: (response) => {
          setInitial(response);
          setDraft(
            Object.fromEntries(
              Object.entries(response.values).map(([key, value]) => [
                key,
                typeof value === 'boolean' ? value : display(value),
              ]),
            ),
          );
          setErrors({});
          explain.setExplain(response.values.show_explanations);
          explain.setShowRequirementIds(response.values.show_requirement_ids);
          setConfirm(false);
          setSaved(true);
          void history.refetch();
        },
        onError: (error) => {
          setConfirm(false);
          if (
            error instanceof ApiError &&
            error.status === 422 &&
            typeof error.problem === 'object' &&
            error.problem !== null &&
            'errors' in error.problem &&
            Array.isArray(error.problem.errors)
          ) {
            const serverErrors: Record<string, string> = {};
            for (const item of error.problem.errors as unknown[]) {
              if (
                typeof item !== 'object' ||
                item === null ||
                !('loc' in item) ||
                !('msg' in item) ||
                !Array.isArray(item.loc) ||
                typeof item.msg !== 'string'
              )
                continue;
              const key: unknown = item.loc.at(-1);
              if (typeof key === 'string' && key in parameters) serverErrors[key] = item.msg;
            }
            setErrors(serverErrors);
          }
        },
      },
    );
  };
  const activeSignal = signals.data?.items.find((s) => s.id === selected);
  return (
    <>
      <Dialog
        open={destination !== null}
        onClose={() => {
          setDestination(null);
        }}
        title="Wijzigingen niet opgeslagen"
        footer={
          <>
            <Button
              onClick={() => {
                setDestination(null);
              }}
            >
              Blijven
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                if (destination) void navigate(destination);
              }}
            >
              Weggooien
            </Button>
          </>
        }
      >
        <p>Je hebt {changed.length} instellingen gewijzigd die nog niet zijn opgeslagen.</p>
      </Dialog>
      {initial.values.show_explanations && (
        <Callout tone="info" title="Er bestaat geen universele norm">
          Voor een goed aantal branderstarts, de juiste ΔT of de beste aanvoertemperatuur. Deze
          grenzen zijn startwaarden die je aan je eigen installatie kunt aanpassen. Na opslaan
          worden de analyses opnieuw berekend. Elk advies bewaart de instellingen van dat moment in
          de Advieshistorie.
        </Callout>
      )}
      {saved && (
        <Callout tone="success">Opgeslagen. De analyse gebruikt de nieuwe instellingen.</Callout>
      )}
      <div className={styles.layout}>
        <nav aria-label="Instellingensecties" className={styles.index}>
          {Object.entries(GROUPS).map(([key, label]) => (
            <a key={key} href={`#${key}`} onClick={() => document.getElementById(key)?.focus()}>
              {label}
            </a>
          ))}
          <small title={initial.revision}>Config-versie {initial.revision.slice(0, 12)}</small>
        </nav>
        <div className={styles.cards}>
          {Object.entries(GROUPS).map(([group, label]) => (
            <Card key={group}>
              <h2 id={group} tabIndex={-1}>
                {label}
              </h2>
              {Object.entries(parameters)
                .filter(
                  ([key, p]) =>
                    p['x-group'] === group &&
                    (key !== 'show_requirement_ids' || import.meta.env.DEV),
                )
                .map(([key, p]) => {
                  const value = draft[key];
                  const id = `setting-${key}`;
                  const isChanged = changed.includes(key);
                  return (
                    <div className={styles.row} key={key}>
                      <div>
                        <label htmlFor={id} className={styles.label}>
                          {p.title ?? key}
                        </label>{' '}
                        {isChanged && <Pill tone="amber">Gewijzigd</Pill>}
                        <p id={`${id}-help`} className={styles.description}>
                          {p.description}
                        </p>
                        <div className={styles.meta}>
                          Standaard{' '}
                          {typeof p.default === 'boolean'
                            ? p.default
                              ? 'aan'
                              : 'uit'
                            : display(p.default) || 'leeg'}{' '}
                          {p['x-unit']}{' '}
                          {p['x-rule']?.length ? `· gebruikt door ${p['x-rule'].join(', ')}` : ''}
                        </div>
                        {value !==
                          (typeof p.default === 'boolean' ? p.default : display(p.default)) && (
                          <button
                            type="button"
                            className={styles.restore}
                            onClick={() => {
                              setDraft({
                                ...draft,
                                [key]:
                                  typeof p.default === 'boolean' ? p.default : display(p.default),
                              });
                              setErrors({ ...errors, [key]: null });
                              document.getElementById(id)?.focus();
                            }}
                          >
                            Standaardwaarde herstellen
                          </button>
                        )}
                      </div>
                      <div>
                        {typeof value === 'boolean' ? (
                          <Toggle
                            checked={value}
                            label={p.title ?? key}
                            onChange={(v) => {
                              setDraft({ ...draft, [key]: v });
                            }}
                          />
                        ) : (
                          <div className={styles.field}>
                            <input
                              id={id}
                              className={styles.input}
                              inputMode="decimal"
                              value={value ?? ''}
                              aria-label={`${p.title ?? key}${p['x-unit'] ? ` in ${p['x-unit']}` : ''}`}
                              aria-invalid={!!errors[key]}
                              aria-describedby={`${id}-help${errors[key] ? ` ${id}-error` : ''}`}
                              onChange={(e) => {
                                setDraft({ ...draft, [key]: e.target.value });
                              }}
                              onBlur={() => {
                                setErrors({
                                  ...errors,
                                  [key]: validate(key, String(draft[key]), p),
                                });
                              }}
                              onKeyDown={(e) => {
                                if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
                                  e.preventDefault();
                                  const n = parseNumber(String(value));
                                  const step = (p['x-step'] ?? 1) * (e.shiftKey ? 10 : 1);
                                  setDraft({
                                    ...draft,
                                    [key]: display(
                                      Number(
                                        ((n ?? 0) + (e.key === 'ArrowUp' ? step : -step)).toFixed(
                                          6,
                                        ),
                                      ),
                                    ),
                                  });
                                }
                              }}
                            />
                            <span className={styles.meta}>{p['x-unit']}</span>
                          </div>
                        )}
                        {errors[key] && (
                          <div id={`${id}-error`} role="alert" className={styles.error}>
                            {errors[key]}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              {group === 'short_cycles' && (
                <p className={styles.meta}>
                  Altijd uitgesloten: tapwatercycli, naloop en gemarkeerde perioden. Dit is niet
                  instelbaar.
                </p>
              )}
              {group === 'data' && (
                <>
                  <h3>Gegevens per signaal</h3>
                  <div className={styles.signals}>
                    {signals.data?.items.map((s) => (
                      <div key={s.id} className={styles.signal}>
                        <span>
                          {s.name}
                          <small className={styles.meta}>
                            {' '}
                            · {s.entity_id ?? 'Niet gekoppeld'} · Werkelijk:{' '}
                            {s.median_update_interval_s === null
                              ? 'onbekend'
                              : `${display(s.median_update_interval_s)} s`}
                          </small>
                        </span>
                        <Button
                          variant="secondary"
                          onClick={() => {
                            setSelected(s.id);
                          }}
                        >
                          Instellen
                        </Button>
                      </div>
                    ))}
                  </div>
                  {activeSignal && (
                    <SignalPanel
                      key={activeSignal.id}
                      signal={activeSignal}
                      signals={signals.data?.items ?? []}
                    />
                  )}
                </>
              )}
              {group === 'costs' &&
                !signals.data?.items.some((s) => s.role === 'gas_cumulative' && s.entity_id) && (
                  <Callout tone="neutral">
                    Er is geen gasmeter gekoppeld, dus euro's kunnen ook met een gasprijs nog niet
                    worden berekend. <Link to="/signalen">Gasmeter koppelen ›</Link>
                  </Callout>
                )}
              {group === 'display' && <Link to="/welkom">Eerste start openen ›</Link>}
            </Card>
          ))}
          <Card>
            <h2>Eerdere wijzigingen</h2>
            {history.isError ? (
              <ErrorCallout subject="eerdere wijzigingen" onRetry={() => void history.refetch()} />
            ) : (
              history.data?.items.slice(0, 10).map((item) => (
                <p key={item.revision}>
                  <time>
                    {new Date(item.saved_at).toLocaleString('nl-NL', {
                      timeZone: 'Europe/Amsterdam',
                    })}
                  </time>{' '}
                  · {item.changed_by ?? 'Onbekend'} · {item.note ?? item.revision.slice(0, 12)}
                </p>
              ))
            )}
          </Card>
        </div>
      </div>
      {Number(draft.flame_resolution_s) > (Number(draft.short_cycle_min) * 60) / 4 && (
        <Callout tone="warning">
          Met deze resolutie zijn cycli van {draft.short_cycle_min} min niet betrouwbaar te
          onderscheiden.
        </Callout>
      )}
      {update.isError && (
        <Callout tone="error">
          {update.error instanceof ApiError && update.error.status === 409 ? (
            <>
              Instellingen zijn intussen gewijzigd. Herlaad de nieuwste waarden; je eigen
              wijzigingen gaan dan verloren.{' '}
              <Button variant="secondary" onClick={reload}>
                Herladen
              </Button>
            </>
          ) : (
            'Niet opgeslagen. Controleer de waarden en probeer opnieuw; je invoer is bewaard.'
          )}
        </Callout>
      )}
      {changed.length > 0 && (
        <div className={styles.bar}>
          <span>{changed.length} wijzigingen niet opgeslagen</span>
          <div className={styles.actions}>
            <Button variant="secondary" onClick={reload}>
              Annuleren
            </Button>
            <Button disabled={update.isPending} onClick={requestSave}>
              Opslaan en herberekenen
            </Button>
          </div>
        </div>
      )}
      <Dialog
        open={confirm}
        onClose={() => {
          setConfirm(false);
        }}
        title="Instellingen opslaan en herberekenen?"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setConfirm(false);
              }}
            >
              Annuleren
            </Button>
            <Button disabled={update.isPending} onClick={save}>
              Opslaan en herberekenen
            </Button>
          </>
        }
      >
        <p>
          De analyses over de bewaarde gegevens worden met de nieuwe grenzen opnieuw berekend.
          Adviezen houden in de Advieshistorie hun oude instellingen.
        </p>
        {status.data?.recompute && (
          <Callout tone="warning">Er loopt al een herberekening; die wordt vervangen.</Callout>
        )}
        <ul>
          {changed.map((k) => (
            <li key={k}>
              {parameters[k]?.title}: {display(initial.values[k as keyof Values])} →{' '}
              {String(draft[k])}
            </li>
          ))}
        </ul>
        {changed.includes('retention_days') &&
          Number(draft.retention_days) < initial.values.retention_days && (
            <Callout tone="warning">
              Gegevens ouder dan {draft.retention_days} dagen worden bij de volgende opruimronde
              verwijderd. Herberekenen kan daarna niet meer.
            </Callout>
          )}
      </Dialog>
    </>
  );
}
export function SettingsScreen() {
  const settings = useSettings();
  const [generation, setGeneration] = useState(0);
  return (
    <div className={styles.page}>
      <PageHeader
        title="Analyse-instellingen"
        subtitle="Grenzen waarmee de analyse patronen beoordeelt"
        icon={<Settings2 />}
        tone="slate"
      />
      {settings.isPending ? (
        <Skeleton height={400} />
      ) : settings.isError ? (
        <ErrorCallout subject="de instellingen" onRetry={() => void settings.refetch()} />
      ) : (
        <SettingsForm
          key={generation}
          initial={settings.data}
          reload={() => {
            void settings.refetch().then(() => {
              setGeneration((g) => g + 1);
            });
          }}
        />
      )}
    </div>
  );
}
