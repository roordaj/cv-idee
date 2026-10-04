# Functionele requirements — CV-analyse en optimalisatieadvies

Versie 1.0 · 4 oktober 2026 · Voorstel voor eigen ontwikkeling

## 1. Doel en uitgangspunten

De software analyseert continu verwarmingsgegevens uit Home Assistant en beantwoordt: hoe gedraagt de installatie zich, waar gaat mogelijk energie of comfort verloren, welke wijziging is zinvol en heeft die wijziging geholpen?

Uitgangssituatie: Remeha Calenta Ace met eTwist, ketelgegevens via CAN-bus beschikbaar in Home Assistant, radiatoren beneden en vloerverwarming met mengverdeler boven. Beschikbare CAN-signalen zijn nog niet vastgesteld. Requirements zijn functioneel en schrijven geen programmeertaal, database of uitvoeringsplatform voor.

Versie 1 observeert en adviseert. Wijzigingen aan ketel of regeling worden door de gebruiker uitgevoerd. Automatische aansturing is een eventuele latere uitbreiding.

Prioriteiten: **M** = noodzakelijk voor MVP; **S** = volgende uitbreiding; **L** = later. De acceptatiecriteria hieronder zijn beoogd productgedrag, geen bewezen diagnosemodellen.

## 2. Configuratie en beschikbare gegevens

| ID | Prioriteit | Requirement | Acceptatiecriterium |
|---|---|---|---|
| FR-01 | M | De gebruiker kan Home Assistant-entiteiten koppelen aan betekenisvolle signalen, inclusief eenheid, sensorlocatie, bron en betekenis. | De gebruiker kan onder meer ketelaanvoer, ketelretour en verdeleraanvoer apart koppelen; een ontbrekend signaal blokkeert alleen analyses die het nodig hebben. |
| FR-02 | M | De gebruiker kan de installatie beschrijven: ketelmodel, radiatoren, mengverdeler, ruimtes, zones en welke thermostaat welke warmtevraag bepaalt. | Het installatieprofiel beïnvloedt toepasselijke analyses; een mengverdeler wordt niet als directe aansluiting behandeld. |
| FR-03 | M | De gebruiker kan bekende instellingen en specificaties vastleggen, waaronder maximumaanvoer, maximum-cv-vermogen, minimumvermogen en pompinstellingen. | Onbekende waarden blijven onbekend; modulatiepercentage wordt niet zonder gevalideerde omzetting vertaald naar kW. |
| FR-04 | M | De software toont per analyse of deze beschikbaar, beperkt of niet beschikbaar is en welke gegevens ontbreken. | Zonder gasmeter blijven cycli-analyses werken; een verbruiksanalyse meldt dat gasgegevens ontbreken. |
| FR-05 | S | De gebruiker kan comfortdoelen per ruimte, gebruikstijden, nachtverlaging en bijzondere gebruiksperioden vastleggen. | Afwijkingen tijdens ingestelde afwezigheid worden anders beoordeeld dan tijdens comforturen. |

### Signalen en betekenis

| Signaal | Gebruik | Nodig voor |
|---|---|---|
| Brander/vlam actief | Werkelijke branderstarts en brandduur | Cycli-analyse |
| CV-/tapwatermodus | Scheiden van verwarmings- en tapwatergedrag | Betrouwbare verwarmingsanalyse |
| Warmtevraag of gewenste ketelaanvoer | Onderscheiden tussen einde warmtevraag en stoppen tijdens vraag | Diagnose van korte cycli |
| Werkelijke ketelaanvoer en -retour | Temperatuurverloop en ketel-ΔT | Temperatuuranalyse |
| Brander-modulatie | Belasting tijdens branden | Onderzoek van minimumlastgedrag |
| Werkelijke en gewenste kamertemperatuur | Comfort, opwarming en overshoot | Comfortanalyse |
| Buitentemperatuur | Vergelijken onder soortgelijke omstandigheden | Weerscorrectie |
| Cumulatief gasverbruik | Brandstofverbruik en vergelijking | Verbruiksanalyse |
| Zonevraag / klepstatus | Context van beschikbare warmteafgifte | Zoneanalyse |
| Verdeleraanvoer/-retour, debiet of pompstatus | Onderscheid ketel- en afgiftecircuit | Hydraulische analyse |
| Geleverde warmte via warmtemeter | Werkelijk gemeten thermisch rendement | Rendementsanalyse |

