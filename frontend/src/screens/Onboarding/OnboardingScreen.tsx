import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAnalyses, useHaStatus, useSignals } from '../../api/hooks/signals';
import { useSettings, useUpdateSettings } from '../../api/hooks/settings';
import { Button, Callout, Card, ErrorCallout, PageHeader, Pill, Skeleton } from '../../components';
import { SignalPanel } from '../Signals/SignalPanel';
import { ImportCard } from '../Quality/ImportCard';
import styles from './Onboarding.module.css';
import { useOnboardingProgress, STEPS } from './progress';

export function OnboardingGate() {
  const settings = useSettings();
  const signals = useSignals();
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    if (location.pathname === '/welkom' || sessionStorage.getItem('cv-idee.setup-deferred')) return;
    if (
      settings.data &&
      signals.data &&
      !settings.data.onboarding_completed_at &&
      !signals.data.items.some((s) => s.role === 'flame' && s.entity_id)
    )
      void navigate('/welkom', { replace: true });
  }, [settings.data, signals.data, location.pathname, navigate]);
  return null;
}
export function OnboardingScreen() {
  const { step, setStep } = useOnboardingProgress();
  const [selected, setSelected] = useState<string | null>(null);
  const [warn, setWarn] = useState(false);
  const ha = useHaStatus();
  const signals = useSignals();
  const analyses = useAnalyses();
  const settings = useSettings();
  const save = useUpdateSettings();
  const navigate = useNavigate();
  const { refetch } = ha;
  useEffect(() => {
    const id = window.setInterval(() => void refetch(), 5000);
    return () => {
      window.clearInterval(id);
    };
  }, [refetch]);
  const connected = ha.data?.connected;
  const mapped = signals.data?.items.some((s) => s.role === 'flame' && s.entity_id);
  const active = signals.data?.items.find((s) => s.id === selected);
  const defer = () => {
    sessionStorage.setItem('cv-idee.setup-deferred', '1');
    void navigate('/overzicht');
  };
  const finish = () => {
    if (!settings.data) return;
    save.mutate(
      {
        revision: settings.data.revision,
        values: settings.data.values,
        onboarding_completed_at: new Date().toISOString(),
      },
      {
        onSuccess: () => {
          sessionStorage.removeItem('cv-idee.setup-deferred');
          void navigate('/overzicht');
        },
      },
    );
  };
  return (
    <div className={styles.page}>
      <PageHeader
        title="Welkom bij CV-analyse"
        subtitle="In drie stappen naar je eerste analyse. Deze app leest alleen; hij stuurt niets aan."
        actions={
          <Button variant="secondary" onClick={defer}>
            Later afmaken ›
          </Button>
        }
      />
      <nav aria-label="Inrichten" className={styles.steps}>
        {STEPS.map((label, i) => (
          <button
            key={label}
            disabled={i + 1 > step}
            aria-current={step === i + 1 ? 'step' : undefined}
            onClick={() => {
              setStep(i + 1);
            }}
          >
            {i + 1 < step ? '✓' : i + 1} {label}
          </button>
        ))}
      </nav>
      <Card>
        <p className={styles.meta}>{step < 4 ? `Stap ${String(step)} van 3` : 'Klaar'}</p>
        {step === 1 && (
          <>
            <h2>Verbinding met Home Assistant</h2>
            {ha.isPending ? (
              <Skeleton height={80} />
            ) : ha.isError ? (
              <ErrorCallout subject="de verbinding" onRetry={() => void ha.refetch()} />
            ) : connected ? (
              <Callout tone="success" title="Verbonden met Home Assistant">
                De verbinding is gecontroleerd. Je kunt nu signalen koppelen.
              </Callout>
            ) : (
              <Callout tone="error" title="Geen verbinding met Home Assistant.">
                {ha.data.configured
                  ? 'Controleer of Home Assistant bereikbaar is en het toegangstoken geldig is. Bekijk het logboek voor de oorzaak.'
                  : 'Stel HA_URL en HA_TOKEN in voor standalone gebruik, of controleer de Supervisor-verbinding van de add-on. Herstart daarna de app.'}
                <p>
                  <Button variant="secondary" onClick={() => void ha.refetch()}>
                    Opnieuw controleren
                  </Button>
                </p>
              </Callout>
            )}
          </>
        )}
        {step === 2 && (
          <>
            <h2>Signalen koppelen</h2>
            <p>
              Koppel de Home Assistant-entiteiten aan wat ze betekenen. Minimaal de vlamstatus is
              nodig; elk extra signaal maakt meer analyses mogelijk. Een ontbrekend signaal
              blokkeert alleen de analyses die het nodig hebben.
            </p>
            {signals.isError ? (
              <ErrorCallout subject="de signalen" onRetry={() => void signals.refetch()} />
            ) : signals.isPending ? (
              <Skeleton height={200} />
            ) : (
              <>
                {(['required', 'recommended', 'optional'] as const).map((group) => (
                  <details key={group} open={group !== 'optional'}>
                    <summary>
                      {
                        {
                          required: 'Minimaal nodig',
                          recommended: 'Sterk aanbevolen',
                          optional: 'Optioneel',
                        }[group]
                      }
                    </summary>
                    {signals.data.items
                      .filter((s) => s.group === group)
                      .map((s) => (
                        <div key={s.id} className={styles.signal}>
                          <div>
                            <strong>{s.name}</strong>
                            <div className={styles.meta}>{s.entity_id ?? 'Nog niet gekoppeld'}</div>
                            <small>Nodig voor {s.needed_for_text}</small>
                          </div>
                          <Button
                            variant="secondary"
                            onClick={() => {
                              setSelected(s.id);
                            }}
                          >
                            {s.entity_id ? 'Wijzigen' : 'Kiezen…'}
                          </Button>
                        </div>
                      ))}
                  </details>
                ))}
                {active && (
                  <SignalPanel key={active.id} signal={active} signals={signals.data.items} />
                )}
              </>
            )}
            <p className={styles.meta}>Locatie en betekenis vul je later aan onder Signalen.</p>
            <h3>Wat je hiermee kunt</h3>
            {analyses.data?.items.map((a) => (
              <Pill key={a.id} tone={a.status === 'available' ? 'green' : 'amber'}>
                {a.name} ·{' '}
                {a.status === 'available'
                  ? 'Beschikbaar'
                  : a.status === 'limited'
                    ? 'Beperkt'
                    : 'Niet beschikbaar'}
              </Pill>
            ))}
            {warn && (
              <Callout tone="warning">
                Zonder CV-/tapwatermodus kan de app tapwater niet van verwarming scheiden.
                Conclusies krijgen dan een lagere zekerheid. Je kunt dit later koppelen.{' '}
                <Button
                  variant="secondary"
                  onClick={() => {
                    setStep(3);
                  }}
                >
                  Toch verder
                </Button>
              </Callout>
            )}
          </>
        )}
        {step === 3 && (
          <>
            <h2>Historie importeren</h2>
            <p>
              Door eerdere metingen te importeren heb je direct gegevens voor een eerste analyse. De
              import gebruikt precies dezelfde analyse als live gegevens.
            </p>
            <ImportCard
              defaultPreset="all"
              minCoveragePct={settings.data?.values.min_assessment_coverage_pct ?? 80}
            />
            <p className={styles.meta}>
              Je kunt verder terwijl de import op de achtergrond loopt. Bij overslaan begint de
              analyse vanaf nu.
            </p>
          </>
        )}
        {step === 4 && (
          <>
            <h2>Klaar om te analyseren</h2>
            <p>
              De analyse loopt vanaf nu. Na minimaal{' '}
              {settings.data?.values.min_observation_hours ?? 'voldoende'} uur met cv-bedrijf
              verschijnt de eerste beoordeling; tot die tijd toont het Overzicht ‘Onvoldoende
              gegevens’.
            </p>
            <h3>Nog te doen (optioneel)</h3>
            <ul>
              <li>
                <Link to="/installatie">Installatieprofiel invullen</Link>
              </li>
              <li>
                <Link to="/signalen">Locatie en betekenis van signalen aanvullen</Link>
              </li>
              <li>
                <Link to="/instellingen/analyse">Analyse-instellingen bekijken</Link>
              </li>
              <li>
                <Link to="/meldingen">Meldingen instellen</Link>
              </li>
            </ul>
            {save.isError && (
              <Callout tone="error">
                De inrichting kon niet worden opgeslagen. Probeer opnieuw; de koppelingen zijn
                bewaard.
              </Callout>
            )}
          </>
        )}
        <div className={styles.actions}>
          {step > 1 && step < 4 && (
            <Button
              variant="secondary"
              onClick={() => {
                setStep(step - 1);
              }}
            >
              ← Vorige
            </Button>
          )}
          {step === 3 && (
            <Button
              variant="secondary"
              onClick={() => {
                setStep(4);
              }}
            >
              Overslaan
            </Button>
          )}
          <Button
            disabled={
              (step === 1 && !connected) ||
              (step === 2 && !mapped) ||
              (step === 4 && (!settings.data || save.isPending))
            }
            onClick={() => {
              if (step === 4) finish();
              else if (
                step === 2 &&
                !signals.data?.items.some((s) => s.role === 'operating_mode' && s.entity_id)
              )
                setWarn(true);
              else setStep(step + 1);
            }}
          >
            {step === 4
              ? 'Naar het Overzicht'
              : step === 3
                ? 'Verder — import kan op de achtergrond doorlopen'
                : 'Volgende →'}
          </Button>
        </div>
      </Card>
    </div>
  );
}
