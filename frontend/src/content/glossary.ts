// Texts copied 1:1 from docs/design/CV-analyse-v3.dc.html (GLOSS, TERMS, KEX).

export const GLOSS = {
  Pendelen:
    'De brander gaat herhaaldelijk kort aan en uit terwijl de thermostaat nog warmte vraagt. Meer starts betekent meestal meer slijtage en een lager rendement.',
  Warmtevraag: 'Het signaal van de thermostaat (eTwist) dat de ketel moet verwarmen.',
  'Gewenste aanvoer': 'De aanvoertemperatuur die de thermostaat op dit moment aan de ketel vraagt.',
  Modulatie:
    'Brandervermogen als % van het maximum. Onder het minimum kan de ketel niet verder terugregelen; dan schakelt hij aan en uit.',
  Minimumvermogen:
    'Het laagste vermogen waarop de brander stabiel kan branden. Vraagt het huis minder, dan ontstaan korte cycli.',
  ΔT: 'Verschil tussen aanvoer- en retourtemperatuur: hoeveel het water onderweg is afgekoeld, dus hoeveel warmte is afgegeven.',
  'Max. aanvoer':
    'De hoogste temperatuur die de ketel voor verwarming mag leveren. Lager is vaak zuiniger, maar kan te weinig warmte geven.',
  Setpoint: 'De ingestelde doeltemperatuur van een ruimte.',
  Terugdraaicriterium:
    'Een grens die je vooraf vastlegt. Wordt die overschreden, dan zet je de wijziging terug.',
  Vloerverwarming:
    'Reageert traag en krijgt via de mengverdeler al een lagere temperatuur. Een lagere ketelaanvoer merk je daar vaak als eerste.',
  'CAN-bus': 'De datalijn waarover de ketel zijn meetwaarden aan Home Assistant doorgeeft.',
  'Onbekende tijd':
    'Tijd zonder gegevens. Telt niet als "brander uit", zodat statistieken niet vertekenen.',
  Mengverdeler:
    'Mengt heet ketelwater met koeler retourwater tot een geschikte temperatuur voor de vloer. Dat circuit gedraagt zich daardoor anders dan de ketel.',
  Tapwater:
    'Warm water voor kraan en douche. De ketel stookt dan heter; die cycli tellen niet mee in de cv-analyse.',
  Naloop: 'Na het branden draait de pomp nog even door om restwarmte uit de ketel af te voeren.',
} as const;

export type GlossaryTerm = keyof typeof GLOSS;

/** Terms shown in 'Begrippen in deze bevinding', per finding id. */
export const TERMS: Readonly<Record<string, readonly GlossaryTerm[]>> = {
  'B-014': ['Pendelen', 'Warmtevraag', 'Gewenste aanvoer', 'Modulatie', 'Minimumvermogen', 'ΔT'],
  'B-011': ['Max. aanvoer', 'Setpoint', 'Terugdraaicriterium', 'Vloerverwarming'],
  'B-015': ['CAN-bus', 'Onbekende tijd'],
  'B-012': ['Mengverdeler', 'ΔT'],
  'B-016': ['Tapwater', 'Naloop'],
};

/** KPI explanations keyed by KPI label. */
export const KPI_EXPLANATIONS: Readonly<Record<string, string>> = {
  Aanvoer: 'Temperatuur van het water van de ketel naar radiatoren en vloer.',
  Retour: 'Temperatuur van het water terug naar de ketel. Lager = meer warmte afgegeven.',
  Modulatie: 'Brandervermogen als % van het maximum.',
  Woonkamer: 'Gemeten door de eTwist; deze bepaalt de warmtevraag.',
  Slaapkamer: 'Losse sensor; stuurt de ketel niet aan.',
  Buiten: 'Gebruikt om perioden met vergelijkbaar weer te vergelijken.',
};

export function kpiExplanation(label: string): string {
  return KPI_EXPLANATIONS[label] ?? '';
}
