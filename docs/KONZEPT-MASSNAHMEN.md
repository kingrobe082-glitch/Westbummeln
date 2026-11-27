# Konzept: Maßnahmen je Einsatz

Stand: 27.11.2026 · Status: **PR A (F1) umgesetzt**, B–D offen · Basis: `main` @ 9333e11 (Stand nach PR A: Abschnitt 7.7)

> **Kurz gesagt:** Statt „Maßnahmen starten“ und einem Balken bis 100 % wählt der Gruppenführer
> echte Maßnahmen wie *Erkunden*, *Wasserversorgung aufbauen* oder *Angriffsleitung legen*. Jede dauert ein paar
> Sekunden und braucht einen freien Trupp. Wer die Reihenfolge falsch wählt oder zu lange wartet, bekommt eine
> Warnung im Funk und danach eine Eskalation (z. B. F1 → F2). Eskalationen lassen sich wieder einfangen. Am Ende
> gibt es eine Einsatzbilanz mit Sternen.

---

## Inhalt

1. [Spielidee in 5 Sätzen](#1-spielidee-in-5-sätzen)
2. [Grundregeln: Trupps, Voraussetzungen, Lage](#2-grundregeln-trupps-voraussetzungen-lage)
3. [Maßnahmen-Katalog je Stichwort](#3-maßnahmen-katalog-je-stichwort)
4. [Eskalation](#4-eskalation)
5. [Bedienung (GF, Leitstelle, KI, Handy)](#5-bedienung)
6. [Wertung / Einsatzbilanz](#6-wertung--einsatzbilanz)
7. [Datenmodell & Umsetzungsplan](#7-datenmodell--umsetzungsplan)
8. [Offene Fragen an Lars](#8-offene-fragen-an-lars)

---

## 1. Spielidee in 5 Sätzen

1. Am Einsatzort wählt der Gruppenführer für seine Trupps konkrete Maßnahmen aus einer kurzen Liste je
   Stichwort, z. B. bei F1 *Erkunden → Wasserversorgung → Angriffsleitung legen → Nachlöschen*.
2. Jede Maßnahme dauert echte Spielsekunden und belegt einen Trupp. Mit mehr Fahrzeugen laufen mehr Maßnahmen
   gleichzeitig, deshalb lohnt sich die richtige Alarmierung.
3. Die Lage lebt weiter: Das Feuer wächst ab dem Notruf, eine Person im Rauch hat nur begrenzt Zeit, ein
   ungesicherter Unfall wird zur Gefahr.
4. Falsche Reihenfolge, Zögern oder zu wenig Kräfte kündigen sich erst im Funk an („Tank halb leer!“) und
   eskalieren dann, z. B. F1 → F2 mit Nachforderung. Mit den richtigen Maßnahmen fängt man das wieder ein.
5. Am Ende zeigt eine Einsatzbilanz mit Zeiten, Eskalationen, geretteten Personen und 1–3 Sternen, was gut lief.
   Das gibt GF *und* Leitstelle ein echtes Ziel, und Anfänger spielen mit Tipps ohne Frust.

**Warum das Spaß macht:** Man trifft echte taktische Entscheidungen (Tankwasser-Schnellangriff oder erst
Wasserversorgung?), sieht sofort die Folgen und lernt nebenbei FwDV 3. Die Leitstelle merkt, ob sie schnell und
mit den richtigen Fahrzeugen alarmiert hat.

---

## 2. Grundregeln: Trupps, Voraussetzungen, Lage

### 2.1 Wer kann was? Trupps je Fahrzeug

Jedes Fahrzeug vor Ort (Phase `vorort`) hat **Plätze für Maßnahmen**:

| Platz | Symbol | Wer | Wofür |
|---|---|---|---|
| Führung | 🧭 | 1 je Fahrzeug (der GF selbst) | Erkunden, Lagemeldung, Einsatzleitung, Übergabe |
| Trupp | 👥 | abhängig von `seats` (siehe unten) | alles Handwerkliche: Wasser, Angriff, Retten, Absichern … |

Die Zahl der Trupps kommt aus dem vorhandenen Feld `seats` (Raumverwaltung kann es schon heute ändern):

| `seats` | Besatzung | Trupps | Standard bei |
|---|---|---|---|
| 1–3 | Führungstrupp | 1 (nur „leichte“ Maßnahmen) | KdoW (3) |
| 4–6 | Staffel | 2 | – |
| 7–12 | Gruppe | 3 (Angriffs-, Wasser-, Schlauchtrupp) | HLF 20, LF 20 (9) |

**Fahrzeugtypen in den Tabellen:**
`L` = LF 20 **oder** HLF 20 · `H` = **nur HLF 20** (hydraulischer Rettungssatz) · `K` = auch KdoW · `A` = alle.

**Tankwasser** (für Schnellangriff ohne Wasserversorgung), als Löschzeit in Spielsekunden:
LF 20 (2000 l) = **40 s**, HLF 20 (1600 l) = **32 s**, KdoW = 0.

**KdoW-Bonus:** Maßnahme „Einsatzleitung übernehmen“ (🧭, 5 s). Danach laufen alle neu gestarteten Maßnahmen
an diesem Einsatz 10 % schneller. So hat der KdoW eine echte Rolle.

### 2.2 Zwei Arten von Voraussetzungen

Das ist der Kern der Idee „falsche Reihenfolge eskaliert“:

- 🔒 **hart:** Der Button ist gesperrt und nennt den Grund. Beispiel: *Nachlöschen* erst, wenn das Feuer aus ist.
  Hier geht es um Logik, nicht um Taktik.
- ⚠️ **weich:** Die Maßnahme geht trotzdem, aber mit Risiko. Beispiel: *Angriff* ohne *Wasserversorgung* ist
  möglich (Tankwasser), aber der Tank geht nach 40 s leer. Hier entsteht die Taktik.

Die Oberfläche zeigt weiche Voraussetzungen offen an („⚠️ ohne Wasserversorgung: Tank reicht 40 s“). Niemand soll
in eine Falle laufen, ohne es hätte wissen zu können.

### 2.3 Die Lage: wenige, sichtbare Zahlen

Je Einsatz gibt es höchstens drei Lagewerte. Sie stehen in einer **Lage-Leiste** über den Maßnahmen:

| Wert | Symbol | Bedeutung | Wann |
|---|---|---|---|
| Brand | 🔥 0–100 | Ausbreitung; wächst ab Einsatzanlage, sinkt beim Löschen | F1, F2, F3 Y, BMA (Brand), TH (Fahrzeugbrand) |
| Gas | 💨 0–100 | Gaskonzentration (Spielwert, keine echte % UEG) | ABC1 |
| Personen | 👤 | Je Person: Zustand + Countdown | F3 Y, TH1, TH2 |

**Wetter wirkt mit** (schon vorhanden: `WORK_FACTOR`): Maßnahmen dauern bei Regen/Nebel länger.
Neu: Wind ×1,3 und Regen ×0,8 auf das Brandwachstum.

**Löschen:** Ein Angriffstrupp senkt den Brand um 0,8 pro Sekunde, höchstens 2 Trupps gleichzeitig (1,6/s).
Das Wachstum läuft weiter, man löscht also gegen das Wachstum an. Ohne Wasserversorgung verbraucht jeder
löschende Trupp das Tankwasser seines Fahrzeugs; mit Wasserversorgung ist Wasser unbegrenzt.

**Vor dem Erkunden** zeigt die Lage-Leiste nur eine grobe Angabe („🔥 ? klein“), die genaue Zahl und die
Variante erst danach. Das ist der Preis fürs Überspringen.

**Ende:** Der Einsatz ist abgearbeitet, wenn alle Pflicht-Maßnahmen ✅ sind. Dann folgt wie heute der
Abschluss mit Rückfahrt, neu mit Einsatzbilanz.

---

## 3. Maßnahmen-Katalog je Stichwort

Lesehilfe: **Dauer** in Spielsekunden bei Sonne. **Platz** 🧭/👥. **Fz** = Fahrzeugtyp (`L`, `H`, `K`, `A`).
**Voraussetzung** 🔒 hart / ⚠️ weich. **P** = Pflicht für den Abschluss.

Die **KI-Reihenfolge** ist die Musterlösung. Die KI-GF nutzt sie, und im Übungsmodus zeigt sie der Tipp an.

### 3.1 F1 · Kleinbrand (z. B. Mülltonne, Gartenhütte, Hecke)

AAO-Empfehlung: 1 LF 20 · Lage: 🔥 Start 15, +0,2/s ab Notruf

| # | Maßnahme | Dauer | Platz | Fz | Voraussetzung | P |
|---|---|---|---|---|---|---|
| 1 | Erkunden | 10 s | 🧭 | A | – | |
| 2 | Wasserversorgung aufbauen (Hydrant → Pumpe) | 30 s | 👥 | L | – | |
| 3 | Angriffsleitung legen & löschen | 15 s Aufbau, dann löscht er | 👥 | L | ⚠️ Erkunden · ⚠️ Wasserversorgung | P |
| 4 | Nachlöschen & Kontrolle | 20 s | 👥 | L | 🔒 Brand = 0 | P |

```
Erkunden ──► Wasserversorgung ──┐
    └──────► Angriffsleitung ───┴──► (Brand 0) ──► Nachlöschen ✅
             (parallel möglich; ohne Wasser: Tank 32–40 s)
```

- **Parallel:** Wasserversorgung und Angriff gleichzeitig mit 2 Trupps. So macht es eine echte Gruppe.
- **Taktik:** Eine Mülltonne ist mit Tankwasser lösbar, das ist realistisch. Bei einer Gartenhütte reicht der
  Tank nicht. *Erkunden* verrät, welcher Fall es ist. Wer spät kommt, braucht die Wasserversorgung immer.
- **Varianten** (zufällig beim Anlegen, *Erkunden* deckt sie auf): Mülltonne (🔥 10), Gartenhütte (🔥 25),
  Hecke am Haus (🔥 20, wächst ×1,5 Richtung Haus).

**Beispiel ideal (Gartenhütte, 🔥 25):** Eintreffen bei 20 s (🔥 29) → Erkunden bis 30 s → Trupp 1 Angriff,
Trupp 2 Wasser, Trupp 3 zweiter Angriff → ab 45 s wird gelöscht (🔥 34, −1,4/s) → Feuer aus bei ca. 70 s →
Nachlöschen bis 90 s. Das dauert ungefähr so lang wie heute (ca. 60 s Balken), aber mit Entscheidungen.
Mit nur einem Angriffstrupp ist das Feuer erst bei ca. 100 s aus, und ohne Wasserversorgung wäre der Tank vorher leer.

### 3.2 F2 · Wohnungsbrand (keine Person vermisst)

AAO: 1 HLF 20 + 1 LF 20 + KdoW · Lage: 🔥 Start 35, +0,25/s

| # | Maßnahme | Dauer | Platz | Fz | Voraussetzung | P |
|---|---|---|---|---|---|---|
| 1 | Erkunden (Rückmeldung: Geschoss, Personen) | 10 s | 🧭 | A | – | |
| 2 | Einsatzleitung übernehmen | 5 s | 🧭 | K | – | |
| 3 | Wasserversorgung aufbauen | 30 s | 👥 | L | ⚠️ Erkunden | |
| 4 | Atemschutzüberwachung einrichten | 10 s | 🧭 | A | – | |
| 5 | Innenangriff unter Atemschutz | 20 s Aufbau, dann löscht er | 👥 | L | ⚠️ Erkunden · ⚠️ Wasser · ⚠️ AS-Überwachung · ⚠️ Sicherheitstrupp | P |
| 6 | Sicherheitstrupp bereitstellen | 10 s, bleibt belegt | 👥 | L | – | |
| 7 | Rauchschutzvorhang / Treppenhaus sichern | 15 s | 👥 | L | – | |
| 8 | Belüften (Überdrucklüfter) | 20 s | 👥 | L | ⚠️ Brand ≤ 20 | |
| 9 | Nachlöschen & Kontrolle (Wärmebildkamera) | 20 s | 👥 | L | 🔒 Brand = 0 | P |
| 10 | Lagemeldung an Leitstelle | 5 s | 🧭 | A | 🔒 Erkunden | |

- **Eigenschutz (FwDV 7):** Innenangriff ohne AS-Überwachung oder ohne Sicherheitstrupp geht, zählt aber als
  **Sicherheitsverstoß** (Bilanz) und kommt als Warnung im Funk.
- **Falle (nur Profi):** Belüften bei Brand > 20 → doppeltes Brandwachstum für 20 s („Sauerstoffzufuhr!“).
- Eine Gruppe (3 Trupps) schafft F2 allein: Angriff, Wasser, Sicherheitstrupp. Mit zweitem Fahrzeug geht es schneller.

### 3.3 F3 Y · Wohnungsbrand, Menschenleben in Gefahr

(„Y“ = Menschenleben in Gefahr, wie in vielen Alarmierungsstichworten.)

AAO: 2 HLF 20 + 1 LF 20 + KdoW · Lage: 🔥 Start 45, +0,3/s · 👤 1 Person (Variante: 1. OG oder 2. OG)

Alles aus F2, dazu:

| # | Maßnahme | Dauer | Platz | Fz | Voraussetzung | P |
|---|---|---|---|---|---|---|
| 11 | Menschenrettung unter Atemschutz | 25 s | 👥 | L | ⚠️ Erkunden · ⚠️ AS-Überwachung | P |
| 12 | Rettung über tragbare Leiter (Person am Fenster) | 20 s | 👥 | L | 🔒 Erkunden zeigt „Person am Fenster“ | |
| 13 | Patient an Rettungsdienst übergeben | 5 s | 🧭 | A | 🔒 Person gerettet · 🔒 RTW angefordert (Leitstelle) | P |

- **Grundregel:** Menschenrettung vor Brandbekämpfung. Beides parallel ist erlaubt und sogar gut, wenn genug
  Trupps da sind. Nur Angriff und keine Rettung lässt den Personen-Countdown laufen (siehe 4.2).
- **Ab 🔥 100 (Vollbrand):** Neue Maßnahme *Riegelstellung zum Nachbarhaus* (👥 L, 25 s, Pflicht).

### 3.4 TH1 · Verkehrsunfall (keine Person eingeklemmt)

AAO: 1 HLF 20 · Lage: 👤 1 leicht verletzte Person · Gefahren: ungesichert, Betriebsstoffe

| # | Maßnahme | Dauer | Platz | Fz | Voraussetzung | P |
|---|---|---|---|---|---|---|
| 1 | Einsatzstelle absichern (Fahrzeug quer, Warnleitkegel) | 15 s | 👥 | K | – | P |
| 2 | Erkunden | 10 s | 🧭 | A | – | |
| 3 | Brandschutz sicherstellen (Pulver/Schnellangriff) | 15 s | 👥 | L | – | |
| 4 | Erstversorgung Patient | 20 s | 👥 | A | – | P |
| 5 | Batterie abklemmen | 10 s | 👥 | L | ⚠️ Brandschutz | |
| 6 | Auslaufende Betriebsstoffe binden | 25 s | 👥 | L | – | P |
| 7 | Patient an Rettungsdienst übergeben | 5 s | 🧭 | A | 🔒 Erstversorgung · 🔒 RTW angefordert | P |
| 8 | Übergabe an Polizei, Fahrbahn frei | 10 s | 🧭 | A | 🔒 Betriebsstoffe gebunden | P |

- **Eigenschutz zuerst:** *Absichern* ist der erste Schritt (auch mit KdoW).
- **Variante „Kraftstoff läuft aus“** (Erkunden zeigt sie): ohne Brandschutz + Batterie in 60 s → Fahrzeugbrand (siehe 4.3).

### 3.5 TH2 · Verkehrsunfall, Person eingeklemmt

AAO: 1 HLF 20 + 1 LF 20 + KdoW · Lage: 👤 1 eingeklemmte Person (Countdown)

| # | Maßnahme | Dauer | Platz | Fz | Voraussetzung | P |
|---|---|---|---|---|---|---|
| 1 | Einsatzstelle absichern | 15 s | 👥 | K | – | |
| 2 | Erkunden (Art der Einklemmung) | 10 s | 🧭 | A | – | |
| 3 | Brandschutz sicherstellen | 15 s | 👥 | L | – | |
| 4 | Fahrzeug stabilisieren / unterbauen | 15 s | 👥 | L | – | |
| 5 | Patient betreuen (Erstversorgung, Innenbetreuung) | 15 s, bleibt belegt | 👥 | A | – | |
| 6 | Glasmanagement | 10 s | 👥 | L | ⚠️ Patient betreut | |
| 7 | Rettungsöffnung schaffen (Tür / Dach) | 25 s leicht · 45 s schwer | 👥 | **H** | 🔒 Erkunden · ⚠️ Stabilisieren · ⚠️ Brandschutz | P |
| 8 | Patientengerechte Rettung | 20 s | 👥 | A | 🔒 Rettungsöffnung | P |
| 9 | Patient an Rettungsdienst übergeben | 5 s | 🧭 | A | 🔒 gerettet · 🔒 RTW/NEF angefordert | P |

- **Nur das HLF hat den Rettungssatz.** Ist kein HLF vor Ort, steht da „🔒 Rettungssatz fehlt – HLF 20
  nachfordern“, und der GF kann mit einem Tipp nachfordern. Hier lernt die **Leitstelle**, das richtige Fahrzeug zu schicken.
- **Patient betreuen** halbiert die Geschwindigkeit des Personen-Countdowns. Das ist eine gute Entscheidung für Trupp 1.

### 3.6 BMA · Brandmeldeanlage

AAO: 1 LF 20 (+ KdoW) · Variante verdeckt: Fehlalarm 60 % · Täuschungsalarm (Dampf/Staub) 30 % · Entstehungsbrand 10 %

| # | Maßnahme | Dauer | Platz | Fz | Voraussetzung | P |
|---|---|---|---|---|---|---|
| 1 | Erkunden an FIZ (FAT/FBF, Laufkarte, Schlüsseldepot) | 10 s | 🧭 | A | – | P |
| 2 | Melderbereich kontrollieren | 20 s | 👥 | K | 🔒 Erkunden | P |
| 3 | BMA zurückstellen, Übergabe an Betreiber | 10 s | 🧭 | A | 🔒 Melderbereich kontrolliert *(Profi: nur ⚠️)* | P |

- Zeigt die Kontrolle einen **Entstehungsbrand** (🔥 5, +0,3/s), kommen die F1-Maßnahmen dazu, und das
  Stichwort wird „BMA → F1“.
- **Falle (nur Profi):** zurückstellen ohne Kontrolle bei echtem Brand → nach 60 s „Passant meldet Rauch“ → F2.

### 3.7 ABC1 · Gasgeruch in Gebäude

AAO: 1 HLF 20 + KdoW · Lage: 💨 Start 20, +0,4/s (Variante „Leitung im Keller defekt“: +0,8/s)

| # | Maßnahme | Dauer | Platz | Fz | Voraussetzung | P |
|---|---|---|---|---|---|---|
| 1 | Erkunden (Zündquellen vermeiden!) | 10 s | 🧭 | A | – | |
| 2 | Gefahrenbereich absperren | 15 s | 👥 | K | – | P |
| 3 | Messen mit Gasmessgerät | 15 s | 👥 | K | – | P |
| 4 | Gebäude räumen | 25 s | 👥 | A | – | P |
| 5 | Gaszufuhr absperren (Hauptabsperreinrichtung) | 15 s | 👥 | L | ⚠️ Messen (bei 💨 > 50 nur mit Atemschutz = 25 s) | P |
| 6 | Natürlich lüften (Fenster öffnen) | 15 s, danach −1/s | 👥 | A | ⚠️ Gaszufuhr abgesperrt | |
| 7 | Übergabe an Netzbetreiber | 5 s | 🧭 | A | 🔒 Gaszufuhr abgesperrt · 🔒 💨 < 10 · 🔒 Netzbetreiber angefordert | P |

- **Falle (nur Profi):** *Überdrucklüfter einsetzen* vor dem Messen → Sicherheitsverstoß + Eskalation
  („Lüfter nicht ex-geschützt – alle raus!“).

### 3.8 Alle anderen Stichworte

Freitext-Stichworte der Leitstelle und neue KI-Stichworte ohne Katalogeintrag (z. B. „TH · Wasserschaden“)
bekommen den **Allgemein-Ablauf**: *Erkunden* + *Maßnahmen durchführen* (= heutiger Fortschrittsbalken).
So geht nichts kaputt, und der Katalog kann Schritt für Schritt wachsen.

Erkannt wird das Stichwort am Titelanfang vor „ · “ (`'F1 · Kleinbrand'` → `F1`), so wie es die
Schnellstichworte in `templates/index.html` und `AI_TITLES` in `game/engine.py` schon schreiben.

---

## 4. Eskalation

### 4.1 Prinzip: erst warnen, dann eskalieren, dann einfangen

Jede Eskalationsregel hat drei Schritte:

1. **Warnung** nach ⅔ der Zeit: Funkspruch + ⚠️ mit Countdown an der betroffenen Lage oder Maßnahme.
2. **Folge**, wenn bis zum Ablauf nichts passiert: Funkspruch, Lage-Ampel wird schlechter, oft eine neue
   Maßnahme oder Nachforderung.
3. **Einfangen:** Die neue Gegenmaßnahme erscheint oben in der Liste. Ist sie erledigt, kommt
   „Lage wieder unter Kontrolle“ und die Ampel wird wieder grün. Die Bilanz merkt sich die schlimmste Stufe.

**Es gibt kein Game Over.** Jeder Einsatz bleibt lösbar, er dauert nur länger und gibt weniger Sterne.

### 4.2 Eskalationsstufen

| Stufe | Ampel | Bedeutung | Beispiele |
|---|---|---|---|
| 0 | 🟢 | Lage stabil | – |
| 1 | 🟡 | Lage verschärft | Wasser aus, Beinahe-Folgeunfall, Patient verschlechtert sich |
| 2 | 🟠 | Stichworterhöhung + Nachforderung | F1 → F2, F2 → F3 Y, ABC1 → ABC2, BMA → F2 |
| 3 | 🔴 | Schaden eingetreten | Vollbrand, Person schwer verletzt, Verpuffung |

### 4.3 Regeln im Einzelnen

| # | Auslöser | Warnung (Funk) | Folge | Einfangen |
|---|---|---|---|---|
| E1 | Angriff ohne Wasserversorgung | „Tank halb leer – Wasserversorgung?“ (bei 50 % Tank) | **Wasser aus:** Löschen pausiert, Brand wächst doppelt, 🟡 | Wasserversorgung fertigstellen → Löschen läuft weiter |
| E2 | 🔥 erreicht Schwelle (F1: 40 · F2: 70) | „Feuer greift auf Carport/Nachbarwohnung über“ bei Schwelle −10 | **Stichworterhöhung** F1→F2 bzw. F2→F3 Y, neue Maßnahmen und Person, Nachforderung nach AAO, 🟠 | Brand unter Schwelle löschen, neue Pflicht-Maßnahmen erledigen |
| E3 | 🔥 erreicht 100 | „Durchzündung droht!“ bei 85 | **Vollbrand**, Riegelstellung wird Pflicht, 🔴 | Riegelstellung + Löschen |
| E4 | Person nicht gerettet (F3 Y) | bei 80 s nach Notruf | **120 s:** Person verletzt (🟡) · **200 s:** schwer verletzt (🔴) | Menschenrettung stoppt den Countdown |
| E5 | Erkunden übersprungen | – (das ist der Sinn) | Verdeckte Lage meldet sich spät: „Nachbar: Da ist noch jemand drin!“ (+Person, weniger Zeit) | Menschenrettung |
| E6 | VU nicht abgesichert (TH1/TH2) | 30 s nach Eintreffen: „Achtung, Verkehr fährt dicht vorbei!“ | **45 s: Folgeunfall** → +1 leicht verletzte Person, 🟡 | Absichern + Erstversorgung der neuen Person |
| E7 | Betriebsstoffe nicht gebunden (TH1) | 60 s | **90 s: Öl im Kanal** → Umweltschaden (Bilanz), neue Maßnahme „Kanal abdichten“ | Kanal abdichten |
| E8 | Kraftstoff läuft aus + kein Brandschutz/Batterie | 40 s | **60 s: Fahrzeugbrand** → F1-Maßnahmen dazu, 🟠 | Löschen |
| E9 | Patient eingeklemmt (TH2) | bei 100 s | **150 s:** Zustand verschlechtert (🟡) · **240 s:** kritisch (🔴). *Betreuen* halbiert das Tempo. | Rettung + Übergabe |
| E10 | 💨 ≥ 60 und nicht geräumt (ABC1) | bei 💨 45 | **ABC2 · Explosionsgefahr**, Nachforderung, 🟠 | Räumen + Gaszufuhr absperren |
| E11 | 💨 ≥ 100 | bei 💨 85 | **Verpuffung** → Gebäudeschaden; Verletzte, falls nicht geräumt, 🔴 | Löschen/Räumen |
| E12 | Kein Fahrzeug mit benötigtem Typ vor Ort | sofort am gesperrten Button | – (keine Strafe, nur Zeitverlust) | Nachfordern |

**Zeiten ab Notruf, nicht ab Eintreffen:** Brandwachstum und Personen-Countdowns laufen ab Einsatzanlage.
So zählt auch, wie schnell die Leitstelle alarmiert.

### 4.4 Beispiel-Funkverkehr (F1 → F2)

Gartenhütte (🔥 25 beim Notruf um 14:01:40), ein LF 20, der GF lässt die Wasserversorgung weg:

```
14:02:10  Florian WB 2 LF 20   Status 4 – Einsatzstelle erreicht.                    🔥 31
14:02:20  Florian WB 2 LF 20   Erkundung: Gartenhütte brennt, Hecke zum Wohnhaus.
14:02:21  Florian WB 2 LF 20   Trupp 1: Angriffsleitung legen.
14:02:56  Florian WB 2 LF 20   ⚠️ Angriffstrupp: Tank halb leer – Wasserversorgung?    🔥 24
14:03:16  Florian WB 2 LF 20   🟡 Wasser aus! Angriffstrupp geht zurück.               🔥 12
14:04:01  Einsatzleitung       ⚠️ Feuer greift auf Carport über.                       🔥 30
14:04:05  Florian WB 2 LF 20   Trupp 2: Wasserversorgung aufbauen.
14:04:26  Einsatzleitung       🟠 Stichworterhöhung F1 → F2. Nachforderung: 1 HLF 20, 1 KdoW.
14:04:35  Florian WB 2 LF 20   Wasserversorgung steht. Angriff läuft wieder.
14:05:20  Einsatzleitung       🟢 Lage wieder unter Kontrolle.
```

Hätte der GF die Wasserversorgung um 14:02:21 parallel gestartet, wäre das Feuer um ca. 14:03:35 aus gewesen.

---

## 5. Bedienung

### 5.1 Gruppenführer: Panel „🧯 Meine Einsatzstelle“

Es erscheint im `controlPanel`, sobald das eigene Fahrzeug `vorort` ist. Es ersetzt dort den Button
„Maßnahmen starten“. In der Einsatzliste sehen alle eine kompakte Nur-Lese-Ansicht.

**Handy (eine Spalte, Buttons ≥ 44 px, Symbole immer mit Text, nie nur Farbe):**

```
┌──────────────────────────────────────┐
│ 🧯 F1 · Kleinbrand – Hauptstraße 5   │
│ 🟡 Lage verschärft                   │
│ 🔥 Brand 34 ▲   💧 Tank 12 s         │  ← Lage-Leiste, bleibt oben
├──────────────────────────────────────┤
│ Mein LF 20:  🧭 frei                 │
│   👥 Trupp 1: Angriff  ███████░ löscht│
│   👥 Trupp 2: frei                   │
│   👥 Trupp 3: frei                   │
├──────────────────────────────────────┤
│ ⚠️ Tank halb leer – Wasserversorgung?│  ← aktive Warnung
├──────────────────────────────────────┤
│ ⏳ LÄUFT                              │
│ Angriffsleitung & löschen  Trupp 1   │
│                                      │
│ ▶ VERFÜGBAR                          │
│ [ 💧 Wasserversorgung aufbauen  30 s ]│  ← Tipp-Rahmen im Übungsmodus
│                                      │
│ 🔒 GESPERRT (1) ▸                     │  ← eingeklappt
│ ✅ ERLEDIGT (1) ▸   Erkunden          │
└──────────────────────────────────────┘
```

- **Antippen** startet die Maßnahme mit dem nächsten freien Trupp des eigenen Fahrzeugs.
- **Lange drücken / ⓘ** zeigt eine Zeile Erklärung mit Fachbegriff, z. B. „Hydrant → Sammelstück → Pumpe.
  Ohne sie hält der Tank 40 s.“
- **Laufende Maßnahme antippen** → „Abbrechen?“, der Trupp wird frei (z. B. um auf Menschenrettung umzuschwenken).
  Der Fortschritt geht verloren.
- Weiche Voraussetzung fehlt → Button bleibt aktiv, Unterzeile ⚠️ „ohne Wasserversorgung: Tank 40 s“.
- Harte Voraussetzung fehlt → grau, Unterzeile 🔒 mit Grund.

### 5.2 Leitstelle: Einsatzkarte in der Liste

```
┌──────────────────────────────────────────────┐
│ F2 · Wohnungsbrand ⬆ (war F1)   🟠 In Arbeit │
│ 📍 Hauptstraße 5 · 14:01                     │
│ 🔥 52 ▼   Maßnahmen 3/6 ✅                   │
│ Vor Ort: WB 2 LF 20 · Anfahrt: WB 3 HLF 20   │
│ 🔴 NACHFORDERUNG: 1 HLF 20 ✔ · 1 KdoW ✖      │
│   [KdoW wählen ▾] [Alarmieren]               │
│ ☎ Dienste: [RTW anfordern] [Polizei] [Stadtw.]│
│ AAO-Vorschlag: HLF 20, LF 20, KdoW           │  ← nur Übung/Normal
│ [Einsatz beenden]                            │
└──────────────────────────────────────────────┘
```

- **Lagemeldungen** kommen wie heute als Funk (`emit`), neu mit Ampel-Symbol.
- **Nachforderungen** (automatisch durch Eskalation oder vom GF über „Lagemeldung“) erscheinen als roter
  Kasten, mit Haken, sobald ein passendes Fahrzeug alarmiert ist.
- **Virtuelle Dienste** (RTW/NEF, Polizei, Netzbetreiber) sind keine Fahrzeuge auf der Karte. Die Leitstelle
  fordert sie an, nach 30 s melden sie sich im Funk „eingetroffen“, und das entsperrt die Übergabe-Maßnahmen.
  Das gibt der Leitstelle während des Einsatzes Arbeit, ohne neue Fahrzeuge einzuführen.
- Der Kartenpin bekommt die Ampelfarbe und bei Stichworterhöhung ein ⬆.

### 5.3 KI

**KI-Gruppenführer** (Erweiterung von `ai_group_leaders`): An unbesetzten Fahrzeugen vor Ort (im KI-Modus sofort,
sonst nach `UNATTENDED_DELAY`) wählt die KI für jeden freien Trupp die nächste Maßnahme:

1. Gibt es eine aktive Warnung mit Gegenmaßnahme → diese zuerst (die KI fängt ein und zeigt damit das Muster).
2. Sonst die nächste verfügbare Maßnahme aus der KI-Reihenfolge des Stichworts.
3. **Mit Absicht nicht perfekt:** Bei *Normal* nimmt sie mit 15 % Wahrscheinlichkeit die zweitbeste verfügbare
  Maßnahme (z. B. Angriff vor Wasser), bei *Profi* mit 25 %. Bei *Übung* spielt sie perfekt. Fallen wählt sie nie.
4. Zufall mit festem Startwert je Einsatz (`random.Random(inc['id'])`), damit Tests reproduzierbar sind.
5. Jede KI-Entscheidung kommt in den Funk („KI-GF WB 4 HLF: Trupp 2 – Fahrzeug stabilisieren“), so lernen
   Menschen mit.

Menschliche Entscheidungen haben Vorrang: Die KI startet keine Maßnahme, die ein Mensch am selben Einsatz
schon gestartet hat.

**KI-Leitstelle** (`run_ai`): alarmiert nach AAO-Vorschlag (soweit Fahrzeuge frei und erlaubt), erfüllt
Nachforderungen nach 10 s und fordert virtuelle Dienste automatisch an.

### 5.4 Mehrere GF an einem Einsatz

Die Maßnahmen gehören dem **Einsatz**, nicht dem Fahrzeug. Jeder GF vor Ort kann jede Maßnahme mit seinen
eigenen Trupps starten. Eine Maßnahme läuft höchstens einmal, nur der Löschangriff bis zu zweimal.
Die vorhandenen **Abschnitte** bleiben: Der Abschnitts-Fortschritt wird der Anteil erledigter Maßnahmen, die
Fahrzeuge dieses Abschnitts gestartet haben.

---

## 6. Wertung / Einsatzbilanz

### 6.1 Bilanz beim Abschluss

Kommt als Funkzeile und als aufklappbare Karte am abgeschlossenen Einsatz:

```
┌────────────────────────────────────────┐
│ 📋 Einsatzbilanz F1 → F2 · Hauptstr. 5 │
│ ★★☆  78 Punkte                         │
│                                        │
│ ⏱ Notruf → Alarm         0:08  👍      │  ← Leitstelle
│ ⏱ Alarm → Eintreffen     0:19          │
│ ⏱ Eintreffen → Feuer aus 2:31          │  ← GF
│ ⏱ Gesamt                 3:40          │
│ 🟠 Höchste Stufe: Stichworterhöhung    │
│ 💧 Wasser aus: 1×                      │
│ 👤 Personen: –                         │
│ ⚠️ Sicherheitsverstöße: 0              │
│ 💡 Tipp: Bei Gartenhütte die Wasser-   │
│    versorgung parallel zum Angriff.    │
└────────────────────────────────────────┘
```

### 6.2 Punkte (Start 100, Rahmen 0–120)

| Ereignis | Punkte |
|---|---|
| Höchste Stufe 🟡 / 🟠 / 🔴 | −10 / −20 / −35 |
| Person verletzt / schwer verletzt | −15 / −30 |
| Sicherheitsverstoß (je) | −5 |
| Wasser aus (je) | −5 |
| Lagemeldung abgegeben | +5 |
| Schneller als Richtzeit des Stichworts | bis +15 |
| Notruf → Alarm unter 20 s (Leitstelle) | +5 |
| AAO erfüllt (richtige Fahrzeugtypen alarmiert) | +5 |

**Sterne:** ★★★ ab 90 · ★★ ab 65 · ★ darunter. Ein Einsatz endet immer mit mindestens ★, damit niemand
mit „0 Punkte“ heimfährt.

Beendet die Leitstelle den Einsatz vorzeitig über „Einsatz beenden“, steht in der Bilanz
„abgebrochen“ und es gibt keine Sterne.

### 6.3 Schwierigkeitsstufen (Raumeinstellung wie Wetter, nur Raumverwaltung)

| | 🟢 Übung | 🟡 Normal | 🔴 Profi |
|---|---|---|---|
| Eskalationen | nur Warnung, keine Folgen | ja, mit Warnung | ja, Warnzeit nur ½ |
| Timer (Brand, Personen) | ×1,5 Zeit | ×1 | ×0,75 |
| Tipp „nächste Maßnahme“ | immer sichtbar | nach einem Fehler | nie |
| AAO-Vorschlag Leitstelle | ja | ja | nein |
| Fallen (z. B. Belüften zu früh) | ausgeblendet | ausgeblendet | sichtbar |
| KI-Fehlerquote | 0 % | 15 % | 25 % |

---

## 7. Datenmodell & Umsetzungsplan

### 7.1 Dateien

| Datei | Inhalt |
|---|---|
| `game/katalog.py` **neu** | **Nur Daten**: Stichworte, Maßnahmen, Varianten, AAO, Eskalationsregeln. Python-Dicts statt JSON: Kommentare möglich, `ruff` prüft, Tests importieren direkt, kein Datei-Laden. |
| `game/massnahmen.py` **neu** | **Reine Logik ohne Django**: `stichwort_aus_titel`, `init_einsatz`, `starten`, `abbrechen`, `tick` (Lage, Fertigstellung, Regeln), `ki_waehlen`, `bilanz`, `snapshot_massnahmen`. |
| `game/engine.py` | Nur **Haken** an 6 Stellen (siehe 7.3), damit es mit parallelen Sessions wenig Konflikte gibt. |
| `static/js/game.js` | Panel „Meine Einsatzstelle“, kompakte Einsatzkarte, Bilanzkarte, Ticker für Countdowns. |
| `templates/index.html` | Container `#scenePanel` im `controlPanel`, Schwierigkeit in der Raumverwaltung. |
| `tests/test_massnahmen.py` **neu** | Siehe 7.5. |

### 7.2 Katalog-Format (Beispiel F1)

```python
# game/katalog.py
L = ('HLF 20', 'LF 20')
ALLE = ('HLF 20', 'LF 20', 'KdoW')

KATALOG = {
    'F1': {
        'name': 'Kleinbrand',
        'aao': ['LF 20'],
        'lage': {'brand': 15, 'wachstum': .2},
        'eskalation': {'brand': [(40, 'F2')]},          # Schwelle → neues Stichwort
        'varianten': {'muelltonne': {'brand': 10}, 'gartenhuette': {'brand': 25},
                      'hecke': {'brand': 20, 'wachstum': .3}},
        'ki': ['erkunden', 'angriff', 'wasser', 'nachloeschen'],
        'richtzeit': 150,
        'massnahmen': {
            'erkunden': {'name': 'Erkunden', 'dauer': 10, 'platz': 'fuehrung', 'fz': ALLE},
            'wasser': {'name': 'Wasserversorgung aufbauen', 'dauer': 30, 'platz': 'trupp', 'fz': L,
                       'wirkung': 'wasser'},
            'angriff': {'name': 'Angriffsleitung legen & löschen', 'dauer': 15, 'platz': 'trupp', 'fz': L,
                        'weich': ['erkunden', 'wasser'], 'wirkung': 'loeschen', 'max': 2, 'pflicht': True},
            'nachloeschen': {'name': 'Nachlöschen & Kontrolle', 'dauer': 20, 'platz': 'trupp', 'fz': L,
                             'hart': ['brand_aus'], 'pflicht': True},
        },
    },
}
```

### 7.3 Einsatz-Zustand (Erweiterung von `new_incident`)

```python
inc = {
    ...,                                  # alles wie heute (title, assigned, sections, progress, working …)
    'stichwort': 'F1',                    # aus dem Titel; ändert sich bei Stichworterhöhung
    'stufe': 0, 'stufe_max': 0,           # aktuelle Ampel / schlimmste Stufe (Bilanz)
    'variante': 'gartenhuette',           # verdeckt bis Erkunden – NICHT im Snapshot vorher!
    'lage': {'brand': 15.0, 'wasser': False, 'tank': {'WB-2-LF20': 40.0}, 'personen': []},
    'm': {                                # Zustand je Maßnahme
        'erkunden': {'status': 'fertig', 'fz': 'WB-2-LF20', 'platz': 'fuehrung',
                     'start': 1000.0, 'ende': 1010.0},
        'angriff':  {'status': 'laeuft', 'fz': 'WB-2-LF20', 'platz': 'trupp', 'trupp': 1,
                     'start': 1010.0, 'ende': 1025.0},
    },
    'warnungen': {'E1': 1052.0},          # Regel → Zeitpunkt der Warnung
    'ereignisse': [],                     # für die Bilanz: {'zeit', 'regel', 'stufe', 'text'}
    'nachforderungen': [{'kind': 'HLF 20', 'erfuellt': False}],
    'dienste': {'RTW': 1100.0},           # angefordert um …
    'zeiten': {'notruf': …, 'alarm': …, 'eintreffen': …},
    'bilanz': None,                       # beim Abschluss gefüllt
}
```

- `progress` bleibt und wird **abgeleitet** (Anteil erledigter Pflicht-Maßnahmen in %). Heutige Anzeigen,
  Abschnitte und die Auto-Schließung bei 100 % funktionieren weiter.
- `working` = „mindestens eine Maßnahme gestartet“.
- Dauer und Ende werden **beim Start festgelegt** (Wetterfaktor, KdoW-Bonus), wie bei den Fahrten
  (`_start_trip`: „Ankunftszeit steht ab jetzt fest“).
- Alles hängt an `now`, deshalb lässt es sich wie `tests/test_spiellogik.py` ohne echte Zeit testen.

**Haken in `game/engine.py`:**

| Stelle | Änderung |
|---|---|
| `new_incident` | `massnahmen.init_einsatz(inc, now)`, wenn das Stichwort im Katalog ist |
| `alarm` | `zeiten['alarm']` setzen (erste Alarmierung) |
| `update` | für Katalog-Einsätze `massnahmen.tick(r, inc, now)` statt `_progress_incident` |
| `ai_group_leaders` | für Katalog-Einsätze `massnahmen.ki_waehlen(…)` statt `working = True` |
| `_finish_incident` | `inc['bilanz'] = massnahmen.bilanz(inc, now)` + Funkzeile |
| `_snapshot_incident` / `snapshot` | `massnahmen.snapshot_massnahmen(inc, vehicles, now)`, Schwierigkeit |

### 7.4 Neue `/api`-Aktionen (in `ACTIONS`)

| Aktion | Wer | Daten | Fehlermeldungen (Beispiele) |
|---|---|---|---|
| `massnahme` | GF vor Ort | `incident`, `key` | „🔒 Erst muss das Feuer aus sein“, „Kein freier Trupp“, „Nur LF 20 oder HLF 20“, „Läuft bereits“ |
| `massnahme_stop` | GF, der sie gestartet hat | `incident`, `key` | „Maßnahme läuft nicht“ |
| `nachforderung` | GF vor Ort | `incident`, `kind` (`HLF 20`/`LF 20`/`KdoW`) | „Unbekannter Fahrzeugtyp“ |
| `dienst` | Leitstelle | `incident`, `dienst` (`RTW`/`Polizei`/`Netzbetreiber`) | „Bereits angefordert“ |
| `settings` `kind=schwierigkeit` | Raumverwaltung | `level` (`uebung`/`normal`/`profi`) | „Schwierigkeit ungültig“ |

`work` bleibt für Einsätze ohne Katalog (Allgemein-Ablauf).

**Snapshot je offenem Katalog-Einsatz** (Server rechnet, Client zeigt nur an, wie heute):

```json
{"stichwort": "F2", "stichwort_start": "F1", "stufe": 2,
 "lage": {"brand": 52, "brand_trend": "sinkt", "tank": 12, "wasser": false, "personen": []},
 "variante": "Gartenhütte",
 "massnahmen": [
   {"key": "angriff", "name": "Angriffsleitung legen & löschen", "status": "laeuft",
    "fz": "WB-2-LF20", "trupp": 1, "start": 1010.0, "ende": 1025.0, "pflicht": true},
   {"key": "wasser", "name": "Wasserversorgung aufbauen", "status": "frei", "dauer": 30,
    "hinweis": "⚠️ ohne Wasserversorgung: Tank 40 s"},
   {"key": "nachloeschen", "status": "gesperrt", "hinweis": "🔒 Erst muss das Feuer aus sein"}],
 "warnungen": [{"text": "Tank halb leer – Wasserversorgung?", "bis": 1072.0}],
 "nachforderungen": [{"kind": "HLF 20", "erfuellt": true}], "tipp": "wasser"}
```

`variante` steht erst nach *Erkunden* im Snapshot. Sonst könnte man in den Entwicklertools schummeln.

**Frontend-Hinweis:** Countdowns und Balken nicht über neues Markup bei jedem Poll, sondern mit
`data-start`/`data-ende` und einem kleinen Ticker (wie `animateVehicles`, mit `serverNow()`). Dann bleibt
`updateIncidents` stabil, und Buttons flackern auf dem Handy nicht.

### 7.5 Tests (`tests/test_massnahmen.py`)

- **Katalog-Konsistenz:** Alle Voraussetzungen zeigen auf vorhandene Schlüssel, es gibt keine Zyklen, und jede
  Pflicht-Maßnahme ist erreichbar.
- **Lösbarkeit:** Für jedes Stichwort spielt die perfekte KI mit **einem einzigen HLF 20** bis zum Ende,
  ohne Stufe 3 (bei Normal). So bleibt jeder Einsatz auch mit 1 Spieler lösbar.
- **F1 ideal:** Erkunden → Angriff + Wasser parallel → Nachlöschen → abgeschlossen, Stufe 0, ★★★.
- **E1:** Angriff mit HLF ohne Wasser → nach 16 s Warnung, nach 32 s „Wasser aus“, Löschen pausiert.
- **E2:** Brand erreicht 40 → Stichwort `F2`, Nachforderung, neue Maßnahmen im Katalog-Zustand.
- **Harte Voraussetzung:** `massnahme` `nachloeschen` bei Brand > 0 → `ValueError` mit deutscher Meldung.
- **Fahrzeugtyp/Trupps:** KdoW darf keine Wasserversorgung; 4. Maßnahme bei 3 Trupps → „Kein freier Trupp“.
- **Wetter:** Bei Regen dauert *Wasserversorgung* 30 / 0,85 s.
- **KI:** gleicher Einsatz-`id` → gleiche Entscheidungen; Übung = Musterreihenfolge; KI fängt Warnungen ein.
- **Snapshot:** keine `variante` vor Erkunden; Größe pro Einsatz < 3 KB.
- **Altbestand:** Freitext-Stichwort und `work` laufen wie bisher (bestehende Tests bleiben grün).
- **Übung:** keine Folgen trotz abgelaufener Timer.

### 7.6 PR-Schritte

| PR | Inhalt | Aufwand | Danach spielbar |
|---|---|---|---|
| **A · F1 spielbar** | `katalog.py` nur mit F1 (4 Maßnahmen), `massnahmen.py` mit Trupps, harten/weichen Voraussetzungen, Brand + Tank, E1 (Wasser aus) und E2 (F1 → F2 als Funk + Stichwort-Anzeige, ohne neue F2-Maßnahmen). Aktion `massnahme`, KI-GF nach Musterreihenfolge (noch fehlerfrei), Panel „Meine Einsatzstelle“, einfache Bilanz-Funkzeile („F1 in 1:32, 0 Eskalationen“). Alle anderen Stichworte laufen wie heute. Tests. | **M** | F1 mit echten Entscheidungen |
| **B · Brände & Eskalationsrahmen** | F2 und F3 Y, Personen-Countdown, Atemschutz-Regeln, E2–E5 vollständig, Stichworterhöhung mit Maßnahmen-Nachladen, Nachforderungen + Leitstellen-Karte, Abschnitts-Fortschritt, `massnahme_stop`. | **M** | Wohnungsbrände mit Menschenrettung |
| **C · TH, BMA, ABC** | TH1, TH2, BMA, ABC1, Varianten über Erkunden, virtuelle Dienste (RTW/Polizei/Netzbetreiber), E6–E12, AAO-Vorschlag, KI-Leitstelle erfüllt Nachforderungen. | **L** | Alle 7 Stichworte |
| **D · Wertung & Schwierigkeit** | Punkte + Sterne + Bilanzkarte, Schwierigkeitsstufen (Raumeinstellung), Tipps, KI-Fehlerquote, Fallen im Profi-Modus. | **M** | Spielziel und Einstieg für Anfänger |

**Abstimmung mit parallelen Arbeiten:**
- `game/engine.py` wird gerade von mehreren Sessions geändert (#16 KI-Leitstelle, #17 Straßenrouten,
  KI-Einsatzrate, Fahrzeuge auf der Karte). Deshalb steckt die Logik in eigenen Dateien. PR A erst nach dem Merge
  von #16/#17 von `main` abzweigen.
- Neue KI-Stichworte (Session „KI-Einsatzrate“) sollten das Titelformat `KÜRZEL · Text` behalten. Dann
  greifen sie automatisch, sobald es einen Katalogeintrag gibt, und bis dahin läuft der Allgemein-Ablauf.
- Mit #17 hängen die Fahrzeiten von der Route ab. Personen- und Brand-Timer laufen ab Notruf, die Richtzeiten
  in der Bilanz rechnen deshalb mit der tatsächlichen Eintreffzeit (`zeiten['eintreffen']`).

### 7.7 Stand nach PR A und Vorausschau: mehr Fahrzeugtypen, größere Einsätze

**Umgesetzt in PR A** (Abweichungen zum Plan oben): Logik in `game/massnahmen.py`, Daten in `game/katalog.py`.
Fahrzeuge werden dort über **Fähigkeiten** beschrieben (`FAHRZEUGTYPEN`), Maßnahmen verlangen Fähigkeiten
(`braucht`) statt Typnamen. Der ganze Zustand steht in `inc['mn']` (JSON, Zufall aus Einsatz-ID + Zähler).
Die Eskalation F1 → F2 ändert Titel und Stichwort, setzt eine Nachforderung nach F2-AAO, die KI-Leitstelle
erfüllt sie nach 10 s (auch mit KI-Besatzung, Frage 4). Bilanz mit Punkten und Sternen kommt schon in PR A
(Frage 5: nur im Raum). Schwierigkeit fest auf *Normal* (KI-Fehlerquote 15 %), Einstellung folgt in PR D.

**Neue Fahrzeugtypen brauchen nur Daten** – drei Stellen, keine neue Logik:

| Typ | Fähigkeiten (`katalog.FAHRZEUGTYPEN`) | Sitze → Trupps | Wache (Vorschlag) | Wofür |
|---|---|---|---|---|
| **TLF 3000** | `erkunden`, `pumpe`, `loeschwasser` · Tank 3000 l = 60 s | 3 → 1 | WB 1 West, WB 4 Ost (Ortsrand, wenig Hydranten) | Wasser für F1/F2 ohne Hydrant, Flächen-/Waldbrand, Wasser-Pendel |
| **DLK 23-12** | `erkunden`, neu `hubrettung` | 3 → 1 | WB 2 Altstadt | F3 Y: Rettung aus 2. OG, Riegelstellung/Brandbekämpfung von oben |
| **RW** | `erkunden`, `rettungssatz`, neu `heben`, `strom` | 3 → 1 | WB 5 Süd (Werkstraße/Gewerbe) | TH2 schwer (LKW, Bus), Fahrzeug anheben, Ausleuchten |
| **ELW 1** | `erkunden`, `einsatzleitung` | 3 → 1 | WB 2 Altstadt | wie KdoW, ab F3/TH3 Pflicht: „Einsatzleitung übernehmen“, Abschnitte |

1. `game/engine.py`: `FLEET` je Wache um die Typen ergänzen (heute fest `HLF 20`, `KdoW`, `LF 20` für WB 1–6) –
   eine Liste `(wache, typ, sitze)` statt der festen Dreierschleife. Raum-IDs bleiben `WB-<wache>-<typ ohne Leerzeichen>`.
2. `game/katalog.py`: Eintrag in `FAHRZEUGTYPEN`, neue Fähigkeiten in `FAEHIGKEIT_TEXT`, Maßnahmen, die sie
   verlangen (z. B. F3 Y „Rettung über Drehleiter“ `braucht: (HUBRETTUNG,)`).
3. **Grafiken:** `static/img/fahrzeuge/tlf.svg`, `dlk.svg`, `rw.svg`, `elw.svg` im Stil von #19 (Draufsicht,
   gleiche Größe wie `lf.svg`; DLK etwas länger mit Leiterpark), dazu je eine Zeile in `css/fahrzeuge.css` und
   `TYPES` in `static/js/fahrzeuge.js` (`TLF: 'tlf'`, `DLK: 'dlk'`, `RW: 'rw'`, `ELW: 'elw'`).

**Größere Einsätze = mehr Fahrzeuge:** Je Katalog-Stichwort gibt es schon eine `aao`-Liste. Ab PR B ersetzt
sie für Katalog-Einsätze die Zählung aus der Stichwortziffer (`needed_vehicles`): Die KI-Leitstelle und der
AAO-Vorschlag alarmieren dann genau diese Typen. Vorschlag:

| Stichwort | AAO | Eskalation → Nachforderung |
|---|---|---|
| F1 | LF 20 | → F2: HLF 20, KdoW (heute schon so) |
| F1 Wald/Fläche (neu, PR C) | LF 20, TLF 3000 | → F2 Wald: 2. TLF, ELW 1 |
| F2 | HLF 20, LF 20, KdoW | → F3 Y: HLF 20, DLK, ELW 1 |
| F3 Y | 2 HLF 20, LF 20, DLK, ELW 1 | → F4 (Vollbrand): TLF, 2. LF, Nachbarwache |
| TH2 | HLF 20, LF 20, KdoW | schwer (LKW): RW nachfordern |

Damit wächst ein Einsatz von selbst mit: F1 → F2 → F3 bringt nacheinander HLF, KdoW, DLK und ELW auf die
Karte, und jeder Typ hat dort eine Maßnahme, die nur er kann. **Reihenfolge:** PR B nimmt DLK + ELW mit
(F2/F3 Y), PR C TLF + RW (Wald/Fläche, schwere TH). Vorher braucht es nur die vier Grafiken.

---

## 8. Offene Fragen an Lars

| # | Frage | Meine Empfehlung |
|---|---|---|
| 1 | **Welche Schwierigkeit für neue Räume?** | **Normal.** Eskalation mit Warnung ist der Kern des Spaßes. Übung für Neue, das stellt die Raumverwaltung um. |
| 2 | **Dürfen Personen im Spiel sterben?** | **Nein, höchstens „schwer verletzt“.** Die Folge ist spürbar (−30 Punkte, 🔴), aber der Ton bleibt Planspiel. |
| 3 | **F1: Soll Wasserversorgung Pflicht sein, oder darf man kleine Brände realistisch nur mit Tankwasser löschen?** | **Nicht Pflicht, sondern eine Entscheidung.** Mülltonne geht mit Tankwasser, Gartenhütte nicht. *Erkunden* zeigt es. So entsteht genau Lars' „falsche Reihenfolge eskaliert“, ohne starre Pflicht. |
| 4 | **Nachforderungen im Mehrspielerbetrieb:** Heute dürfen dort nur besetzte Fahrzeuge alarmiert werden (offen in #16). Bei TH2 ohne HLF-Spieler wäre der Einsatz dann nicht lösbar. Dürfen **Nachforderungen** mit KI-Besatzung fahren? | **Ja, für Nachforderungen und AAO-Fahrzeuge mit KI-Besatzung.** Die KI-GF arbeitet dann nach Musterreihenfolge mit. Sonst brauchen F3 Y/TH2 vier Spieler. |
| 5 | **Wo wird die Wertung gespeichert?** Nur im Raum (weg nach Neustart) oder je Konto mit Statistik/Bestenliste? | **Erst nur im Raum** (PR D). Eine Speicherung je Konto später als Opt-in, weil sie Datenschutzerklärung und Datenexport betrifft. |

---

*Konzept: Claude Code für Lars, 27.11.2026. Grundlage: `game/engine.py`, `static/js/game.js` und
`templates/index.html` auf `main` @ 9333e11; FwDV 3 (Einheiten im Lösch- und Hilfeleistungseinsatz) und
FwDV 7 (Atemschutz), spielbar vereinfacht.*
