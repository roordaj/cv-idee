# Ontwerpaanvullingen op v3 — instellingen, onboarding, dialogen, staten en markers

Versie 1.0 · 4 oktober 2026 · Refinement [#6](https://github.com/roordaj/cv-idee/issues/6)

Ontwerp v3 ([`CV-analyse-v3.dc.html`](CV-analyse-v3.dc.html)) dekt de hoofdschermen. Dit document beschrijft wat ontbreekt, precies genoeg om zonder vragen te bouwen. **v3 blijft leidend**: alles hieronder hergebruikt de visuele taal, componenten en toon van v3 (niet het "Modernist"-design system). Waar dit document afwijkt van v3 staat dat er expliciet bij, met reden.

Inhoud:

- [0. Gedeelde bouwstenen](#0-gedeelde-bouwstenen) — tokens, componenten, dialoog, formulierregels
- [1. Analyse-instellingen](#1-analyse-instellingen) — drempels en parameters (FR-03, FR-11, FR-14, FR-39, FR-41)
- [2. Eerste start (onboarding)](#2-eerste-start-onboarding) — HA-verbinding, signalen, historie (FR-01, FR-06)
- [3. Dialoog Periode markeren en entiteitkiezer](#3-dialoog-periode-markeren-en-entiteitkiezer) (FR-10, FR-01)
- [4. Historische import](#4-historische-import) — starten, voortgang, resultaat (FR-06)
- [5. Laadstaten, lege staten en foutstaten](#5-laadstaten-lege-staten-en-foutstaten) — per scherm, incl. Overzicht bij onvoldoende gegevens (FR-36)
- [6. Wijzigingsmarkers in grafieken](#6-wijzigingsmarkers-in-grafieken) (FR-29)
- [7. Openstaande ontwerpvragen](#7-openstaande-ontwerpvragen)
- [8. Verbruiksscherm (FR-31)](#8-verbruiksscherm-fr-31)

---

## 0. Gedeelde bouwstenen

### 0.1 Tokens (uit v3, ongewijzigd)

| Token | Waarde | Gebruik |
|---|---|---|
| Font | Plus Jakarta Sans 400/500/600/700/800, basis 14px / 1.5, `tabular-nums` | alles |
| `--bg` | `#f4f5f8` | paginaachtergrond, hover van secundaire knoppen, segmented-control-bak |
| `--text` | `#1d2433` | tekst |
| `--text-2` | `#5b6475` | subtekst, labels |
| `--muted` | `#8a92a3` | meta, eenheden, placeholders |
| `--strong-2` | `#3d4452` | nav-tekst, legenda |
| `--border` | `#e7e9ee` | kaartranden, scheidingslijnen |
| `--border-input` | `#dfe2e8` | invoervelden, secundaire knoppen |
| `--row` | `#eef0f3` | tabelrijlijnen, rasterlijnen grafiek |
| `--subtle` | `#f8f9fb` | tabelkop, binnenvlak (mini-tijdlijn), hover lijstitem |
| `--link` | `#c2531f` (hover `#ea6a2f`) | tekstlinks, "Alles bekijken ›" |
| Focus | `outline: 2px solid #ea6a2f; outline-offset: 2px` | `:focus-visible` overal |
| Palet `C` | oranje `#ea6a2f/#fdeee6/#a2421a`, teal `#1a9e8f/#e1f4f1/#0f6b61`, violet `#7c5cd6/#efeafb/#563ba8`, blauw `#3b7ddd/#e7effb/#2659a8`, amber `#d99a12/#fcf3dc/#8a6206`, rose `#e0475b/#fce8eb/#a92536`, groen `#2f9e5b/#e4f4ea/#1d6b3c`, slate `#5b6475/#eef0f3/#3d4452` | (basis / tint / donker) |
| Arcering "geen gegevens" | `repeating-linear-gradient(45deg,#c3c8d2 0 2px,#f4f5f8 2px 5px)`; SVG-pattern 6×6, rotate 45°, rect 2×6 `#c3c8d2` | datagaten, onbekend |

### 0.2 Componenten uit v3 die hier worden hergebruikt

| Naam (frontend) | v3-bron | Stijl |
|---|---|---|
| `Card` | alle schermen | `background:#fff; border:1px solid #e7e9ee; border-radius:20px; padding:20px; gap:12–14px`. Kop `h3` 16px/700. |
| `TintCard` | "Aanbevolen actie", Beschikbare analyses, Bijzondere perioden | tintkleur als achtergrond, geen rand, radius 20px (groot) of 14px (tegel), padding 14–22px |
| `PageHeader` | Cycli, Signalen, … | 44×44 icoonbadge radius 14px (tint + basiskleur), `h1` 24px/800, subregel `#5b6475`. Overzicht gebruikt `h1` 28px/800 zonder badge. |
| `KpiTile` | Overzicht / Cycli | wit, rand, radius 16px, padding 16px (Cycli 14px), icoonbadge 36px r11 (Cycli 30px r9), label 12px `#5b6475`, waarde 22px/800, sub 12px (11px) `#8a92a3`, optionele uitleg 12px boven stippellijn `1px dashed #e7e9ee` |
| `Pill` | overal | `padding:3px 10px; border-radius:999px; font-size:12px; font-weight:600` (groot) of `2px 9px; 11px; 700` (klein); tint als achtergrond, donker als tekst |
| `Segmented` | Cycli-bereik, Meldingen | bak `#f4f5f8` (of wit met rand op Cycli), radius 12px, padding 4px, gap 4px; knop radius 9px, `padding:6–7px 14px`, 13px/600. Actief: wit + `box-shadow:0 1px 3px rgba(16,24,40,.12)` en tekst `#1d2433` (Meldingen-variant), of oranje met witte tekst (Cycli-variant, alleen voor tijdbereik) |
| `Toggle` | Meldingen | baan 40×24 radius 12px, padding 3px; aan `#1a9e8f`, uit `#c3c8d2`; knop 18px wit `box-shadow:0 1px 2px rgba(0,0,0,.2)`. Label rechts, 14px. Wordt als `role="switch"` met `aria-checked` gebouwd. |
| `Field` | Wijzigingen, Signalen | `label` kolom, gap 4px, 12px `#5b6475`; invoer `padding:9px 12px; border:1px solid #dfe2e8; border-radius:10px; font-size:14px; color:#1d2433` |
| `ButtonPrimary` | "Open advies", "Vastleggen" | `padding:10px 16px; border-radius:12px; background:#ea6a2f; color:#fff; font-weight:700`; hover `#d65a20`; icoon 18px links |
| `ButtonSecondary` | "Periode markeren", "Toon in tijdlijn" | `padding:8px 14px; border-radius:10px; border:1px solid #dfe2e8; background:#fff; font-weight:600`; hover `#f4f5f8` |
| `LinkButton` | "Alles bekijken ›", "Details ›" | geen rand, transparant, `#c2531f`, 600, chevron |
| `Callout` | uitlegbanner Cycli (violet), "Let op" Signalen (amber), resolutie Kwaliteit (teal) | `border-radius:16px; padding:14px 16px; font-size:13px; line-height:1.55; display:flex; gap:10px`, icoon 18px. Varianten: **uitleg** `#f3effc`/`#3f2a85` (icoon `book`), **let op** `#fcf3dc`/`#6b4c05` (`info`), **in orde** `#e1f4f1`/`#0f4f48` (`checkCircle`), **fout** (nieuw, zelfde patroon) `#fce8eb`/`#7a1d2a` (`alert`), **neutraal** (nieuw) `#eef0f3`/`#3d4452` (`info`) |
| `Table` | Alle cycli | kop `#f8f9fb`, 12px/600 `#5b6475`, cellen `padding:9px 12px`, rijlijn `1px solid #eef0f3`, 13px |
| `ListButton` | Bevindingen-zijlijst, Logboek | volle breedte, `padding:10px; border-radius:12–14px`, geselecteerd `background:#fff7f2` + `box-shadow:0 0 0 2px #ea6a2f inset` |
| `DefList` | Observatie / Toen vastgelegd | grid 2 kolommen, sleutel 12px `#8a92a3`, waarde 13px |

### 0.3 Nieuwe gedeelde componenten (in v3-stijl)

Deze bestaan niet in v3 en worden hier vastgelegd zodat elk scherm ze gelijk toont.

**`Dialog`** (modaal)
- Overlay `rgba(29,36,51,.45)`; paneel wit, `border-radius:20px`, `padding:24px`, `box-shadow:0 20px 48px rgba(16,24,40,.18)`, breedte `min(560px, 100vw − 32px)`, max-hoogte `calc(100vh − 64px)` met scroll in de body.
- Kop: 44px icoonbadge (r14, tint/basis van het onderwerp), titel `h2` 20px/800, optionele subregel 13px `#5b6475`; rechtsboven sluitknop (icoon `x`, 36×36, r10, hover `#f4f5f8`, `aria-label="Sluiten"`).
- Voet: rechts uitgelijnd `ButtonSecondary` "Annuleren" + `ButtonPrimary`; destructieve actie links (`DangerButton`, zie onder).
- **Smal (< 640 px viewport):** paneel wordt een *sheet* vanaf de onderkant: volle breedte, `border-radius:20px 20px 0 0`, max-hoogte 92vh, voet sticky onderaan met witte achtergrond en bovenrand `#e7e9ee`; knoppen volle breedte, primaire bovenaan.
- Focus: bij openen naar het eerste invoerveld (of de titel als er geen veld is); focus-trap; `Esc` sluit (met bevestiging als er gewijzigde velden zijn: "Wijzigingen weggooien?" — knoppen "Verder bewerken" / "Weggooien"); bij sluiten focus terug naar de knop die de dialoog opende. `role="dialog"`, `aria-modal="true"`, `aria-labelledby` = titel.

**`DangerButton`**: `ButtonSecondary`-maat, `border:1px solid #f3c3ca; color:#a92536; background:#fff`; hover `#fce8eb`.

**`EmptyState`** (binnen een `Card` of als paginablok): gecentreerd, `padding:32px 20px`, icoonbadge 52px r16 slate-tint (`#eef0f3`/`#5b6475`), titel 16px/700, tekst 14px `#5b6475` max 46ch, daaronder optioneel één `ButtonPrimary` of `ButtonSecondary`.

**`Skeleton`**: blokken `#eef0f3`, radius gelijk aan het element dat ze vervangen, puls-animatie opacity .55 → 1 (1,2 s, ease-in-out); `prefers-reduced-motion` → geen animatie. Het skelet volgt de echte layout (zelfde kaarten en grid), zodat er geen sprong is. Container krijgt `aria-busy="true"`; schermlezer-tekst "Laden…".

**`ErrorCallout`**: `Callout` variant fout + `ButtonSecondary` "Opnieuw proberen" (icoon `repeat`) + inklapbaar "Technische details" (12px `#8a92a3`: HTTP-status, endpoint, tijd).

**`StatusPill` in de header** (uitbreiding van v3 "Live · bijgewerkt 12:00"): zelfde pil (wit, rand, 13px) met gekleurde stip 8px + ring 3px in tint:

| Staat | Stip | Tekst |
|---|---|---|
| live | groen | `Live · bijgewerkt 12:00` |
| vertraagd (laatste waarneming > 2 min) | amber | `Vertraagd · laatste gegevens 11:52` |
| geen verbinding HA | rose | `Geen verbinding met Home Assistant · sinds 10:10` |
| importeren | blauw | `Historie importeren · 42 %` (klik → Gegevenskwaliteit, import-kaart) |
| herberekenen | violet | `Analyses herberekenen · 63 %` (klik → Analyse-instellingen) |
| stubdata (`CVIDEE_STUB_DATA=1`) | slate, extra pil | `Voorbeeldgegevens` |

Bron: `GET /api/status`.

### 0.4 Formulierregels (alle instellingen en dialogen)

- Getallen in `nl-NL`: komma als decimaalteken; invoer accepteert komma én punt, toont altijd komma. Eenheid staat als suffix *in* het veld rechts (12px `#8a92a3`, `padding-right` zodat tekst niet overlapt) en hoort bij het `aria-label` ("Kortecyclusgrens in minuten").
- Valideren bij verlaten van het veld (`blur`) en bij opslaan, niet bij elke toets. Fout: rand `#e0475b`, daaronder 12px `#a92536` met `alert`-icoon 14px, `aria-invalid="true"` + `aria-describedby`. Waarschuwing (opslaan mag wel): rand `#d99a12`, tekst `#8a6206`.
- Pijltjes ↑/↓ in een getalveld verhogen/verlagen met de stapgrootte; Shift+↑/↓ met 10× de stap.
- Tijden 24 u, `Europe/Amsterdam`; datumweergave "4 okt 2026 08:30". Datum/tijd-invoer met native `input type="date"` + `type="time"` (twee velden naast elkaar, op smal onder elkaar).
- Opslaan-knoppen tonen tijdens verzenden een spinner 16px in plaats van het icoon en zijn dan uitgeschakeld; daarna kort (3 s) een groene bevestiging 12px `#1d6b3c` met `check`: "Opgeslagen 12:04".

---

## 1. Analyse-instellingen

**Doel.** Alle grenswaarden waarmee de analyse patronen beoordeelt zichtbaar en instelbaar maken, met uitleg in gewone taal. Er bestaat geen universele norm voor een goed aantal starts, de juiste ΔT of aanvoertemperatuur; de app moet dat eerlijk laten zien.
**Requirements:** FR-03, FR-11 (§3 sensorleeftijd/resolutie), FR-14, FR-22, FR-30/32 (vergelijkbaarheid), FR-39 (herstelcriterium), FR-41 (snapshot), §4 "geen universele norm", §6 (gasprijs).
**API:** `GET /api/settings` (waarden + schema + standaardwaarden + historie), `PUT /api/settings` (gewijzigde waarden → nieuwe config-hash + herberekening), herberekeningsvoortgang via `GET /api/status` (`recompute`). Zie [#22](https://github.com/roordaj/cv-idee/issues/22).

### 1.1 Plaats in navigatie — besluit

Nieuw nav-item **"Analyse-instellingen"** in de sectie *Instellingen*, als laatste item (na Meldingen). Icoon lucide `settings-2`. Route `/instellingen/analyse`.

Waarom hier en niet in Installatie of Meldingen:
- *Installatie* beschrijft **feiten** over het huis en de ketel (FR-02/03): wat er is. Drempels zijn **beoordelingskeuzes**: wanneer iets als probleem telt. Die mengen maakt beide schermen onduidelijk.
- *Meldingen* gaat over **wie wanneer bericht krijgt**. Drempels bepalen of er überhaupt een bevinding is; dat staat los van het meldkanaal.
- Een eigen item onder *Instellingen* past in het bestaande patroon van v3 (één onderwerp per scherm) en het label zegt letterlijk wat het is.

Gevolgen voor bestaande v3-schermen (kleine afwijkingen, zie ook [§7](#7-openstaande-ontwerpvragen)):
- **Installatie › Instellingen en specificaties › Gasprijs**: de rij blijft zoals in v3 ("Niet ingesteld · besparing in euro niet beschikbaar"), maar wordt een link: klik → Analyse-instellingen, sectie *Kosten*, veld krijgt focus. Bewerken gebeurt op één plek.
- **Meldingen › Ruisonderdrukking › Herstelcriterium**: het vrije tekstveld uit v3 wordt een alleen-lezen samenvatting in dezelfde veldstijl (achtergrond `#f8f9fb`), opgebouwd uit de gestructureerde parameters, met `LinkButton` "Aanpassen in Analyse-instellingen ›". Reden: een vrij tekstveld kan niet door de regelengine worden gelezen en niet in de snapshot worden vergeleken.
- **Signalen › Signaal instellen › Max. leeftijd**: blijft bewerkbaar in het paneel (zoals v3). Het is dezelfde waarde als in de tabel *Gegevens per signaal* hieronder; beide schrijven naar `PUT /api/settings` (sleutel `signals.<rol>.max_age_s`).
- In de **rail** (< 960 px) verschijnt het icoon als vijfde onder de scheidingslijn, met `title="Analyse-instellingen"`.

### 1.2 Layout

Desktop (main-breedte ≥ 1060 px): sectie-index links (zoals de Bevindingen-zijlijst, 272 px, sticky `top:16px`), kaarten rechts. Main 700–1059 px: index wordt een horizontale rij `Pill`-ankers bovenaan (scrollbaar, `overflow-x:auto`, geen paginascroll). Onder 700 px: parameterrijen stapelen (label boven, invoer eronder).

```
┌ sidebar 240 ┬──────────────────────────────────────────────────────────────────────┐
│ Analyse     │ [Live · bijgewerkt 12:00] [CAN-bus via HA]           Zondag 4 okt 2026│
│  Overzicht  │                                                                      │
│  Bevindingen│ (⚙) Analyse-instellingen                                             │
│  Cycli      │     Grenzen waarmee de analyse patronen beoordeelt                   │
│  Wijzigingen│ ┌ uitleg (violet) ─────────────────────────────────────────────────┐ │
│  Advieshist.│ │ 📖 Er bestaat geen universele norm …                            │ │
│ Instellingen│ └──────────────────────────────────────────────────────────────────┘ │
│  Signalen   │ ┌ index (272) ─┐ ┌ Card: Korte cycli ─────────────────────────────┐ │
│  Installatie│ │▸Korte cycli  │ │ Kortecyclusgrens                  [ 3   min ]  │ │
│  Gegevenskw.│ │ Comfort      │ │ Een cv-cyclus die korter duurt …               │ │
│  Meldingen  │ │ Effectmeting │ │ Standaard 3 min · gebruikt door kort-branden   │ │
│ ▸Analyse-   │ │ Gegevens     │ │─────────────────────────────────────────────── │ │
│  instell.   │ │ Herstel      │ │ Minimum aantal korte cycli   (Gewijzigd) [ 6 ] │ │
│             │ │ Kosten       │ │ …                    Standaardwaarde herstellen│ │
│             │ │ Weergave     │ └────────────────────────────────────────────────┘ │
│             │ │──────────────│ ┌ Card: Comfort ─────────────────────────────────┐ │
│             │ │ Laatst gewijz│ │ …                                              │ │
│             │ │ 24 sep 10:12 │ └────────────────────────────────────────────────┘ │
│             │ └──────────────┘ ┌ Card: Eerdere wijzigingen ─────────────────────┐ │
│             │                  │ 24 sep 10:12 · Kortecyclusgrens 4 → 3 min      │ │
│ [Alleen-    │                  └────────────────────────────────────────────────┘ │
│  lezen …]   │ ┌ sticky opslaanbalk (alleen bij wijzigingen) ─────────────────────┐ │
│             │ │ 2 wijzigingen niet opgeslagen       [Annuleren] [Opslaan en her…]│ │
└─────────────┴─┴──────────────────────────────────────────────────────────────────┴─┘
```

Smal (< 640 px viewport, rail 72 px, padding 16 px):

```
┌72┬─────────────────────────────────┐
│🔥│ [● Live · 12:00] [CAN-bus via HA]│
│▦ │ (⚙) Analyse-instellingen        │
│💡│  Grenzen waarmee de analyse …    │
│〰│ ┌ uitleg ─────────────────────┐  │
│⇅ │ │ Er bestaat geen universele… │  │
│⟲ │ └─────────────────────────────┘  │
│──│ (Korte cycli)(Comfort)(Effect…)→ │
│🔌│ ┌ Korte cycli ────────────────┐  │
│⌂ │ │ Kortecyclusgrens            │  │
│🛡│ │ Een cv-cyclus die korter …  │  │
│🔔│ │ [ 3                   min ] │  │
│⚙ │ │ Standaard 3 min · kort-br…  │  │
│  │ └─────────────────────────────┘  │
│  │ ┌ opslaanbalk (sticky) ───────┐  │
│  │ │ 2 wijzigingen               │  │
│  │ │ [Opslaan en herberekenen  ] │  │
│  │ │ [Annuleren                ] │  │
└──┴─┴─────────────────────────────┴──┘
```

### 1.3 Componenten en stijl

- `PageHeader`: badge slate (`#eef0f3` / `#5b6475`), icoon `settings-2`; titel "Analyse-instellingen"; subregel "Grenzen waarmee de analyse patronen beoordeelt".
- Uitleg-`Callout` (violet), alleen als "uitleg tonen" aan staat (zoals de Cycli-banner).
- Per sectie één `Card` met `h3` + één zin intro (13px `#5b6475`). Rijen gescheiden door `border-top:1px solid #eef0f3`, rij-padding 14px 0.
- **Parameterrij** (`SettingRow`), grid `minmax(0,1fr) 200px`, gap 16px (onder 700 px: één kolom):
  - links: label 14px/700; uitleg 13px `#5b6475` (max 70ch); meta 12px `#8a92a3`: "Standaard 3 min · gebruikt door kort-branden v1.3". Als waarde ≠ standaard: `Pill` klein amber "Gewijzigd" achter het label en `LinkButton` 12px "Standaardwaarde herstellen".
  - rechts: `Field` met eenheid-suffix, of `Segmented`, of `Toggle`.
- Sectie-index: `ListButton`s (13px/600) met per sectie een teller-`Pill` slate als er gewijzigde waarden in zitten ("2"). Onderaan de index: 12px `#8a92a3` "Laatst gewijzigd 24 sep 10:12" + regel "Config-versie 7f3a…" (eerste 4 tekens van de config-hash; tooltip: volledige hash).
- **Opslaanbalk**: verschijnt alleen bij niet-opgeslagen wijzigingen; `position:sticky; bottom:16px`; wit, rand `#e7e9ee`, radius 16px, `box-shadow:0 8px 24px rgba(16,24,40,.12)`, padding 12px 16px; links 14px/600 "2 wijzigingen niet opgeslagen", rechts `ButtonSecondary` "Annuleren" + `ButtonPrimary` "Opslaan en herberekenen". Uitgeschakeld zolang er een validatiefout is (tekst links wordt dan `#a92536` "Los eerst 1 fout op").
- **Eerdere wijzigingen**: `Card` met `Table` (Wanneer · Instelling · Oud → nieuw · Door). Max 10 rijen, daarna `LinkButton` "Alles tonen".

### 1.4 Teksten

- Uitleg-callout: **"Er bestaat geen universele norm** voor een goed aantal branderstarts, de juiste ΔT of de beste aanvoertemperatuur. Deze grenzen zijn startwaarden die je aan je eigen installatie kunt aanpassen. Na opslaan worden de analyses opnieuw berekend. Elk advies bewaart de instellingen van het moment waarop het werd gegeven, zodat je in de Advieshistorie altijd ziet waarom het toen zo werd beoordeeld."
- Bevestigingsdialoog bij "Opslaan en herberekenen" (`Dialog`, badge slate `settings-2`):
  - Titel: "Instellingen opslaan en herberekenen?"
  - Tekst: "De analyses over de bewaarde gegevens (nu 4 jul – 4 okt) worden met de nieuwe grenzen opnieuw berekend. Dat duurt meestal enkele minuten; de app blijft bruikbaar. Bevindingen kunnen verschijnen of verdwijnen. Adviezen die al gegeven zijn, houden in de Advieshistorie hun oude instellingen."
  - Lijst van wijzigingen (DefList): "Kortecyclusgrens: 3 min → 4 min".
  - Knoppen: "Annuleren" / "Opslaan en herberekenen".
- Na opslaan: header-pil "Analyses herberekenen · 0 %" (violet); in de sectie-index een teal `Callout` klein "Opgeslagen 12:04. Herberekenen loopt." Als klaar: "Herberekend met de nieuwe instellingen (12:07)."
- Verlaten met niet-opgeslagen wijzigingen: `Dialog` "Wijzigingen niet opgeslagen" — "Je hebt 2 instellingen gewijzigd die nog niet zijn opgeslagen." — "Blijven" (primair) / "Weggooien" (`DangerButton`).

### 1.5 Parameters

Alle waarden komen uit het `params_schema` van de geregistreerde regels plus algemene instellingen ([#22](https://github.com/roordaj/cv-idee/issues/22)). De UI rendert **generiek uit het schema** (`title`, `description`, `default`, `minimum`, `maximum`, `x-unit`, `x-step`, `x-group`, `x-rule`); de tabel hieronder is de beoogde inhoud en de bron voor de teksten. Standaardwaarden zijn voorstellen (zie [§7](#7-openstaande-ontwerpvragen), vraag 4).

#### Sectie "Korte cycli" — intro: "Wanneer telt de app branden als *pendelen*? Alleen cv-cycli tijdens warmtevraag tellen mee; tapwater en gemarkeerde perioden nooit."

| Parameter (label) | Standaard | Eenheid · stap | Geldig bereik | Uitleg (UI-tekst) | Regel |
|---|---|---|---|---|---|
| Kortecyclusgrens | 3 | min · 0,5 | 1 – 15 | Een cv-cyclus die korter duurt dan deze grens én stopt terwijl de thermostaat nog warmte vraagt, telt als **korte cyclus**. | kort-branden |
| Warmtevraag na stop | 60 | s · 10 | 0 – 600 | Hoe lang de warmtevraag na het stoppen van de brander nog moet aanhouden om te spreken van "stop tijdens vraag". Voorkomt dat een cyclus die toevallig vlak voor het einde van de vraag stopt als pendelen telt. | stop-tijdens-vraag |
| Minimum aantal korte cycli | 4 | cycli · 1 | 2 – 30 | Zoveel korte cycli moeten er binnen één beoordeling zijn voordat de app een patroon meldt. Eén korte cyclus is nooit een waarschuwing. | kort-branden |
| Minimale observatieduur | 6 | uur · 1 | 1 – 72 | Zoveel uur met gegevens tijdens cv-bedrijf of warmtevraag is nodig voordat de app iets over cycli concludeert. Uren zonder gegevens tellen niet mee. | kort-branden, Overzicht |
| Herhaling over dagen | 2 van 7 | dagen · 1 | 1 – 14 van 3 – 28 | Een patroon heet **structureel** als het op minstens zoveel dagen binnen de periode voorkomt. Daarvoor is de zekerheid lager ("voorlopig"). Twee velden naast elkaar: "[2] van de laatste [7] dagen". Validatie: eerste ≤ tweede. | kort-branden (zekerheid) |
| *Bedrijfscontext* (alleen-lezen) | — | — | — | Regel 13px `#5b6475` met `info`-icoon: "Altijd uitgesloten: tapwatercycli, naloop en gemarkeerde perioden (opstookprotocol, onderhoud, …). Dit is niet instelbaar." | — |

#### Sectie "Comfort" — intro: "Wanneer telt een ruimte als te koud? Wordt gebruikt bij voor/na-vergelijkingen en terugdraaicriteria."

| Parameter | Standaard | Eenheid · stap | Bereik | Uitleg | Regel |
|---|---|---|---|---|---|
| Comfortgrens | 0,5 | °C · 0,1 | 0,1 – 3,0 | Een ruimte telt als **te koud** als de gemeten temperatuur meer dan zoveel graden onder het setpoint ligt. | voor-na |
| Toegestaan comfortverlies | 4 | u/week · 0,5 | 0 – 40 | Standaard terugdraaicriterium per ruimte: zoveel uur per week mag een ruimte te koud zijn na een wijziging. Daarboven adviseert de app terugdraaien. Een advies kan een eigen grens hebben; die staat dan bij het advies. | voor-na |

#### Sectie "Effectmeting" — intro: "Hoe vergelijkt de app de periode vóór en ná een wijziging?"

| Parameter | Standaard | Eenheid · stap | Bereik | Uitleg | Regel |
|---|---|---|---|---|---|
| Lengte vergelijkingsperiode | 7 | dagen · 1 | 3 – 28 | Even lange periode vóór en ná de wijziging. Gemarkeerde perioden worden eruit gelaten. | voor-na |
| Vergelijkbaar weer | 2,0 | °C · 0,5 | 0,5 – 6,0 | Verschil in gemiddelde buitentemperatuur waarbinnen de perioden **vergelijkbaar** zijn. | voor-na |
| Beperkt vergelijkbaar weer | 4,0 | °C · 0,5 | 1,0 – 10,0 | Tot dit verschil is de vergelijking **beperkt** (lagere zekerheid); daarboven rapporteert de app geen effect. Validatie: ≥ "Vergelijkbaar weer". | voor-na |
| Minimale dekking per periode | 90 | % · 1 | 50 – 100 | Zoveel procent van de tijd moeten de benodigde signalen gegevens hebben in beide perioden. | voor-na |

#### Sectie "Gegevens" — intro: "Wanneer is een meting te oud, en is de meetresolutie fijn genoeg voor de cyclusgrens?"

| Parameter | Standaard | Eenheid · stap | Bereik | Uitleg | Regel |
|---|---|---|---|---|---|
| Minimale dekking voor een beoordeling | 80 | % · 1 | 50 – 100 | Onder deze dekking van de kernsignalen (vlamstatus, modus, aanvoer) toont het Overzicht "Onvoldoende gegevens" en geeft de app geen beoordeling. | Overzicht, zekerheid |
| Gewenste meetresolutie vlamstatus | 10 | s · 1 | 1 – 60 | Hoe vaak de vlamstatus minimaal ververst moet worden. Is de werkelijke resolutie grover, dan wordt de korte-cycli-analyse **beperkt** of **niet beschikbaar**. Ernaast, alleen-lezen: "Werkelijk: 4 s" met groene of amber `Pill`. Waarschuwing (amber) als waarde > kortecyclusgrens ÷ 4: "Met deze resolutie zijn cycli van 3 min niet betrouwbaar te onderscheiden." | beschikbaarheid |
| Bewaartermijn ruwe gegevens | 180 | dagen · 30 | 30 – 730 | Ruwe meetwaarden ouder dan dit worden opgeruimd. Afgeleide cycli, bevindingen en advieshistorie blijven bewaard. Verkorten toont een waarschuwing: "Gegevens ouder dan X worden bij de volgende opruimronde verwijderd. Herberekenen over die periode kan daarna niet meer." | opslag |

**Tabel "Gegevens per signaal"** (in dezelfde kaart, `Table`; op smal per signaal een blok):

| Kolom | Inhoud |
|---|---|
| Signaal | naam (zoals Signalen), daaronder entity_id 12px `#8a92a3` of "Niet gekoppeld" |
| Verwacht regelmatige updates | `Toggle`. Uitleg in kolomkop-tooltip: "Aan als het signaal ook zonder verandering regelmatig een waarde stuurt. Alleen dan kan de app aan de leeftijd zien dat een meting verouderd is." |
| Max. leeftijd | `Field` met eenheid-`Segmented` (s / min / u) — uitgeschakeld (grijs, "n.v.t.") als de toggle uit staat |
| Werkelijk | alleen-lezen: mediane update-interval laatste 24 u, `Pill` groen/amber |

Standaard max. leeftijd per signaal (uit v3): ketelsignalen (vlam, modus, gewenste aanvoer, aanvoer, retour, modulatie) **30 s**; kamertemperaturen **10 min**; buitentemperatuur **15 min**; verdeleraanvoer/-retour, zonevraag/klep, pomp/debiet **1 min**; gasverbruik en warmtemeter **1 u**. Bereik 5 s – 24 u. Standaard "verwacht regelmatige updates": aan voor kamer- en buitentemperatuur, uit voor de rest tot de CAN-inventarisatie ([#5](https://github.com/roordaj/cv-idee/issues/5)) en ADR-003 ([#9](https://github.com/roordaj/cv-idee/issues/9)) anders besluiten.

#### Sectie "Herstel" — intro: "Wanneer is een probleem echt voorbij? Een bevinding en de bijbehorende melding sluiten pas daarna. Een datagat telt nooit als herstel."

| Parameter | Standaard | Eenheid · stap | Bereik | Uitleg |
|---|---|---|---|---|
| Dagen zonder patroon | 3 | dagen · 1 | 1 – 14 | Zoveel aaneengesloten dagen moet het patroon weg zijn. |
| Alleen bij vergelijkbaar weer | aan | `Toggle` | — | Herstel telt alleen als het weer vergelijkbaar is met de periode waarin het patroon optrad (zie *Vergelijkbaar weer*). |
| Minimale dekking in herstelperiode | 90 | % · 1 | 50 – 100 | Zoveel procent gegevens is nodig in de herstelperiode. |
| Uitstellen standaard | 7 | dagen · 1 | 1 – 60 | Termijn achter de knop "Uitstellen" bij een advies. De knoptekst volgt deze waarde ("Uitstellen 7 d"). |

Samenvattingszin (ook gebruikt op Meldingen): "{n} dagen zonder patroon, bij vergelijkbaar weer en ≥ {p} % gegevens" — gelijk aan de v3-tekst bij standaardwaarden.

#### Sectie "Kosten" — intro: "Optioneel. Zonder gasprijs toont de app nooit bedragen in euro's."

| Parameter | Standaard | Eenheid · stap | Bereik | Uitleg |
|---|---|---|---|---|
| Gasprijs | leeg | € per m³ · 0,01 | 0,01 – 10,00 (of leeg) | Gebruik je all-in prijs per m³ (inclusief energiebelasting en btw, zonder vaste leveringskosten). **Leeg laten = geen euro's.** Besparingen in euro worden altijd met deze prijs en de aannames erbij getoond. Een gasprijs alleen is niet genoeg: er moet ook een gasmeter gekoppeld zijn. |

Onder het veld, als geen gasmeter gekoppeld is: `Callout` neutraal "Er is geen gasmeter gekoppeld, dus euro's kunnen ook met een gasprijs nog niet worden berekend. Gasmeter koppelen ›".

#### Sectie "Weergave"

| Parameter | Standaard | Uitleg |
|---|---|---|
| Uitleg tonen | aan (`Toggle`) | Toont uitleg bij kengetallen, begrippen bij bevindingen en de uitlegbanners. (Plan §3.10; per browser opgeslagen *én* in settings, zie [#13](https://github.com/roordaj/cv-idee/issues/13).) |
| Requirement-ID's tonen | uit (`Toggle`) | Alleen zichtbaar in dev-modus. |
| Eerste start opnieuw doorlopen | `ButtonSecondary` "Eerste start openen" | Opent de onboarding (§2) zonder iets te wissen. |

### 1.6 Staten en validatie

- **Laden:** skelet van index + 3 kaarten met elk 3 rijen.
- **Fout bij laden:** `ErrorCallout` "Kon de instellingen niet laden. De analyse draait door met de laatst opgeslagen instellingen." Geen formulier tonen (nooit standaardwaarden tonen alsof ze actief zijn).
- **Fout bij opslaan (422):** veldfouten van de server op de betreffende rijen tonen; opslaanbalk "Niet opgeslagen: 1 waarde is ongeldig". **(409, iemand anders heeft intussen opgeslagen):** `Dialog` "Instellingen zijn intussen gewijzigd" — "Sinds je deze pagina opende zijn de instellingen opgeslagen vanaf een ander venster. Herlaad om de nieuwste waarden te zien; je eigen wijzigingen gaan dan verloren." — "Herladen". **(Netwerk):** `ErrorCallout` boven de opslaanbalk, invoer blijft staan.
- **Tijdens herberekenen:** instellingen blijven bewerkbaar; nieuw opslaan start een nieuwe herberekening die de lopende vervangt (bevestigingsdialoog meldt dat: "Er loopt al een herberekening; die wordt vervangen.").
- Validatie per veld volgens bereik in de tabel; leeg veld is alleen geldig bij Gasprijs. Kruisvalidaties: herhaling *x ≤ y*; beperkt weer ≥ vergelijkbaar weer; resolutie ≤ kortecyclusgrens ÷ 4 (waarschuwing, geen fout).
- **Snapshot:** de UI hoeft niets extra's te doen; `PUT` levert een nieuwe config-hash die backend in runs en `recommendation_snapshots` vastlegt. In de Advieshistorie (v3, "Toen vastgelegd › Instellingen") verschijnen de relevante drempels, bv. "Kortecyclusgrens 3 min · min. 4 korte cycli · max aanvoer 60 °C".

### 1.7 Toetsenbord en focus

- Tab-volgorde: index → kaarten van boven naar beneden → opslaanbalk. Index-items zijn ankers; Enter scrolt naar de kaart en zet focus op de `h3` (`tabindex="-1"`).
- Rij "Standaardwaarde herstellen" zet de waarde terug en houdt focus op het veld.
- `Ctrl/Cmd+S` = opslaan (opent de bevestigingsdialoog) als er wijzigingen zijn.

---

## 2. Eerste start (onboarding)

**Doel.** Een nieuwe installatie in drie stappen naar een eerste analyse brengen: verbinding met Home Assistant controleren, signalen koppelen, historie importeren.
**Requirements:** FR-01, FR-04, FR-06, FR-36 (geen misleidend oordeel zolang dit niet af is).
**API:** `GET /api/status` (`ha`, `mqtt`, `setup`), `GET /api/ha/entities`, `GET /api/signals`, `PUT /api/signals/{role}`, `GET /api/analyses`, `POST /api/import` + `GET /api/import/{id}`, `PUT /api/settings` (`onboarding.completed_at`).

### 2.1 Plaats en bereikbaarheid — besluit

- Route `/welkom`. Wordt **automatisch** geopend bij het starten van de app zolang `setup.onboarding_done = false` én er nog geen vlamstatus gekoppeld is. Daarna nooit meer automatisch.
- Geen eigen nav-item (het is eenmalig). Opnieuw bereikbaar via Analyse-instellingen › Weergave › "Eerste start openen", en via de inrichtingsbanner op Overzicht.
- Layout: dezelfde app-shell, maar de zijbalk toont in plaats van de navigatie een **stappenlijst** (zelfde breedte 240 px, zelfde logo bovenaan, zelfde "Alleen-lezen"-blok onderaan). Zo voelt het als dezelfde app, zonder dat de gebruiker naar lege schermen kan navigeren. In rail-modus (< 960 px) verdwijnt de zijbalk en komt er boven de inhoud een voortgangsregel.
- "Later afmaken" (`LinkButton`, rechtsboven in de inhoud) sluit de onboarding; de gewone navigatie verschijnt. Overzicht toont dan de inrichtingsbanner (§5c).

### 2.2 Wireframes

Desktop:

```
┌ 240 ─────────────────┬────────────────────────────────────────────────────────────┐
│ 🔥 CV-analyse         │                                          Later afmaken ›   │
│    Thuis · Calenta Ace│ Welkom bij CV-analyse                                     │
│                       │ In drie stappen naar je eerste analyse. Deze app leest     │
│ Inrichten             │ alleen; hij stuurt niets aan.                              │
│ (✓) 1 Verbinding      │ ┌ Card ───────────────────────────────────────────────────┐ │
│ (2) 2 Signalen        │ │ Stap 2 van 3                                            │ │
│     koppelen     ◀    │ │ Signalen koppelen                                       │ │
│ ( ) 3 Historie        │ │ Koppel minimaal de vlamstatus. Hoe meer signalen, hoe   │ │
│     importeren        │ │ meer analyses beschikbaar worden.  [Voorstellen zoeken] │ │
│ ( ) Klaar             │ │ ── Minimaal nodig ───────────────────────────────────── │ │
│                       │ │ 🔥 Brander/vlam actief  binary_sensor.remeha_flame  [✎] │ │
│                       │ │ ── Sterk aanbevolen ─────────────────────────────────── │ │
│                       │ │ ◎ CV-/tapwatermodus  (Voorstel) sensor.remeha_status    │ │
│                       │ │                                [Overnemen] [Andere…]    │ │
│                       │ │ 🌡 Ketelaanvoer          Nog niet gekoppeld  [Kiezen…]  │ │
│                       │ │ ── Optioneel (later ook via Signalen) ▸ ────────────── │ │
│                       │ └─────────────────────────────────────────────────────────┘ │
│                       │ ┌ Wat je hiermee kunt ────────────────────────────────────┐ │
│                       │ │ [Cycli: Beschikbaar][Temperatuur: Beperkt][Comfort: Niet]│ │
│ [🛡 Alleen-lezen …]   │ └─────────────────────────────────────────────────────────┘ │
│                       │                               [← Vorige]  [Volgende →]     │
└───────────────────────┴────────────────────────────────────────────────────────────┘
```

Smal (< 960 px: geen zijbalk; < 640 px: knoppen volle breedte):

```
┌─────────────────────────────────┐
│ 🔥 CV-analyse    Later afmaken ›│
│ Stap 2 van 3 · Signalen koppelen│
│ [■■■■■■■■■■□□□□□□□□□□]          │
│ ┌ Card ───────────────────────┐ │
│ │ Signalen koppelen           │ │
│ │ Koppel minimaal …           │ │
│ │ [Voorstellen zoeken       ] │ │
│ │ Minimaal nodig              │ │
│ │ 🔥 Brander/vlam actief      │ │
│ │ binary_sensor.remeha_flame  │ │
│ │                     [Wijzig]│ │
│ └─────────────────────────────┘ │
│ [Volgende →                   ] │
│ [← Vorige                     ] │
└─────────────────────────────────┘
```

### 2.3 Componenten

- Stappenlijst (zijbalk): items in nav-knopstijl (`padding:9px 12px; border-radius:10px`), met een rondje 24px links: open = rand `#dfe2e8` + nummer `#5b6475`; actief = oranje `#ea6a2f` met wit nummer, item-achtergrond `#fdeee6`, tekst `#a2421a` 700; klaar = groen `#2f9e5b` met wit `check`. Sectiekop "Inrichten" (11px/600 `#8a92a3`, zoals "Analyse"). Een eerdere stap is klikbaar; een latere alleen als de vorige klaar is. `aria-current="step"` op de actieve.
- Voortgangsregel (smal): 13px/600 "Stap 2 van 3 · Signalen koppelen" + balk 6px radius 3px, achtergrond `#eef0f3`, vulling `#ea6a2f`.
- Stapinhoud in één `Card` (max-breedte 760 px), kop: 12px/700 `#a2421a` "Stap 2 van 3", titel 22px/800, intro 14px `#5b6475`.
- Navigatie onder de kaart: `ButtonSecondary` "← Vorige", `ButtonPrimary` "Volgende →" (rechts).
- Hergebruik: analysetegels uit Overzicht › "Beschikbare analyses" (compacte variant: alleen icoon + naam + status-`Pill`), `EntityPicker` (§3b), `ImportPanel` (§4).

### 2.4 Stap 1 — Verbinding met Home Assistant

Wordt bij openen automatisch gecontroleerd (`GET /api/status`, opnieuw elke 5 s zolang niet verbonden).

| Staat | Weergave |
|---|---|
| Controleren | Skeleton-regel + 13px `#5b6475` "Verbinding met Home Assistant controleren…" |
| Verbonden | `Callout` in orde: "**Verbonden met Home Assistant {versie}** via {de add-on \| {HA_URL}}. {n} entiteiten gevonden." "Volgende" actief. |
| Geen verbinding (add-on) | `Callout` fout: "**Geen verbinding met Home Assistant.** De add-on kon Home Assistant niet bereiken via de Supervisor. Herstart de add-on; helpt dat niet, bekijk dan het logboek van de add-on." + "Opnieuw controleren" |
| Geen verbinding (standalone, onbereikbaar) | "**Home Assistant is niet bereikbaar op {HA_URL}.** Controleer het adres en of Home Assistant draait. Het adres stel je in met de omgevingsvariabele `HA_URL`; herstart daarna de container." |
| Token geweigerd (401) | "**Home Assistant weigert het toegangstoken.** Maak in Home Assistant onder *Profiel › Beveiliging* een nieuw *long-lived access token* en zet het in de omgevingsvariabele `HA_TOKEN`; herstart daarna de container." |

De app vraagt **nooit** om een token in de UI (plan §3.1: token via omgeving). Daaronder, niet blokkerend, de MQTT-regel (13px, met icoon):
- broker gevonden (teal `checkCircle`): "Samenvattingen verschijnen in Home Assistant als apparaat *CV-analyse* (via MQTT)."
- geen broker (amber `info`): "Geen MQTT-broker gevonden. Samenvattingen worden via de terugvaloptie naar Home Assistant gestuurd; installeer de Mosquitto-add-on voor stabiele entiteiten. Dit kan later."

"Volgende" is uitgeschakeld tot de verbinding er is; tooltip "Eerst verbinding met Home Assistant nodig".

### 2.5 Stap 2 — Signalen koppelen

- Intro: "Koppel de Home Assistant-entiteiten aan wat ze betekenen. Minimaal de vlamstatus is nodig; elk extra signaal maakt meer analyses mogelijk. Een ontbrekend signaal blokkeert alleen de analyses die het nodig hebben."
- `ButtonSecondary` "Voorstellen zoeken" (icoon `search`): vraagt voorstellen op basis van entity_id, `device_class` en eenheid (bv. `*_flame` → vlamstatus). Voorstellen worden **nooit** automatisch opgeslagen: rij krijgt `Pill` violet "Voorstel" + knoppen "Overnemen" / "Andere kiezen…". Bovenaan dan `LinkButton` "Alle {n} voorstellen overnemen".
- Groepen (kop 12px/700 `#5b6475` met lijn):
  - **Minimaal nodig:** Brander/vlam actief.
  - **Sterk aanbevolen:** CV-/tapwatermodus, gewenste ketelaanvoer, ketelaanvoer, ketelretour, brander-modulatie, kamertemp. woonkamer, buitentemperatuur.
  - **Optioneel** (ingeklapt, "Toon 7 optionele signalen"): overige rollen uit v3 (slaapkamer, verdeler, zone, pomp, gas, warmtemeter).
- Rij: icoonbadge 32px (zoals Signalen-kaart), naam 14px/700, entity_id of "Nog niet gekoppeld" (`#8a92a3`), "Nodig voor …" 12px; rechts `ButtonSecondary` "Kiezen…" / "Wijzigen". Kiezen opent de `EntityPicker`; na kiezen wordt de koppeling direct opgeslagen (`PUT /api/signals/{role}`) met de standaardvelden (eenheid uit HA, soort waarde uit de catalogus). Locatie en betekenis vult de gebruiker later in Signalen aan; regel 12px: "Locatie en betekenis vul je later aan onder Signalen."
- Kaart "Wat je hiermee kunt": analysetegels, live bijgewerkt na elke koppeling (`GET /api/analyses`).
- "Volgende" uitgeschakeld zonder vlamstatus (tooltip "Koppel eerst de vlamstatus"). Ontbreekt een aanbevolen signaal, dan bij "Volgende" een amber `Callout` boven de knoppen (één keer): "Zonder **CV-/tapwatermodus** kan de app tapwater niet van verwarming scheiden. Conclusies krijgen dan een lagere zekerheid. Je kunt dit later koppelen." + "Toch verder" / "Nu koppelen".

### 2.6 Stap 3 — Historie importeren

- Intro: "Home Assistant bewaart meestal de laatste 10 dagen. Door die te importeren heb je direct een eerste analyse, in plaats van na een paar dagen. De import gebruikt precies dezelfde analyse als live gegevens."
- Inhoud: `ImportPanel` (§4) met standaardkeuze "Alles wat Home Assistant bewaart".
- Knoppen: "Overslaan" (`ButtonSecondary`; tekst daaronder 12px "Dan begint de analyse vanaf nu.") en "Importeren en verder" (primair). Tijdens de import: "Verder — import loopt op de achtergrond door" (primair).

### 2.7 Klaar

- Groene icoonbadge 52px `checkCircle`, titel "Klaar om te analyseren".
- Tekst afhankelijk van situatie:
  - met import: "De historie van {van} tot {tot} is geïmporteerd ({n} cycli gevonden). Het Overzicht toont nu je eerste beoordeling."
  - zonder import / import loopt: "De analyse loopt vanaf nu. Na minimaal {minimale observatieduur} uur met cv-bedrijf verschijnt de eerste beoordeling; tot die tijd toont het Overzicht 'Onvoldoende gegevens'."
- Checklist "Nog te doen (optioneel)" — `ListButton`s met chevron: "Installatieprofiel invullen (radiatoren, mengverdeler)", "Locatie en betekenis van signalen aanvullen", "Analyse-instellingen bekijken", "Meldingen instellen".
- `ButtonPrimary` "Naar het Overzicht". Zet `onboarding.completed_at`.

---

## 3. Dialoog Periode markeren en entiteitkiezer

### 3a. Periode markeren

**Doel.** Perioden markeren als opstookprotocol, onderhoud, ontluchten, test, vakantie of bijzonder gebruik. Ze blijven zichtbaar, maar tellen standaard niet mee voor normaalgedrag en wijzigingsvergelijkingen.
**Requirements:** FR-10, FR-30/32 (uitsluiting in vergelijkingen), scenario 9.
**API:** `GET /api/periods`, `POST /api/periods`, `DELETE /api/periods/{id}`; bewerken via `PUT /api/periods/{id}` (ontbreekt in plan §3.9 — zie [§7](#7-openstaande-ontwerpvragen), vraag 8).
**Bereikt via:** Gegevenskwaliteit › Bijzondere perioden › "Periode markeren" (v3-knop, opent nieuw) en klik op een bestaande periodekaart (opent bewerken). Ook: Cycli › tijdlijn — na selectie van een tijdvak (§6.5) de knop "Periode markeren" in de selectiebalk, dialoog vooringevuld met van/tot.

Wireframe (desktop, 560 px):

```
┌──────────────────────────────────────────────────────┐
│ (📅) Periode markeren                            [×]  │
│      Telt standaard niet mee voor normaal gedrag     │
│                                                      │
│ Soort                                                │
│ (Opstookprotocol)(Onderhoud)(Ontluchten)             │
│ (Test)(Vakantie)(Bijzonder gebruik)                  │
│ ┌ uitleg bij gekozen soort (tint) ─────────────────┐ │
│ │ Vakantie: thermostaat lager, weinig warmtevraag… │ │
│ └──────────────────────────────────────────────────┘ │
│ Van                         Tot                      │
│ [17-09-2026][00:00]         [19-09-2026][23:59]      │
│ [ ] Loopt nog (geen einddatum)                       │
│ Omschrijving (optioneel)                             │
│ [Thermostaat op 15 °C                            ]   │
│                                                      │
│ Niet meetellen voor                                  │
│ [●] Normaal gedrag en referentie                     │
│ [●] Voor/na-vergelijkingen van wijzigingen           │
│ [●] Bevindingen (cv-conclusies over deze periode)    │
│                                                      │
│ ⚠ Overlapt met 'Onderhoud 18 sep'. Mag, …            │
│                                                      │
│ [Verwijderen]                 [Annuleren] [Markeren] │
└──────────────────────────────────────────────────────┘
```

Smal: sheet (§0.3); soortkeuze blijft als wrap-chips; van/tot onder elkaar.

**Componenten en tokens.**
- Badge: blauw `calendar` (nieuw) of in de tint van de gekozen soort (bewerken).
- Soortkeuze: `role="radiogroup"` met chips (`Pill` groot, `padding:7px 12px`, 13px/600). Niet gekozen: `#f4f5f8`/`#3d4452`; gekozen: tint + donker van de soort en `box-shadow:0 0 0 2px <basis> inset`. Kleuren per soort (v3 voor de eerste drie; nieuw voor de rest, consistent met het palet):

| Soort | Kleur | Uitlegtekst in de dialoog |
|---|---|---|
| Opstookprotocol | oranje | "Nieuwe (vloer)verwarming wordt volgens schema opgestookt. Het gedrag is bewust afwijkend." |
| Onderhoud | slate | "Monteur aan het werk; ketel kan aan/uit gaan of op testwaarden staan." |
| Ontluchten | teal | "Radiatoren of vloer ontlucht; pomp en temperaturen gedragen zich tijdelijk anders." |
| Test | violet | "Je probeert zelf iets uit, bijvoorbeeld een andere instelling voor een paar uur." |
| Vakantie | blauw | "Niemand thuis, thermostaat lager. Weinig warmtevraag is dan normaal." |
| Bijzonder gebruik | amber | "Iets ongewoons, zoals een feest, open ramen bij verbouwing of een kapotte sensor." |

- Uitlegblok: `TintCard` 14px radius in de tint van de soort, 13px tekst in de donkere kleur.
- Van/tot: `Field` datum + tijd. Standaard bij nieuw: van = vandaag 00:00, tot = vandaag 23:59 (of het geselecteerde tijdvak).
- "Loopt nog": checkbox (native, `accent-color:#ea6a2f`). Aan → "Tot"-velden uitgeschakeld, tekst "Tot je de periode beëindigt". De periodekaart toont dan "sinds 4 okt · loopt nog" en een `LinkButton` "Nu beëindigen".
- Omschrijving: `Field` tekst, max 140 tekens, teller 12px `#8a92a3` rechts onder bij > 100.
- "Niet meetellen voor": drie `Toggle`s, standaard **alle aan** voor elke soort (plan §3.4: bijzondere perioden zijn standaard uitgesloten van normaalgedrag, vergelijkingen en cv-conclusies). Uitleg onder de groep (12px `#5b6475`): "De gegevens blijven altijd zichtbaar in grafieken en tabellen."

**Teksten.**
- Titel nieuw: "Periode markeren"; bewerken: "Periode bewerken". Subregel: "Telt standaard niet mee voor normaal gedrag en vergelijkingen".
- Primaire knop: "Markeren" / "Opslaan". Verwijderen (alleen bij bewerken): `DangerButton` "Verwijderen" → bevestiging in de dialoog zelf (knop wordt "Zeker weten? Verwijderen" voor 5 s).
- Na opslaan: dialoog sluit, nieuwe kaart krijgt 2 s `box-shadow:0 0 0 2px #ea6a2f`; onder de kaartenlijst 12px: "Analyses over deze periode worden opnieuw berekend." (header-pil "herberekenen").

**Validatie.**
- Soort verplicht ("Kies een soort periode").
- Van verplicht; tot verplicht tenzij "Loopt nog".
- Tot > van ("De eindtijd moet na de begintijd liggen").
- Van mag niet vóór de oudste bewaarde gegevens liggen: waarschuwing (geen fout) "Voor {datum} zijn geen gegevens meer; dat deel heeft geen effect."
- Toekomst is toegestaan (geplande vakantie); waarschuwing als van > nu + 365 d.
- Overlap met een andere periode: **toegestaan**, amber waarschuwing "Overlapt met '{soort} {datum}'. Dat mag; beide gelden dan."
- Maximale duur: geen; > 60 dagen geeft waarschuwing "Lange periode: in deze tijd worden geen normaalgedrag en vergelijkingen opgebouwd."

**Focus/toetsenbord.** Focus bij openen op de eerste soort-chip (nieuw) of het omschrijvingsveld (bewerken). Pijltjes links/rechts binnen de radiogroep. Enter in een tekstveld = primaire knop. `Esc` volgens §0.3.

### 3b. Entiteitkiezer

**Doel.** Snel de juiste Home Assistant-entiteit vinden tussen honderden, zonder entity_id's uit het hoofd te kennen.
**Requirements:** FR-01 (koppelen met eenheid, locatie, bron, betekenis), FR-04.
**API:** `GET /api/ha/entities` (id, friendly_name, unit, device_class, state, last_changed/last_reported, area, device_name) — één keer per dialoog-open laden, filteren in de client; `GET /api/signals` voor "al gekoppeld".
**Bereikt via:** Signalen › Signaal instellen › veld "Home Assistant-entiteit" (in v3 alleen-lezen met placeholder "Kies een entiteit…": klik, Enter of spatie opent de kiezer), en onboarding stap 2.

Wireframe (desktop, 640 px breed):

```
┌──────────────────────────────────────────────────────────────┐
│ (🔌) Entiteit kiezen                                     [×]  │
│      voor Ketelaanvoer · verwacht °C                          │
│ [🔍 Zoek op naam of entity_id, bijv. aanvoer of remeha     ]  │
│ [ Passend (°C) | Alle entiteiten ]              38 gevonden   │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ ★ Remeha aanvoertemperatuur               54,2 °C  [4 s] │ │ ← actief
│ │   sensor.remeha_flow_temp · Ketel · Technische ruimte    │ │
│ │   Remeha retourtemperatuur                41,8 °C  [4 s] │ │
│ │   sensor.remeha_return_temp  (Al gekoppeld: Ketelretour) │ │
│ │   Woonkamer temperatuur                   20,4 °C [2 min]│ │
│ │   sensor.etwist_woonkamer                                │ │
│ │   Zolder temp                    Niet beschikbaar        │ │
│ └──────────────────────────────────────────────────────────┘ │
│ ↑↓ kiezen · Enter selecteren · Esc sluiten                    │
│                                         [Annuleren] [Kiezen]  │
└──────────────────────────────────────────────────────────────┘
```

Smal: sheet op volle hoogte (92vh), lijst vult de ruimte, hint-regel verborgen.

**Componenten en tokens.**
- Badge teal `plug` (zelfde kleur als Signalen).
- Zoekveld: `Field` met `search`-icoon links (16px `#8a92a3`, `padding-left:36px`), wisknop `x` rechts bij invoer. `role="combobox"`, `aria-expanded="true"`, `aria-controls` = lijst, `aria-activedescendant` = actieve optie.
- Filter: `Segmented` (Meldingen-variant) "Passend ({eenheid})" | "Alle entiteiten". Passend = zelfde eenheid of compatibele `device_class` (temperatuur → °C/°F; vlam → `binary_sensor`; modus → `sensor` zonder eenheid of met enum; gas → m³ met `state_class: total_increasing`). Rechts 12px `#8a92a3` "{n} gevonden".
- Lijst: `role="listbox"`, max-hoogte 360 px met scroll, rand `#e7e9ee` radius 14px. Optie (`role="option"`): `padding:10px 12px`, regel 1 friendly_name 14px/700 + rechts actuele waarde 13px tabular + leeftijds-`Pill` klein (groen < max. leeftijd, amber erboven, slate "Niet beschikbaar" bij `unavailable`/`unknown`); regel 2 entity_id 12px `#5b6475` (`word-break:break-all`) · apparaat · ruimte. Actieve optie (toetsenbord/hover): `#f8f9fb`; gekozen: `#fff7f2` + `box-shadow:0 0 0 2px #ea6a2f inset`. Zoektreffer vetgedrukt in naam en id (`<mark>` zonder achtergrond, 800).
- Voorstel (hoogste score): `Pill` klein violet "Voorstel" of ★ voor de naam.
- "Al gekoppeld aan {signaal}": `Pill` klein amber. Kiezen mag (een entiteit kan bij twee signalen horen, bijv. verkeerd gekoppeld), maar toont na kiezen in het paneel: "Deze entiteit is ook gekoppeld aan {signaal}. Klopt dat?".

**Zoeken en sorteren.**
- Hoofdletter- en accentongevoelig; meerdere woorden = alle woorden moeten voorkomen (in id, naam, apparaat of ruimte). Debounce 120 ms.
- Volgorde: voorstellen → passend op eenheid/device_class → alfabetisch op naam. Max. 200 opties renderen; daarboven onderaan 12px "Toon je zoekopdracht specifieker om meer te zien (nog {n})".

**Teksten en staten.**
- Laden: 6 skeletonrijen.
- Geen resultaten (passend): "Geen entiteiten met eenheid {eenheid} gevonden." + `LinkButton` "Toon alle entiteiten".
- Geen resultaten (zoekterm): "Niets gevonden voor '{term}'. Controleer of de entiteit in Home Assistant bestaat en niet is uitgeschakeld."
- Fout: `ErrorCallout` "Kon de entiteiten niet ophalen uit Home Assistant." + "Opnieuw proberen".
- Eenheid past niet na kiezen (in het paneel, onder het veld): omrekenbaar (°F → °C): info teal "Wordt omgerekend van °F naar °C."; niet omrekenbaar (bv. % voor een temperatuur): fout "Deze entiteit meet in %, maar dit signaal verwacht °C." en "Koppeling opslaan" uitgeschakeld.
- In het Signalen-paneel naast het veld: `LinkButton` "Ontkoppelen" (bevestiging: "Ontkoppel {signaal}? Analyses die dit signaal nodig hebben worden beperkt of niet beschikbaar. Bestaande gegevens blijven bewaard.").
- Na opslaan van een **gewijzigde** koppeling, 12px onder de knop: "De nieuwe koppeling geldt vanaf nu. Wil je ook de historie van deze entiteit gebruiken? Historie importeren ›" (opent §4 met dit signaal voorgeselecteerd).

**Toetsenbord.** Focus bij openen in het zoekveld. ↓/↑ verplaatst de actieve optie (lijst scrollt mee), Home/End eerste/laatste, PageUp/PageDown 10 opties. Enter = kies actieve optie en sluit (waarde staat in het veld van het paneel; opslaan gebeurt met "Koppeling opslaan", in onboarding direct). `Esc`: eerst zoekveld leegmaken, tweede `Esc` sluit. Tab gaat naar segmented → knoppen (lijst zelf is geen tabstop; bediening via combobox).

---

## 4. Historische import

**Doel.** Historie uit de recorder van Home Assistant importeren en laten zien hoe ver het is en wat het opleverde. Import en live verwerking gebruiken dezelfde analyse.
**Requirements:** FR-06, FR-08 (ontdubbelen), FR-11 (gaten blijven onbekend).
**API:** `POST /api/import {from, to, roles?}` → `{id}`; `GET /api/import/{id}` (poll elke 2 s zolang actief, daarna stoppen); lijst/laatste via `GET /api/import` (aanname, zie [#19](https://github.com/roordaj/cv-idee/issues/19)). Benodigde velden: `status ∈ {wachtend, ophalen, analyseren, klaar, onderbroken, mislukt, geannuleerd}`, `from`, `to`, `blocks_done`, `blocks_total`, `current_block_day`, `observations_imported`, `duplicates_skipped`, `signals[{role, observations, first_ts}]`, `earliest_available_ts`, `cycles_found`, `coverage_pct`, `errors[]`, `started_at`, `finished_at`.
**Bereikt via:** Gegevenskwaliteit — nieuwe `Card` "Historie importeren" direct ná "Bijzondere perioden" (onderaan de pagina); onboarding stap 3; link na wijzigen van een koppeling (§3b); header-pil tijdens import.

### 4.1 Wireframes

Kaart, staat *gereed om te starten* (desktop):

```
┌ Card ─────────────────────────────────────────────────────────────────────┐
│ Historie importeren                     Laatste import: 4 okt 09:12 · ✓    │
│ Haal eerdere metingen op uit Home Assistant. Dezelfde analyse als live.    │
│ Periode  [ Laatste 7 dagen | Laatste 30 dagen | Alles beschikbaar | Zelf ] │
│          (Zelf: [van ▾] [tot ▾])                                           │
│ Signalen  Alle 9 gekoppelde signalen ▾                                     │
│ ⓘ Home Assistant bewaart historie vanaf 24 sep (recorder). Ouder bestaat   │
│   niet meer en wordt overgeslagen.                                         │
│                                                         [⇩ Importeren]    │
└────────────────────────────────────────────────────────────────────────────┘
```

Staat *bezig*:

```
┌ Card ─────────────────────────────────────────────────────────────────────┐
│ Historie importeren                                 (Bezig · ophalen)     │
│ 24 sep → 4 okt · dag 6 van 10 (29 sep)                                     │
│ [■■■■■■■■■■■■■■■■■■■■■■■■□□□□□□□□□□□□□□□]  58 %                           │
│ ① Ophalen ✓──── ② Analyseren ○──── ③ Klaar ○                               │
│ 84.212 metingen · 1.304 dubbel overgeslagen · nog ca. 2 min                │
│ Je kunt de app gewoon gebruiken; de import loopt op de achtergrond door.   │
│                                                          [Stoppen]        │
└────────────────────────────────────────────────────────────────────────────┘
```

Staat *klaar*:

```
┌ Card ─────────────────────────────────────────────────────────────────────┐
│ Historie importeren                                 (Klaar · 4 okt 09:16) │
│ [Periode 24 sep – 4 okt] [Metingen 141.880] [Cycli 1.212] [Dekking 97,4 %]│  ← KpiTiles (Cycli-maat)
│ ⚠ 2 aandachtspunten                                                       │
│   · Slaapkamer: historie begint pas op 2 okt (sensor later toegevoegd).    │
│   · 27 sep 03:10–05:40: geen gegevens van 9 CAN-signalen (telt als         │
│     onbekend).                                                             │
│ [Bekijk in Cycli ›] [Dekking per signaal ›]           [Nog een import]    │
└────────────────────────────────────────────────────────────────────────────┘
```

Smal: periode-`Segmented` wordt een `select`; KPI-tegels 2 per rij (grid `minmax(140px,1fr)`); knoppen onder elkaar volle breedte.

### 4.2 Componenten

- `Card` met kop `h3` "Historie importeren" en rechts status-`Pill`: Bezig (blauw), Analyseren (violet), Klaar (groen), Onderbroken (amber), Mislukt (rose), Geannuleerd (slate).
- Periode: `Segmented` (Meldingen-variant) "Laatste 7 dagen | Laatste 30 dagen | Alles beschikbaar | Zelf kiezen"; "Zelf kiezen" toont twee datumvelden.
- Signalen: standaard alle gekoppelde; `ButtonSecondary` klein met chevron opent een lijst met checkboxes per signaal (alleen gekoppelde).
- Voortgangsbalk: hoogte 10px, radius 5px, achtergrond `#eef0f3`, vulling `#3b7ddd` (ophalen) of `#7c5cd6` (analyseren); `role="progressbar"` met `aria-valuenow`, `aria-valuetext="dag 6 van 10, 58 procent"`. Percentage rechts 13px/700 tabular.
- Fasen: drie stappen-rondjes 20px (zelfde stijl als onboarding, kleiner) met labels 12px.
- Resultaat: `KpiTile` (Cycli-maat): Periode (`calendar`, blauw), Metingen (`database`, teal), Cycli gevonden (`repeat`, oranje), Dekking (`shield`, amber; waarde groen-donker `#1d6b3c` als ≥ minimale dekking, anders `#8a6206`).
- Aandachtspunten: amber `Callout` met lijst.

### 4.3 Teksten

- Intro: "Haal eerdere metingen op uit Home Assistant. De import gebruikt precies dezelfde analyse als live gegevens, dus dezelfde historie levert dezelfde cycli op."
- Recorder-info (neutraal `Callout`): "Home Assistant bewaart historie vanaf {earliest}. Oudere gegevens bestaan daar niet meer en worden overgeslagen." Als gekozen van < earliest: zelfde tekst in amber.
- Import al eerder gedaan over (een deel van) de periode: 12px `#5b6475` "Dit bereik is al (deels) geïmporteerd. Opnieuw importeren is veilig: dubbele metingen worden overgeslagen."
- Bezig: "{van} → {tot} · dag {i} van {n} ({dag})"; "{n} metingen · {d} dubbel overgeslagen · nog ca. {t}" (schatting pas na 2 blokken tonen; daarvoor "tijd wordt geschat…"); "Je kunt de app gewoon gebruiken; de import loopt op de achtergrond door."
- Analyseren: "Metingen opgehaald. Cycli en bevindingen worden berekend…"
- Stoppen: bevestiging in een `Dialog`: "Import stoppen?" — "Wat al is opgehaald blijft bewaard en wordt geanalyseerd. Je kunt later verdergaan waar de import stopte." — "Doorgaan met importeren" / "Stoppen" (`DangerButton`).
- Onderbroken (app herstart of verbinding weg): amber `Callout` "De import is onderbroken bij {dag} ({reden}). Wat al binnen is, is bewaard." + `ButtonPrimary` "Hervatten".
- Mislukt: `ErrorCallout` "De import is mislukt: {fouttekst}. Er is niets dubbel opgeslagen; je kunt het veilig opnieuw proberen." + "Opnieuw proberen".
- Klaar zonder aandachtspunten: teal `Callout` "Alles binnen. Geen gaten gevonden in de geïmporteerde periode."
- Geen gegevens in bereik: neutraal `Callout` "Home Assistant had voor deze periode geen gegevens van de gekoppelde signalen."

### 4.4 Regels

- Maximaal één import tegelijk. Tijdens import is "Importeren" vervangen door de voortgang; elders (onboarding, Signalen-link) verwijst de knop naar deze kaart.
- Validatie zelf kiezen: van < tot; tot ≤ nu; bereik > 365 dagen geeft waarschuwing "Grote import; dit kan lang duren."
- Na "klaar": `Overview`, `Cycles`, `Quality` queries invalideren (TanStack Query), zodat schermen de nieuwe data tonen.
- Focus: bij start verschuift focus naar de statusregel (`aria-live="polite"`, alleen fasewissels en klaar/mislukt aankondigen, niet elk procent).

---

## 5. Laadstaten, lege staten en foutstaten

**Doel.** Elk scherm toont eerlijk of het laadt, leeg is, faalt of te weinig gegevens heeft — nooit lege grafieken of nullen die op meetwaarden lijken.
**Requirements:** FR-04, FR-11, FR-28, FR-36, scenario 5 en 10.

### 5a. Algemene regels

1. **Laden** = `Skeleton` in de echte layout. Pas na 300 ms tonen (voorkomt flitsen). Na 15 s zonder antwoord: foutstaat met "Het laden duurt langer dan verwacht."
2. **Fout** per kaart, niet per pagina: één mislukte query vervangt alleen die kaart door een `ErrorCallout`; de rest van de pagina blijft bruikbaar. Standaardtekst: "Kon {onderwerp} niet laden. De analyse zelf draait gewoon door; dit gaat alleen over het tonen." Retry: TanStack Query 2× automatisch, daarna de knop.
3. **App niet bereikbaar** (API weg, bv. add-on gestopt): hele main-inhoud wordt een `EmptyState` met rose badge `wifioff`: "CV-analyse is niet bereikbaar" — "De achtergronddienst reageert niet. Controleer of de add-on draait. Deze pagina probeert het elke 10 seconden opnieuw." Header-pil: "Geen verbinding met CV-analyse" (rose).
4. **HA-verbinding weg** (app draait wel): header-pil rose (§0.3); op Overzicht een rose `Callout` bovenaan (§5c). Overige schermen tonen hun historische data normaal; datagaten verschijnen als arcering.
5. **Nooit** een `0`, `0 %` of groen vinkje tonen voor iets dat onbekend is: gebruik "—" met een sub-regel die zegt waarom ("niet gekoppeld", "geen recente meting", "te weinig gegevens").
6. **Leeg** heeft altijd een vervolgstap (knop of link), behalve als leeg goed nieuws is (geen bevindingen).
7. **Stubdata**: header-pil "Voorbeeldgegevens" zodat niemand voorbeeldwaarden voor echte aanziet.

### 5b. Per scherm

| Scherm | Laden | Leeg | Fout | Onvoldoende / beperkt |
|---|---|---|---|---|
| **Overzicht** | skelet: statuskaart, actiekaart, 6 KPI-tegels, 2 kaarten, analysetegels | n.v.t. — zie §5c | per kaart `ErrorCallout`; statuskaart-fout: "Kon de status niet laden." (géén oordeel tonen) | §5c |
| **Bevindingen** | skelet zijlijst (5 rijen) + detail (kop, 4 bewijstegels, 2 kolommen) | `EmptyState` badge groen `checkCircle`: "Geen open bevindingen" — "In de geanalyseerde periode ({n} uur met gegevens, {p} % dekking) vond de app geen patroon dat aandacht vraagt. Dat is geen garantie: analyses die niet beschikbaar zijn, zijn niet beoordeeld." + `LinkButton` "Bekijk beschikbare analyses ›". Bij onvoldoende gegevens **niet** deze staat, maar: badge slate `info` "Nog geen bevindingen mogelijk" — "Er zijn te weinig gegevens om patronen te herkennen ({n} van minimaal {m} uur)." | lijst-fout: `ErrorCallout` op plaats van de lijst; detail-fout (bijv. id bestaat niet meer): `EmptyState` "Deze bevinding bestaat niet meer" — "Mogelijk is ze samengevoegd of opnieuw berekend na een instellingswijziging." + "Naar alle bevindingen" | statuslabels uit v3 ("Zekerheid: Onvoldoende bewijs") volstaan |
| **Cycli** | skelet KPI's + grafiekvlak (hoogte 410/1120 viewBox-verhouding) + 8 tabelrijen | geen cycli in bereik: KPI's "—"; grafiek tekent wel modus/temperatuur; in de Brander-baan 12px `#8a92a3` "Geen branderperiodes in dit tijdvak"; tabel → `EmptyState` klein "Geen cycli tussen {van} en {tot}." + `Segmented` suggestie "Probeer 24 uur of 7 dagen". Vlamstatus niet gekoppeld: hele pagina `EmptyState` badge oranje `activity` "Cycli zijn nog niet beschikbaar" — "Daarvoor is de vlamstatus van de brander nodig." + `ButtonPrimary` "Vlamstatus koppelen" | grafiek- en tabelfout los | resolutie te grof: amber `Callout` boven KPI's "Resolutie vlamstatus is {r}. Cycli korter dan {g} min zijn niet betrouwbaar te herkennen; 'Kort tijdens warmtevraag' wordt niet geteld." en die KPI toont "—" |
| **Wijzigingen** | skelet logboek (3) + detail | geen wijzigingen: logboek-plaats `EmptyState` klein badge slate `sliders` "Nog geen wijzigingen vastgelegd" — "Leg hier vast wat jij of de installateur aan ketel of thermostaat verandert. Dan meet de app het effect voor en na." (formulier "Wijziging vastleggen" blijft gewoon zichtbaar). Geen evaluatie nog: in detail-resultaatblok slate "Evaluatie loopt — resultaat na {datum} ({n} dagen na de wijziging)." | per blok | evaluatie "Onvoldoende bewijs" bestaat al in v3 |
| **Advieshistorie** | skelet lijst (4) + detailkaart | `EmptyState` badge violet `history` "Nog geen adviezen" — "Elk advies dat de app geeft, wordt hier bewaard met de meetperiode, instellingen en regelversie van dat moment." | per blok | — |
| **Signalen** | skelet 12 signaalkaarten + paneel | n.v.t. (catalogus staat altijd); 0 gekoppeld: violet uitleg-`Callout` bovenaan "Nog niets gekoppeld. Begin met de vlamstatus; de eerste start helpt je stap voor stap." + `LinkButton` "Eerste start openen ›" | lijst-fout; entiteitenlijst-fout alleen in de kiezer (§3b) | signaal te oud: v3-`Pill` amber "· te oud" |
| **Installatie** | skelet 3 kaarten + 2 | nooit leeg: onbekende waarden tonen "Onbekend" (v3). Geen circuits: `EmptyState` klein "Nog geen circuits beschreven" — "Beschrijf of radiatoren direct op de ketel zitten of via een mengverdeler. Dat bepaalt welke analyses kloppen." + "Circuit toevoegen" | per kaart | — |
| **Gegevenskwaliteit** | skelet dekkingsbalken (8), gebeurtenissen (5), modusbalk | geen gebeurtenissen: 13px `#5b6475` in de kaart "Geen bijzonderheden gedetecteerd in deze periode." Geen bijzondere perioden: tekst "Nog geen perioden gemarkeerd. Markeer bijvoorbeeld onderhoud of vakantie, zodat die tijd niet meetelt in vergelijkingen." (knop blijft). Geen data ooit: dekkingsbalken volledig gearceerd met "—" | per kaart | dekking < minimale dekking: ondertitel in amber |
| **Meldingen** | skelet 2 kolommen | "Recent verstuurd" leeg: "Nog geen meldingen verstuurd." HA-export niet actief: rose `Callout` "Niet verbonden met de MQTT-broker. Home Assistant toont de CV-analyse-entiteiten als *niet beschikbaar*." | per kaart | — |
| **Analyse-instellingen** | §1.6 | n.v.t. | §1.6 | — |

### 5c. Overzicht: onvoldoende gegevens

**Doel.** FR-36: bij onvoldoende gegevens geen misleidende groene beoordeling.
**API:** `GET /api/overview` levert `beoordeling: { niveau: "onvoldoende_gegevens" | "beperkt" | "voldoende", redenen: [{code, tekst, actie?}], waargenomen_uren, minimale_uren, dekking_pct }` en `setup` (zie §2). Dezelfde `niveau = onvoldoende_gegevens` zet `binary_sensor.cv_analyse_onvoldoende_gegevens` aan; UI en Home Assistant zijn dus altijd consistent.

**Wanneer `onvoldoende_gegevens`** (één reden is genoeg; alle redenen worden getoond):
1. vlamstatus niet gekoppeld — "Vlamstatus is niet gekoppeld." (actie: Koppelen)
2. waargenomen tijd in het venster < *minimale observatieduur* — "Pas {n} van {m} uur met gegevens." (actie: Historie importeren)
3. dekking kernsignalen (vlam, modus, aanvoer) < *minimale dekking voor een beoordeling* — "Dekking {p} % (minimaal {q} %)." (actie: Gegevenskwaliteit)
4. nog nooit een waarneming ontvangen — "Nog geen gegevens ontvangen uit Home Assistant."

**Kleurregel (geldt voor het hele Overzicht):**

| Niveau | Statuskaart-badge | Kwaliteitspil | Groen toegestaan? |
|---|---|---|---|
| `onvoldoende_gegevens` | slate `info` | slate "Onvoldoende gegevens" | **Nee**, nergens op de pagina (ook niet in donut of analysetegels "Beschikbaar") |
| `beperkt` | volgens bedrijfsmodus (v3: slate `pause` bij standby) | amber "Datakwaliteit: beperkt" (v3) | Alleen analysetegels die echt beschikbaar zijn; geen "alles in orde" |
| `voldoende`, open bevindingen | volgens modus | geen kwaliteitspil, wel rose "{n} vragen om actie" (v3) | tegels |
| `voldoende`, geen open bevindingen | groen `checkCircle` | groen "Gegevens voldoende · {p} %" | **Ja**: titel "Geen bijzonderheden in de afgelopen {venster}" |

Wireframe `onvoldoende_gegevens` (desktop):

```
┌ Callout neutraal (alleen als setup niet af) ──────────────────────────────────┐
│ ⓘ Inrichting nog niet af — 1 van 3 stappen gedaan.     [Verder met inrichten] │
└───────────────────────────────────────────────────────────────────────────────┘
┌ Card (flex 2) ─────────────────────────────────┐ ┌ TintCard oranje (flex 1) ─┐
│ (ⓘ) Status                                     │ │ (💡) Eerste stap          │
│     Nog geen beoordeling mogelijk              │ │ Importeer de historie     │
│     Er zijn te weinig gegevens om iets te       │ │ Dan heb je direct een     │
│     zeggen over hoe je installatie draait. De  │ │ eerste beoordeling in     │
│     app geeft daarom (nog) geen oordeel.       │ │ plaats van over 4 uur.    │
│     (Onvoldoende gegevens) (Modus: CV · live)  │ │ [Historie importeren →]   │
│ ┌ waarom ───────────────────────────────────┐  │ └───────────────────────────┘
│ │ · Pas 2 van 6 uur met gegevens.  Importeren›│ │
│ │ · Dekking 61 % (minimaal 80 %).  Details › │  │
│ └───────────────────────────────────────────┘  │
│ ┌ mini-tijdlijn (alleen als er data is) ─────┐ │
└────────────────────────────────────────────────┘
[Aanvoer 54,2 °C][Retour —        ][Modulatie —     ][Woonkamer 20,4 °C]...
 gemeten · 4 s    niet gekoppeld    geen recente m.   doel 20,5 °C
┌ Bevindingen ──────────────────────┐ ┌ Datakwaliteit ──────────────────┐
│ (EmptyState) Nog geen bevindingen │ │ (donut slate, "61%")            │
│ mogelijk …                        │ │ Onvoldoende. 61 % dekking …     │
└───────────────────────────────────┘ └─────────────────────────────────┘
┌ Beschikbare analyses — tegels zoals v3, "Beschikbaar" hier in slate i.p.v. groen ┐
```

Smal: kaarten stapelen (v3-flex-wrap doet dit al); "waarom"-lijst links/rechts → onder elkaar.

**Details.**
- Statuskaart: label "Status" (i.p.v. "Status ketel"), titel 22px/800 "Nog geen beoordeling mogelijk", tekst zoals in wireframe. Pillen: slate "Onvoldoende gegevens"; slate "Modus: {modus} · live" als de actuele modus bekend is (actuele status mag wel getoond worden; het is een *waarneming*, geen *oordeel*).
- "Waarom"-blok: binnenvlak `#f8f9fb` radius 14px (zoals de mini-tijdlijn), per reden een regel 13px met icoon (plug/clock/shield) en rechts de `LinkButton`-actie.
- Actiekaart: blijft oranje (het is een actie, geen oordeel) maar heet **"Eerste stap"** i.p.v. "Aanbevolen actie" en bevat een inrichtingsactie, nooit een optimalisatieadvies. Prioriteit: 1 koppel vlamstatus → 2 importeer historie → 3 wacht ("De analyse loopt. Nog ca. {n} uur tot de eerste beoordeling." zonder knop).
- KPI-tegels: waarde "—" (22px/800 `#8a92a3`) met reden als sub-regel; een tegel van een niet-gekoppeld signaal krijgt sub "niet gekoppeld · Koppelen" (link).
- Donut: ring in slate (`#eef0f3` / `#5b6475`), tekst "Onvoldoende." in `#3d4452`.
- Analysetegels: status "Beschikbaar" toont in deze staat slate-tint i.p.v. groen met tekst "Beschikbaar · wacht op gegevens".
- HA-verbinding weg (los van niveau): rose `Callout` bovenaan "**Geen verbinding met Home Assistant sinds {tijd}.** Er komen geen nieuwe gegevens binnen. Deze tijd telt als onbekend, niet als 'brander uit'. Conclusies over deze periode worden niet getrokken." De statuskaart toont dan modus "onbekend".

---

## 6. Wijzigingsmarkers in grafieken

**Doel.** Vastgelegde wijzigingen (W-xx) op het juiste tijdstip in grafieken tonen, zodat gedrag voor en na een wijziging direct zichtbaar is.
**Requirements:** FR-29 ("grafieken tonen de wijziging op het juiste tijdstip"), FR-37, FR-10 (verwant: bijzondere perioden).
**API:** `GET /api/timeline?from&to` levert naast reeksen ook `changes: [{id, ts, parameter, oud, nieuw, door, verdict}]` (alle wijzigingen in het bereik) en `last_change_before: {id, ts, parameter}`; plus `periods: [{id, soort, from, to}]`. (Toevoegen aan contract [#11](https://github.com/roordaj/cv-idee/issues/11); anders combineert de frontend met `GET /api/changes`.)
**Component:** `TimelineChart` en `MiniTimeline` ([#14](https://github.com/roordaj/cv-idee/issues/14)).

### 6.1 TimelineChart (Cycli)

Bovenaan de grafiek komt een extra baan **"Wijzigingen"** (label links zoals de andere banen, 12px/600 `#3d4452`), hoogte 22 px, alleen als er in het bereik ≥ 1 wijziging is. De overige banen schuiven 26 px omlaag (viewBox-hoogte 410 → 436).

```
             06:00        07:00        08:00        09:00        10:00
Wijzigingen                     [W-08]
                                  │
Modus       ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
Warmtevraag ━━━━━━━━━━━━━━━━━━━━━│━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Brander     ▌ ▌ ▌  ▌ ▌ ▌ ▌  ▌  ▌ │  ▌▌  ▌   ▌▌    ▌  ▌
Temperatuur   ╱╲╱╲╱╲╱╲╱╲╱╲╱╲╱╲╱ │╱‾‾╲__╱‾‾╲__
Modulatie   ________________ ___│________________
```

- **Vlag**: afgeronde rechthoek `rx:9`, hoogte 18, breedte tekst + 16, `fill:#1d2433`, tekst wit 11px/700 "W-08", gecentreerd op het tijdstip.
- **Lijn**: van onder de vlag tot onderkant Modulatie-baan, `stroke:#3d4452`, `stroke-width:1.5`, `opacity:.6`, **doorgetrokken** (niet gestippeld — gestippeld grijs is al "gewenste aanvoer").
- Ligt **boven** de modusvlakken en cycli, **onder** de temperatuurlijnen en de cyclusselectie.
- **Hover/focus**: lijn `opacity:1`, `stroke-width:2`; tooltip-kaart (wit, rand `#e7e9ee`, radius 12px, `box-shadow:0 8px 24px rgba(16,24,40,.12)`, padding 10px 12px, max-breedte 280px), boven de vlag, binnen de grafiek gehouden:
  - regel 1: 12px `#8a92a3` "W-08 · 4 okt 07:40 · door gebruiker"
  - regel 2: 14px/700 "Maximale CV-aanvoer: 60 °C → 70 °C"
  - regel 3: `Pill` klein met oordeel in v3-kleuren (Afweging · terugdraaien = rose, Niet toe te schrijven = amber, Onvoldoende bewijs / Evaluatie loopt = slate, Verbeterd = groen)
  - regel 4: 12px `#c2531f` "Klik om de wijziging te openen"
- **Klik / Enter / spatie**: navigeer naar Wijzigingen met die wijziging geselecteerd (`/wijzigingen/W-08`).
- **Trefgebied**: transparante rect 16 px breed over de volle hoogte + de vlag.
- **Overlap**: vlaggen waarvan de middens < 40 px (in schermpixels na schalen) uit elkaar liggen worden één vlag "2 wijzigingen"; lijnen blijven apart. Tooltip toont beide (gescheiden door een lijn); klik opent een klein menu (zelfde kaartstijl) met per wijziging een `ListButton`.
- **Wijziging vóór het bereik**: geen lijn; rechts in de legenda-regel boven de grafiek 12px `#5b6475`: "Laatste wijziging vóór dit tijdvak: W-07 · 21 sep (Maximale CV-aanvoer)" als link.
- **Legenda**: nieuw item "Wijziging" met icoon: lijn 2×12 `#3d4452` + mini-vlag 10×6 `#1d2433`.
- **Toegankelijkheid**: elke vlag `role="button"`, `tabindex="0"`, `aria-label="Wijziging W-08, 4 oktober 07:40: maximale CV-aanvoer van 60 naar 70 graden. Open wijziging."`. Tab-volgorde chronologisch, vóór de cyclusbalken. De SVG-`<title>` noemt het aantal wijzigingen in beeld.
- **Smal** (grafiek < 600 px breed): vlagtekst vervalt tot een cirkel r=6 `#1d2433` met witte "W" (8px); tooltip opent op tik (niet op hover), tweede tik navigeert.

### 6.2 MiniTimeline (Overzicht)

Geen extra baan. Per wijziging: lijn 1.5 px `#3d4452` opacity .6 over de volle hoogte (82) en bovenaan een driehoekje 6 px `#1d2433` (wijst omlaag). Geen tekst, wel `<title>` "Wijziging W-08 om 07:40". Niet klikbaar (de hele mini-tijdlijn linkt al naar Cycli).

### 6.3 Voor/na-weergave (Wijzigingen)

Geen grafiekmarker nodig; de v3-weergave "Voor · 14–20 sep / Na · 22–28 sep" blijft. Wel: knop `ButtonSecondary` "Toon in tijdlijn" (icoon `activity`, zoals bij Bevindingen) opent Cycli met bereik 7 dagen rond het tijdstip van de wijziging, marker in beeld.

### 6.4 Bijzondere perioden in grafieken (verwant, FR-10)

Een gemarkeerde periode wordt in `TimelineChart` als **band achter alle banen** getekend: tint van de soort (§3a) met `opacity:.5`, radius 8, en bovenaan in de Wijzigingen-baan (die dan ook verschijnt) een label 11px/700 in de donkere kleur: "Vakantie · telt niet mee". Datagat-arcering ligt erboven. In `MiniTimeline`: alleen de band, zonder label.

### 6.5 Tijdvak selecteren (voor "Periode markeren")

In `TimelineChart` (alleen met muis/pen of toetsenbord, niet nodig op smal): slepen in de Modus-baan selecteert een tijdvak (violet `rgba(124,92,214,.08)` met rand `#7c5cd6`, zoals cyclusselectie). Boven de grafiek verschijnt een balk: "{van}–{tot} geselecteerd" + `ButtonSecondary` "Periode markeren" + `LinkButton` "Wissen". Toetsenbord-alternatief: de knop "Periode markeren" in Gegevenskwaliteit. (Optioneel voor MVP; zie §7.)

---

## 7. Openstaande ontwerpvragen

Beslissing van de eigenaar nodig. Tot die tijd geldt het **voorstel**; UI-agents bouwen volgens het voorstel.

1. **Herstelcriterium op Meldingen.** v3 heeft een vrij tekstveld. Voorstel: gestructureerde velden in Analyse-instellingen › Herstel, op Meldingen alleen een samenvatting met link (§1.1). Akkoord met deze afwijking van v3?
2. **Gasprijs: waar bewerken?** v3 toont hem bij Installatie › Instellingen en specificaties. Voorstel: bewerken in Analyse-instellingen › Kosten, de Installatie-rij linkt erheen. Of liever bewerkbaar in Installatie laten?
3. **Max. sensorleeftijd: één bron.** Het plan noemt hem in `signal_mappings` én in `settings` (#22). Voorstel: één waarde (`settings`, sleutel per rol), bewerkbaar in het Signalen-paneel én in de tabel van Analyse-instellingen. Bevestigen voor het datamodel (#7) en #22.
4. **Standaardwaarden zijn voorstellen zonder norm**: kortecyclusgrens 3 min (v3), warmtevraag na stop 60 s, min. 4 korte cycli, minimale observatie 6 u, herhaling 2 van 7 dagen, comfortgrens 0,5 °C en 4 u/week (v3), vergelijkbaar weer 2 °C / beperkt 4 °C (afgeleid uit v3-voorbeelden), dekking 80 % (beoordeling) en 90 % (effect/herstel), gewenste resolutie 10 s. Graag bevestigen; resolutie en "verwacht regelmatige updates" definitief na de CAN-inventarisatie (#5) en ADR-003 (#9).
5. **Omvang van herberekening na een instellingswijziging.** Voorstel: alle bewaarde gegevens (tot 180 dagen) op de achtergrond, nieuwste eerst. Alternatief: alleen de laatste 30 dagen (sneller, maar oudere bevindingen blijven op oude grenzen).
6. **Lopende bevindingen na een drempelwijziging.** Voorstel: een bevinding die onder de nieuwe grens niet meer bestaat, sluit met reden "Instelling gewijzigd" (niet "Hersteld"), en blijft vindbaar in de advieshistorie. Akkoord?
7. **Installatieprofiel in de onboarding?** Voorstel: niet verplicht (alleen in de checklist van "Klaar"), omdat cycli-analyse zonder profiel werkt. Maar zonder profiel weet de app niet dat er een mengverdeler is (scenario 6). Verplichte stap "Circuits" toevoegen?
8. **Bijzondere periode bewerken.** Plan §3.9 kent alleen `GET|POST|DELETE /api/periods`. Voorstel: `PUT /api/periods/{id}` toevoegen (#11, #21), anders wordt bewerken verwijderen + opnieuw aanmaken (verliest id/historie).
9. **Per-advies terugdraaicriterium.** Mag een individueel advies een eigen comfortgrens hebben die afwijkt van de algemene "Toegestaan comfortverlies"? Voorstel: ja, bij het advies getoond; de algemene waarde is alleen de standaard.
10. **Instellingen wijzigen zonder login (standalone).** Iedereen met toegang tot de UI kan drempels wijzigen. In de add-on regelt HA de toegang; standalone alleen met optionele `CVIDEE_API_TOKEN`. Acceptabel, of alleen-lezen-modus voor instellingen zonder token?
11. **Tijdvak selecteren in de tijdlijn (§6.5)** is handig maar niet vereist. Meenemen in MVP (#14/#44) of later?
12. **Navigatie op telefoon.** v3 houdt onder 640 px de rail van 72 px aan. Met een extra nav-item (Analyse-instellingen) worden het 10 iconen. Voldoende, of een onderbalk/hamburger voor < 480 px?

## 8. Verbruiksscherm (FR-31)

Het scherm **Verbruik** staat in de hoofdnavigatie en gebruikt de bestaande v3-kaarten, kleuren, typografie en responsieve kolommen. Het ontwerp is uitgewerkt in [`CV-analyse-v3.dc.html`](CV-analyse-v3.dc.html). De voorbeeldstaat bevat geen synthetische meterstanden of bedragen.

### 8.1 Bovenaan en ruwe meterdata

- Titel **Gasverbruik**, met subtitel dat het ruwe meterstanden en een beschrijvende vergelijking betreft, zonder weerscorrectie.
- De hoofdkaart toont beschikbaarheid, bron, expliciete meter-scope en cumulatieve meterstand met eenheid. Ontbrekende waarden zijn `—`; onbekende scope staat letterlijk als **Onbekend**.
- De gebruiker kan doorklikken naar het installatieprofiel om de cumulatieve gasmeter te koppelen en de scope vast te leggen. Een entiteitsnaam leidt niet automatisch de scope af.
- Toon alleen gasvolume in m³ wanneer bron en eenheid dit ondersteunen. Geen omzetting naar kWh, warmteafgifte of rendement zonder gevalideerde conversie en systeemgrens.

### 8.2 Periodevergelijking en context

- De gebruiker kiest zelf een referentieperiode en observatieperiode; er wordt geen “beste match” automatisch geselecteerd.
- Vergelijking is alleen beschikbaar bij dezelfde meter, eenheid en bevestigde scope, met gelijke periodeduur en bruikbare tellerdekking. Toon ruwe periodetotalen en het absolute verschil in m³; presenteer dit niet als besparing.
- Een toekomstige weersanalyse blijft een afzonderlijke, optionele uitkomst met eigen beschikbaarheid en methode-uitleg. Dit scherm claimt geen weerscorrectie.
- Toon per periode de beschikbare context: buitentemperatuur, binnen-setpoint en gebruik, CV-bedrijfsduur, tapwateractiviteit en bijzondere perioden. Onbekend blijft **Onbekend** en wordt niet ingevuld als gelijk of nul.

### 8.3 Datagaten, resets en afgeleide uitkomsten

- Tellerreset, teruglopende stand, verouderde waarde en datagat krijgen afzonderlijke waarschuwing/status. Een lijn wordt onderbroken op een reset of onbekend interval; geen gladgestreken lijn en geen nulverbruik voor ontbrekende tijd.
- Beschikbaarheid wordt apart getoond voor ruwe gasmeting, vergelijking, rendement en kosten.
- Rendement blijft niet beschikbaar zonder gevalideerde geleverde warmte en passende systeemgrens. Kosten blijven niet beschikbaar zonder ingestelde toepasselijke gasprijs. Geen fictieve euro’s of besparingsbadge.
- Benoem dat woninggas mogelijk koken en tapwater omvat en dat ketelgas tapwater kan omvatten. Wijs het totaal niet toe aan ruimteverwarming.

Alle bediening gebruikt gelabelde native formuliervelden, zichtbare focus en semantische tabelkoppen; op smalle schermen mogen kaarten onder elkaar vallen en tabellen horizontaal scrollen.
