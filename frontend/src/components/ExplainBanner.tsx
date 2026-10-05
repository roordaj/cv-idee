import { useExplain } from '../content/useExplain.ts';
import { Callout } from './Callout.tsx';

/** Cycli explanation banner (design v3). Hidden when 'uitleg tonen' is off. */
export function ExplainBanner() {
  const { explain } = useExplain();
  if (!explain) return null;
  return (
    <Callout tone="info">
      <strong>Cyclus</strong> = één brandperiode, van start tot stop. Stopt de brander binnen enkele
      minuten terwijl de thermostaat nog warmte vraagt, dan is dat een <strong>korte cyclus</strong>
      . Vaak levert de ketel dan zelfs op minimumvermogen meer warmte dan de installatie op dat
      moment afneemt, maar ook doorstroming of dichte groepen kunnen meespelen.
    </Callout>
  );
}
