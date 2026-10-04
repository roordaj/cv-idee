import {
  Activity,
  Bell,
  History,
  House,
  LayoutDashboard,
  Lightbulb,
  Plug,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  type LucideIcon,
} from 'lucide-react';
import type { Tone } from '../lib/semantics.ts';

export type ScreenKey =
  | 'overzicht'
  | 'bevindingen'
  | 'cycli'
  | 'wijzigingen'
  | 'historie'
  | 'signalen'
  | 'installatie'
  | 'kwaliteit'
  | 'meldingen'
  | 'analyse-instellingen';

export interface ScreenDef {
  key: ScreenKey;
  /** Route path relative to the router basename (Dutch slugs from design v3). */
  path: string;
  /** Sidebar label. */
  label: string;
  /** Page heading (design v3 h1; some differ from the nav label). */
  title: string;
  /** Static subtitle from design v3, where the design has one that does not depend on data. */
  subtitle?: string;
  icon: LucideIcon;
  tone: Tone;
  section: 'analyse' | 'instellingen';
}

export const SCREENS: readonly ScreenDef[] = [
  {
    key: 'overzicht',
    path: 'overzicht',
    label: 'Overzicht',
    title: 'Overzicht',
    subtitle: 'Status van je installatie',
    icon: LayoutDashboard,
    tone: 'orange',
    section: 'analyse',
  },
  {
    key: 'bevindingen',
    path: 'bevindingen',
    label: 'Bevindingen',
    title: 'Bevindingen',
    icon: Lightbulb,
    tone: 'orange',
    section: 'analyse',
  },
  {
    key: 'cycli',
    path: 'cycli',
    label: 'Cycli',
    title: 'Cycli',
    icon: Activity,
    tone: 'orange',
    section: 'analyse',
  },
  {
    key: 'wijzigingen',
    path: 'wijzigingen',
    label: 'Wijzigingen',
    title: 'Wijzigingen',
    icon: SlidersHorizontal,
    tone: 'violet',
    section: 'analyse',
  },
  {
    key: 'historie',
    path: 'historie',
    label: 'Advieshistorie',
    title: 'Advieshistorie',
    subtitle: 'Elk advies met de meetperiode, instellingen en regelversie van dat moment',
    icon: History,
    tone: 'violet',
    section: 'analyse',
  },
  {
    key: 'signalen',
    path: 'signalen',
    label: 'Signalen',
    title: 'Signaalkoppeling',
    icon: Plug,
    tone: 'teal',
    section: 'instellingen',
  },
  {
    key: 'installatie',
    path: 'installatie',
    label: 'Installatie',
    title: 'Installatieprofiel',
    icon: House,
    tone: 'blue',
    section: 'instellingen',
  },
  {
    key: 'kwaliteit',
    path: 'kwaliteit',
    label: 'Gegevenskwaliteit',
    title: 'Gegevenskwaliteit',
    icon: ShieldCheck,
    tone: 'amber',
    section: 'instellingen',
  },
  {
    key: 'meldingen',
    path: 'meldingen',
    label: 'Meldingen',
    title: 'Meldingen',
    subtitle: 'Eén melding per probleem, niet per cyclus',
    icon: Bell,
    tone: 'rose',
    section: 'instellingen',
  },
  {
    key: 'analyse-instellingen',
    path: 'instellingen/analyse',
    label: 'Analyse-instellingen',
    title: 'Analyse-instellingen',
    icon: Settings2,
    tone: 'slate',
    section: 'instellingen',
  },
];