De software toont of een waarde gemeten, door een apparaat gerapporteerd, afgeleid of geschat is. Een klepcommando bewijst niet dat de klep fysiek open is. Gasmeterverbruik kan ook koken en tapwater omvatten. Ketel-ΔT is niet hetzelfde als ΔT per vloerverwarmingslus.

## 3. Gegevenskwaliteit en bedrijfscontext

| ID | Prioriteit | Requirement | Acceptatiecriterium |
|---|---|---|---|
| FR-06 | M | De software verwerkt live gegevens en kan historische gegevens importeren met dezelfde analyselogica. | Analyse van dezelfde historie levert dezelfde cycli op, ongeacht live verwerking of import. |
| FR-07 | M | De software herkent ontbrekende, verouderde, ongeldige en onwaarschijnlijke gegevens en houdt rekening met updatefrequentie en tijdverschillen. | Een oude retourmeting wordt niet met een nieuwe aanvoermeting gecombineerd zonder kwaliteitsmelding. |
| FR-08 | M | De software herkent tellerresets, dubbele waarnemingen en verbindingverlies. | Een reset van de gasmeter veroorzaakt geen negatief verbruik; reconnect veroorzaakt geen kunstmatige branderstart. |
| FR-09 | M | De software classificeert perioden als CV-bedrijf, tapwaterbedrijf, standby, naloop, storing/blokkering of onbekend, voor zover signalen dit toelaten. | Tapwateropwarming wordt niet als te hoge cv-aanvoer gerapporteerd; ontbrekende modusdata resulteert in beperkte zekerheid. |
| FR-10 | M | De gebruiker kan perioden markeren als opstookprotocol, onderhoud, ontluchten, test, vakantie of bijzonder gebruik. | Deze perioden blijven zichtbaar maar worden standaard uitgesloten van normaalgedrag en wijzigingsvergelijkingen. |
| FR-11 | M | Iedere analyse vermeldt gegevensdekking en uitgesloten tijd. | Bij een gat in de vlamstatus wordt brandduur als onvolledig gemarkeerd; de onbekende tijd wordt niet stilzwijgend als uit-tijd geteld. |

De gebruiker kan gewenste maximale sensorleeftijd en meetresolutie instellen. Een analyse van korte cycli wordt alleen beschikbaar als de werkelijk beschikbare resolutie voldoende is om de ingestelde cyclusgrenzen te onderscheiden.

## 4. Monitoring en patroonherkenning

