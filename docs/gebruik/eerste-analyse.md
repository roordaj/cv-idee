# Eerste analyse en historie importeren

Deze handleiding brengt CV-analyse van een verse installatie naar de eerste beoordeling. De app
geeft observaties en adviezen; zij bedient de ketel of thermostaat niet.

## Vooraf

- Home Assistant met Supervisor en add-onondersteuning.
- Voor automatische HA-entiteiten: Mosquitto Broker en de MQTT-integratie zijn geïnstalleerd en
  verbonden. De add-on krijgt de brokergegevens van Supervisor; vul geen brokerwachtwoord in de
  app in.
- Recorder bewaart historie voor de sensoren die je wilt importeren. Alleen historie die nog in
  Recorder staat kan worden opgehaald.
- De bronrepository is momenteel privé. Een gewone repository-URL kan alleen worden toegevoegd
  als Home Assistant die Git-repository kan lezen. Zie [add-on installeren](../../addon/DOCS.md)
  voor de lokale route en de distributiebeperking.

## Installeren en starten

Gebruik *Add-onwinkel → Repositories* zodra de Git-repository voor Home Assistant toegankelijk is.
Zolang die privé is, gebruik je een lokale checkout:

1. Voer in de repo-root `make addon-local` uit.
2. Kopieer `build/addon-local/cv_analyse` naar `/addons/cv_analyse` op je HA-host.
3. Vernieuw de add-onwinkel, installeer *CV-analyse* en start deze.
4. Zet *Toon in zijbalk* aan en open de app.

Opties zijn `log_level` (standaard `info`), `retentie_dagen` (180; toegestaan 7–3650) en
`notify_doel` (standaard leeg). Stel `notify_doel` alleen in als je pushmeldingen wilt en weet
welke `notify.*`-service je gebruikt. Zonder doel blijft het HA-event beschikbaar.

## Home Assistant-signalen koppelen

Doorloop de eerste setup of open *Signaalkoppeling*. Kies per betekenis de juiste Home Assistant-
entiteit; neem niet alleen op de naam aan dat twee entiteiten hetzelfde meten. In de entiteitkiezer
kun je de huidige status, eenheid en HA-naam controleren.

Begin met deze signalen:

| Betekenis in CV-analyse | HA-entiteit |
|---|---|
| Brander/vlam actief | `binary_sensor.*` of andere entiteit met aan/uit-status voor de werkelijke vlamstatus |
| CV-/tapwatermodus | Entiteit waarvan de waarden de bedrijfsmodus van de ketel weergeven |
| Warmtevraag | Entiteit die aangeeft dat er daadwerkelijk warmtevraag is |
| Gewenste ketelaanvoer | Gewenste aanvoertemperatuur van de ketel |
| Ketelaanvoer / ketelretour | Aanvoer- en retourtemperatuur bij de ketel |
| Brander-modulatie | Gemeten of door de ketel gerapporteerde modulatie in procenten |
| Kamer-/buitentemperatuur en kamer-setpoint | De bijbehorende sensor of thermostaatwaarde |

De vlamstatus is minimaal nodig. Modus en warmtevraag zijn sterk aanbevolen; zonder die waarden
wordt korte-cycli-analyse beperkt of niet beschikbaar. Andere signalen maken aanvullende
temperatuur-, comfort-, zone- en hydraulische analyses mogelijk. De pagina *Analyses* laat zien
welke analyse met je koppelingen beschikbaar is.

Controleer ook de eenheid, maximale leeftijd en of de bron regelmatig updates verstuurt. Voor
moduswaarden vraagt de app om de betekenis van de ruwe statussen vast te leggen. Koppel een klep-
commando niet als bewijs dat een klep fysiek open is; een gasmeter telt ook koken en tapwater mee;
ketel-ΔT is niet de ΔT van een vloerverwarmingsgroep. Ontkoppelen bewaart reeds opgehaalde
waarnemingen.

Voer bekende installatiegegevens in bij *Installatie*. Laat onbekende ketelvermogens of andere
specificaties als onbekend staan; de app leidt geen vermogen of kosten af uit alleen
modulatiepercentages.

## Recorder-historie importeren

1. Open *Kwaliteit* en de kaart *Historie importeren*.
2. Kies *Laatste 7 dagen*, *Laatste 30 dagen*, *Alles beschikbaar* of *Zelf kiezen*.
3. Kies *Importeren* en laat de app open of ga verder met de app; de import loopt op de achtergrond.
4. Controleer de voortgang, waarschuwingen, dekking en gevonden cycli op dezelfde pagina.

De app importeert alleen de gekoppelde signalen en gebruikt de gewone analysepipeline. Historie
die ouder is dan de HA-Recorder-bewaartermijn ontbreekt en wordt overgeslagen. Een lange periode
kan lang duren. Een onderbroken import kan worden hervat; reeds opgeslagen waarnemingen worden
niet dubbel geteld. Stoppen bewaart wat al is opgehaald. Een herimport van dezelfde periode is
veilig.

Ga daarna naar *Overzicht*. Bekijk de status van de gegevensdekking en *Analyses* voordat je een
bevinding interpreteert. Onvoldoende of ontbrekende data is geen bewijs dat er geen probleem is.
Een langere import kan de dekking verbeteren, maar maakt meetgaten niet ongedaan.
