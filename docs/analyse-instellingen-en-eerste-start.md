# Analyse-instellingen en eerste start

`/instellingen/analyse` toont de actieve grenswaarden uit het JSON-schema van
`GET /api/settings`. Labels, uitleg, eenheden, standaardwaarden en bereiken worden
uit het schema gelezen. Een leeg gasprijsveld blijft onbekend; het is geen nulprijs.
Per-signaalveroudering blijft onderdeel van de signaalkoppeling en wordt met het
bestaande signaalpaneel bewerkt.

Getalvelden accepteren een komma of punt. Na controle bij verlaten van het veld of
opslaan volgt een bevestiging met de gewijzigde waarden. Opslaan gebruikt de
gelezen revisie: bij een conflict blijft de invoer staan en kan de gebruiker
herladen. Bestaande adviessnapshots worden niet herschreven. Navigatielinks en het
sluiten van de browser waarschuwen bij niet-opgeslagen wijzigingen.

Een installatie zonder vlamkoppeling en zonder opgeslagen onboarding-voltooiing
opent `/welkom`. Deze flow controleert de echte `/api/ha/status`, laat signalen
koppelen en hergebruikt het importpaneel met standaard de volledige beschikbare
historie. Zonder verbinding of vlamkoppeling kan de volgende stap niet worden
geopend. Ontbrekende bedrijfsmodus geeft een waarschuwing vóór verdergaan.
Importeren kan op de achtergrond doorlopen of worden overgeslagen. Het
voltooimoment wordt met de bestaande instellingen opgeslagen. 'Later afmaken'
stelt de automatische flow voor de huidige browsersessie uit; opnieuw openen kan
via Analyse-instellingen of de inrichtingsbanner op Overzicht.

De verbindingstest vraagt geen toegangstoken in de UI. De backend gebruikt de
bestaande omgevingsconfiguratie. Voltooien van de inrichting is geen uitspraak
over voldoende meetgegevens: de eerste beoordeling blijft afhankelijk van dekking,
resolutie en observatieduur. De overige echte leesroutes volgen in issue #117.