| ID | Prioriteit | Requirement | Acceptatiecriterium |
|---|---|---|---|
| FR-12 | M | De software reconstrueert afzonderlijke branderperiodes met start, einde, duur, modus, temperatuurverloop, modulatie en warmtevraag. | Voor een bekende reeks aan/uit-overgangen worden de bijbehorende branderperiodes correct weergegeven. |
| FR-13 | M | De software berekent starts per daadwerkelijk geobserveerd uur, totale brandtijd, gemiddelde/mediaan brandduur, korte cycli en pauzeduur. | Startfrequentie en de gebruikte tijdsbasis zijn zichtbaar; lange standbytijd maskeert niet het patroon tijdens warmtevraag. |
| FR-14 | M | De software detecteert herhaald kort branden met configureerbare duur, herhaling, minimumobservatie en bedrijfscontext. | Eén korte cyclus geeft geen structurele waarschuwing; tapwatercycli tellen niet mee in een cv-pendelmelding. |
| FR-15 | M | De software analyseert gewenste versus werkelijke aanvoer, overschrijding, opwarmsnelheid en ΔT tijdens stabiel cv-bedrijf. | De opstart- en naloopfase zijn afzonderlijk zichtbaar en worden niet gebruikt als stabiele bedrijfstoestand. |
| FR-16 | M | De software herkent stoppen van de brander terwijl warmtevraag aanhoudt en correleert dit met temperatuur, modulatie en bekende blokkeringen. | De melding maakt onderscheid tussen een waargenomen stop en een vermoedelijke oorzaak. |
| FR-17 | S | De software analyseert opwarmtijd, afwijking van het kamersetpoint, overshoot en comfortverlies per ruimte. | Een ruimte boven setpoint en een andere ruimte onder setpoint blijven afzonderlijke bevindingen. |
| FR-18 | S | De software vergelijkt ketelgedrag met het aantal vragende of geopende zones. | Bij voldoende gegevens toont zij of korte cycli vooral voorkomen bij weinig actieve zones; correlatie wordt niet als oorzaak gepresenteerd. |
| FR-19 | S | De software vergelijkt aanvoer en retour van ketel en mengverdeler als aparte circuits. | Een lage lus-ΔT veroorzaakt geen algemene aanbeveling om de ketelretour te verhogen of iedere lus op één vaste ΔT te zetten. |
| FR-20 | S | De software herkent verandering van normaalgedrag onder vergelijkbare omstandigheden. | Een afwijking vermeldt de referentieperiode en relevante verschillen, bijvoorbeeld weer, setpoint of zonegebruik. |

Er bestaat geen universele norm voor een goed aantal starts, optimale ΔT of juiste aanvoertemperatuur. Grenswaarden zijn configureerbaar, zichtbaar en contextafhankelijk. Detectieregels leggen expliciet vast bij welke bedrijfsmodus en installatieconfiguratie ze geldig zijn.

## 5. Conclusies en aanbevelingen

| ID | Prioriteit | Requirement | Acceptatiecriterium |
|---|---|---|---|
| FR-21 | M | Iedere bevinding scheidt observatie, interpretatie en advies. | De gebruiker ziet meetwaarden en tijdvak apart van mogelijke verklaringen. |
| FR-22 | M | Iedere bevinding bevat ernst, zekerheid en onderbouwing: dekking, aantal relevante cycli, herhaling en ontbrekende signalen. | Een conclusie op basis van weinig gegevens wordt als voorlopig getoond; zekerheid is geen ongedocumenteerd percentage. |
| FR-23 | M | De software kan meerdere mogelijke oorzaken en onderscheidende vervolgmetingen voorstellen. | Bij korte cycli kan zij bijvoorbeeld afgifte, doorstroming of minimumvermogen als hypotheses noemen en aangeven welke meting helpt ze te onderscheiden. |
| FR-24 | M | Adviezen zijn afgestemd op installatie, meetgegevens en bekende instellingen. | Zonder verdelerdata wordt geen concrete wijziging aan een lusdebiet aanbevolen. |
| FR-25 | M | Iedere aanbeveling bevat een concrete actie, reden, verwachte uitkomst, voorwaarden, evaluatiemethode en criterium om terug te draaien. | De gebruiker kan na uitvoering bepalen of de wijziging geslaagd, ongunstig of nog onbeslist is. |
| FR-26 | M | De software prioriteert aanbevelingen en bundelt bevindingen die waarschijnlijk bij hetzelfde patroon horen. | Meerdere temperatuur- en cyclusmeldingen kunnen tot één onderzoekspunt leiden met de oorspronkelijke onderbouwing. |
| FR-27 | M | De gebruiker kan aanbevelingen accepteren, afwijzen, uitstellen, als uitgevoerd markeren en van een toelichting voorzien. | Een uitgestelde aanbeveling verschijnt opnieuw op het ingestelde moment of bij relevante verslechtering. |
| FR-28 | M | De software geeft expliciet aan wanneer gegevens onvoldoende zijn om advies te geven. | Bij onvoldoende bewijs wordt een aanvullende meting voorgesteld in plaats van een zekere diagnose. |

### Vereist informatieformaat van een aanbeveling

- Titel en relevantie voor energie, comfort of bedrijfsstabiliteit.
- Waargenomen patroon, periode en gebruikte signalen.
- Mogelijke verklaringen, aanwijzingen vóór/tegen en zekerheid.
- Concrete eerste actie of aanvullende meting.
- Verwacht effect en mogelijke invloed op comfort.
- Wijzigingsomvang wanneer die onderbouwd kan worden; anders geen verzonnen getal.
- Evaluatieperiode en voorwaarden voor vergelijkbaarheid.
- Succescriterium, terugdraaicriterium en opvolgstatus.

Voorbeeld van beoogde output, met fictieve waarden: “In 18 van 24 cv-cycli stopt de brander binnen drie minuten terwijl warmtevraag blijft bestaan. De werkelijke aanvoer overschrijdt de gewenste aanvoer vaak vlak vóór de stop. Dit past bij onvoldoende afgifte ten opzichte van het geleverde vermogen, maar bewijst de oorzaak niet. Controleer eerst welke circuits werkelijk open staan en of doorstroming beschikbaar is. Vergelijk vervolgens korte cycli en comfort onder vergelijkbare omstandigheden.”

## 6. Optimalisatie en effectmeting

| ID | Prioriteit | Requirement | Acceptatiecriterium |
|---|---|---|---|
| FR-29 | M | De gebruiker kan wijzigingen vastleggen met tijdstip, parameter, oude/nieuwe waarde, reden en betrokken aanbeveling. | Grafieken en analyses tonen de wijziging op het juiste tijdstip. |
| FR-30 | M | De software vergelijkt voor/na op starts, brandduur, temperaturen en beschikbare comfortgegevens. | Een afname in starts met tegelijk slechter comfort wordt niet zonder meer als verbetering beoordeeld. |
| FR-31 | S | De software vergelijkt verbruik met correctie of selectie op buitentemperatuur, binnensetpoint, bedrijfsduur en gebruik. | Zij toont ruwe én gecorrigeerde uitkomst, gebruikte aannames en wanneer perioden niet vergelijkbaar zijn. |
| FR-32 | M | De software herkent overlappende wijzigingen en onvoldoende vergelijkbare gegevens. | Bij gelijktijdige aanpassing van pomp en aanvoer krijgt geen van beide afzonderlijk de besparing toegeschreven. |
| FR-33 | S | De software ondersteunt een begeleid experiment met één wijziging, referentieperiode, observatieperiode en evaluatie. | Het experiment eindigt met verbeterd, verslechterd of onvoldoende bewijs en toont de relevante indicatoren. |
| FR-34 | S | De software kan een gecontroleerde proef met lagere aanvoer voorstellen als comfortdata en bedrijfsomstandigheden dit ondersteunen. | De proef bevat ruimtegebonden comfortgrenzen; voldoende temperatuur in de woonkamer alleen bewijst niet dat boven voldoende warmte beschikbaar is. |
| FR-35 | S | De software houdt een normaalgedragmodel bij en kan leren tijdelijk pauzeren of een nieuwe referentie opbouwen na grote veranderingen. | Een nieuwe thermostaatregeling of renovatie wordt niet automatisch als storing ten opzichte van de oude situatie gezien. |

Een weersgecorrigeerde verbruiksindicator is geen gemeten ketelrendement. Rendement wordt alleen getoond wanneer toegevoerde brandstofenergie én geleverde warmte voldoende betrouwbaar beschikbaar zijn; anders blijft het een expliciet benoemde schatting of verbruiksindicator. Besparingen in euro vereisen een door de gebruiker ingestelde prijs en vermelden de aannames.

## 7. Presentatie, meldingen en terugkoppeling naar Home Assistant

| ID | Prioriteit | Requirement | Acceptatiecriterium |
|---|---|---|---|
| FR-36 | M | De gebruiker ziet een overzicht van actuele bedrijfsmodus, gegevenskwaliteit, belangrijkste bevindingen en eerstvolgende aanbevolen actie. | Bij onvoldoende gegevens toont het overzicht geen misleidende groene beoordeling. |
| FR-37 | M | De gebruiker kan vanuit een conclusie het relevante tijdvak, cycli en signalen bekijken. | De meetgegevens waarmee een conclusie is onderbouwd zijn direct terug te vinden. |
| FR-38 | M | De software stelt samenvattende meetwaarden, bevindingen en aanbevelingsstatus beschikbaar aan Home Assistant. | Een gebruiker kan deze waarden in een dashboard tonen en een eigen notificatieautomatisering maken. |
| FR-39 | M | Meldingen zijn instelbaar naar ernst en frequentie, worden gebundeld en verdwijnen pas na aantoonbaar herstel. | Eén aanhoudend probleem veroorzaakt geen nieuwe melding per cyclus; verslechtering kan wel opnieuw melden. |
| FR-40 | S | De software kan een dag-/weekrapport en export van analyses leveren. | Het rapport bevat veranderingen, openstaande adviezen, effect van uitgevoerde wijzigingen en ontbrekende gegevens. |
| FR-41 | M | Advieshistorie bewaart de gebruikte meetperiode, instellingen en versie van de analyseregel. | De gebruiker kan later achterhalen waarom een eerder advies werd gegeven, ook na wijziging van een regel. |
| FR-42 | L | Een taalmodel kan berekende bevindingen in begrijpelijk Nederlands toelichten. | De toelichting gebruikt uitsluitend aangeleverde metingen en hypotheses; zij verzint geen meetwaarden, besparingen of zekerheid. |

## 8. Afbakening

De MVP adviseert over gebruikersinstellingen, warmteafgifte, regeling en benodigde vervolgmetingen. Zij wijzigt geen instellingen automatisch. Zij presenteert geen diagnose van verbranding, rookgasveiligheid of mechanische defecten op basis van alleen temperatuur- en statusdata. Door de ketel gemelde storingen worden als apparaatmelding weergegeven, met de bron erbij.

Automatische aansturing, vervanging van eTwist, autonome instellingsexperimenten, optimalisatie van tapwaterhygiëne, voorspelling van componentuitval en warmtepompregeling vallen buiten versie 1.

## 9. Aanbevolen ontwikkelvolgorde

1. **MVP:** signaalkoppeling, installatieprofiel, datakwaliteit, bedrijfsmodi, cycli, temperatuurpatronen, verklaarbare aanbevelingen, wijzigingslogboek en terugkoppeling naar Home Assistant.
2. **Uitbreiding:** ruimtecomfort, zones, mengverdeler, gasverbruik, weerscorrectie en begeleide experimenten.
3. **Later:** geleerd normaalgedrag, aanvullende rapportages, natuurlijke-taaltoelichting en eventueel een afzonderlijk ontworpen regelmodule.

### Minimale acceptatiescenario's voor de MVP

1. Langdurig cv-bedrijf zonder relevante afwijking: meetwaarden zichtbaar, geen ongefundeerd optimalisatieadvies.
2. Herhaald kort branden tijdens aanhoudende warmtevraag: één onderbouwde melding met hypotheses en een uitvoerbare vervolgstap.
3. Brander uit na beëindigde warmtevraag: niet geclassificeerd als pendelen tijdens aanhoudende vraag.
4. Tapwatercyclus: uitgesloten van cv-temperatuur- en pendelconclusies.
5. Uitval van CAN-/Home Assistant-data: kwaliteitsmelding, geen fictieve starts en geen conclusie dat het probleem is opgelost.
6. Gemengde installatie met onbekende verdelermetingen: beperkte hydraulische conclusie, geen specifiek lusadvies.
7. Aanvoerwijziging met betere cycli maar slechter comfort: uitkomst benoemt de afweging en activeert het ingestelde terugdraaicriterium.
8. Twee gelijktijdige wijzigingen of afwijkend weer: effect niet ten onrechte toegeschreven aan één parameter.
9. Opstookprotocol actief: data zichtbaar, uitgesloten van normale optimalisatie en referentiemodel.
10. Onvoldoende gegevens: status 'onvoldoende bewijs' met expliciete ontbrekende metingen.
