# Implementierung — Materialsammlung für den Implementierungsteil der Bachelorarbeit

Arbeitsdokument. Sammelt stichpunktartig, **was** implementiert wurde, schlägt eine
**Gliederung** für das Kapitel vor, benennt die **Begründungsmuster** und markiert,
**wo Quellen gebraucht werden**.

Detaillierte Chronologie: `CHANGELOG.md` · Offene Punkte: `TODO_DeepSearch.md`
· Anforderungsbezug: `Checklist.md`

---

## Teil A — Was implementiert wurde

### A.0 Ausgangslage

- Vergleichsbasis ist das textbasierte SWORDS-Werkzeug (`cli.py`,
  `config_parsers/cpp_test_config_parser.py`): reguläre Ausdrücke auf CMake-Dateien,
  zeilenweise, Erkennung über `ADD_TEST_REGEX`, `GTEST_DISCOVER_REGEX`,
  `FIND_PACKAGE_REGEX`.
- Eigenes Werkzeug: `cli2.py` + Paket `treesitter_detector/` (2.882 Zeilen,
  16 Module), 96 Unit-Tests.
- Datensatz: 206 JOSS-Repositories mit C++-Tag (`foo/dataset_index.csv`).

### A.1 Syntaktische Ebene — Tree-sitter statt Regex, gleiche Heuristik

*Zweck: die syntaktischen Vorteile isoliert nachweisen.*

- Umstellung auf die **Query-API** (`Query`/`QueryCursor`) statt manuellem
  Baumdurchlauf mit Typ-Substring-Heuristiken.
  - CMake: `(normal_command (identifier) @name (argument_list (argument)* @arg)?)`
  - C++: zwei Makroformen (`function_definition` für `TEST(...){...}`,
    `call_expression` für `TEST_CASE(...)`) plus `preproc_include`
- Grammatik-Anbindung vereinheitlicht (`tree_sitter_backend.py`), Query-Cache.
- **Dabei gefundene Fehler der Vorgängerfassung** (alle mit Regressionstest):
  - `if(...)`/`endif()` wurden als Kommandos gezählt (Substring-Match `"command" in type`)
  - Quotierte Argumente mit Leerzeichen wurden am Leerzeichen zerlegt
  - `find_package(Catch2)` setzte fälschlich `uses_gtest`
  - `find_package(GTest)` allein setzte fälschlich `tests_found`/`gtests_found`
  - `assert` stand in `GENERIC_TEST_MACROS` (kein Test-Framework-Makro)
- **Heuristik-Angleichung an die Baseline**, damit der Vergleich nur die
  Parsing-Technologie misst (4 Punkte: `uses_gtest` nicht aus
  `gtest_discover_tests`; `enable_testing()` allein zählt nicht;
  `find_package` nur erstes Argument; `has_cmakelists`-Definition angeglichen).
- **Ergebnis:** 14 Abweichungszeilen (4 inhaltlich) über 206 Repos.

### A.2 Refactoring (Zwischenschritt)

- Toter Code entfernt, dreifach vorhandene Helfer zusammengeführt,
  Modulnamen begradigt (`detector.py` → `cmake_parser.py` u. a.).
- **Verifikationsprinzip etabliert:** spaltenweiser CSV-Vergleich über alle 206 Repos;
  Anforderung „0 Abweichungen" als Nachweis, dass sich die Logik nicht geändert hat.
  Dieses Prinzip wird ab hier bei *jeder* Änderung angewandt.

### A.3 Semantische Ebene — Tiefensuche durch den Baum

*Zweck: die semantischen Vorteile erarbeiten. Schwerpunkt der Arbeit.*

| Stufe | Was | Kernergebnis |
|---|---|---|
| 0 | `--cmake-only` | 97 % der Parsingzeit entfiel auf C++; Laufzeit 8 → 4 min |
| 1 | Erreichbarkeit (`cmake_graph.py`) | nur **70 %** der CMake-Dateien sind ab Root erreichbar |
| 2 | Wrapper-Argumentbindung (`cmake_semantics.py`) | 7.877 Registrierungen rekonstruiert |
| 3 | `foreach`-Bindung | 4.815 verschiedene Testnamen |
| 4 | Target-Verknüpfung | 1.666 Tests mit Target, **1.062 Testquelldateien** |
| 5 | Treiber-Klassifikation | 1.666 in scope / 1.627 out of scope |
| 6 | Bedingungskontext | **65 %** der Registrierungen sind bedingt |

**Stufe 1 — Auswertungsreihenfolge.** Graph ab Root-`CMakeLists.txt` über
`add_subdirectory`, `include`, `find_package`; `.in`-Dateien als Templates;
implizite `CTestConfig.cmake`/`CPackConfig.cmake`. Konservativ: unauflösbare
Direktiven kürzen nicht, sondern halten die unmittelbaren Unterverzeichnisse
erreichbar.

**Stufe 2 — Bindung.** Parameter der Definition werden an die Argumente der
Aufrufstelle gebunden; `${ARGN}`/`${ARGV0..n}`/`${ARGC}`; `set()` im Rumpf erweitert
die Bindung in Quelltextreihenfolge. Fixpunkt-Iteration mit Tiefenbegrenzung gegen
(gegenseitige) Rekursion.

**Stufe 3 — Schleifen.** `foreach` literal, über `set()`, `IN LISTS`, `IN ITEMS`,
`RANGE`; verschachtelt als Kreuzprodukt. Unbestimmbare Liste wird als
`indeterminate_count` markiert, **nicht** geraten.

**Stufe 4 — Targets.** `add_executable` wird im selben Expansionslauf erfasst (weil
Targets oft erst im Wrapper entstehen), danach `add_test(COMMAND …)` → Target →
Quelldateien. `$<TARGET_FILE:…>` und Pfadreferenzen (`${CMAKE_BINARY_DIR}/x`) werden
aufgelöst.

**Stufe 5 — Treiber.** `repo_target` / `external_tool` / `unresolved`. Erkennung über
CMake-**Konventionen** statt Namenslisten: `${<Pkg>_EXECUTABLE}` (find_package-Konvention),
`${CMAKE_COMMAND}`, `Namespace::Target` (importiertes Target). Setzt die
`out of scope`-Markierung aus Konzeption §4.4 um.

**Stufe 6 — Bedingungen.** `if`/`elseif`/`else`-Zweige; verschachtelte Bedingungen
verknüpft; Bedingung wird mit der Wrapper-Bindung expandiert. Bedingungen werden
**erfasst, nicht ausgewertet**.

### A.4 Ausgabe und Vergleich

- **Test-Inventar** (`inventory.py`, `--inventory-out`): JSON Lines, eine Zeile je
  Repo, 4,0 MB. Pro Registrierung: Name (roh + aufgelöst), Wrapper-Kette,
  Definitions- und Aufrufort, Target, Quelldateien, Treiber, Bedingung.
- **Zwei Vergleichsskripte** (gemeinsame Mechanik in `comparison.py`):
  - `comp_rgx_ts.py` — strenge Parität (syntaktische Ebene)
  - `comp_rgx_ts_deep.py` — volle Fähigkeit, zwei Stufen (semantische Ebene)

### A.5 Methodisch relevante Nebenbefunde

Diese sind **eigenständige Ergebnisse** und gehören in die Arbeit:

1. **Syntaxfehler verschlucken Kommandos.** 57 Dateien in 46 Repos parsen mit
   ERROR-Knoten. Bei Repo 1848 (Chaste) macht korrupter Quelltext in Zeile 608
   rund 580 Folgezeilen für die Query unsichtbar — Tree-sitter liest sie als
   Bracket-Argument. → Fehlertoleranz heißt „der Parser stürzt nicht ab", **nicht**
   „alles bleibt analysierbar".
2. **Reproduzierbarkeit.** Die Analyse war zwischenzeitlich nicht deterministisch
   (Iteration über ein `set` bei mehrdeutigen Dateinamen). Behoben; mit
   `PYTHONHASHSEED` 0/1/42/12345 verifiziert.
3. **Zahlen sind Obergrenzen.** Repo 2260 (ginkgo): 8 textuelle `add_test`-Vorkommen,
   1.369 rekonstruierte Registrierungen — 4 Backends hinter `if(GINKGO_BUILD_*)`.
4. **Ein belegbarer False Positive beider flacher Verfahren** (Repo 7881): Die
   einzigen `add_test`-Vorkommen stehen in einem String-Literal und in einer nie
   aufgerufenen Funktion, beide in eingebundenem Fremdcode.

---

## Teil B — Gliederungsvorschlag für das Implementierungskapitel

Die Reihenfolge folgt der Argumentation, nicht der Chronologie.

```
5 Implementierung
  5.1 Überblick und Architektur
      - Zweischichtung: syntaktischer Pass (pro Datei) / semantischer Pass (repo-weit)
      - Modulübersicht, Datenfluss, Abgrenzung zur Baseline
  5.2 Syntaktische Ebene
      5.2.1 Grammatik-Anbindung und Query-Sprache
      5.2.2 Extraktion: Kommandos, Definitionen, Schleifen, Bedingungen
      5.2.3 Angleichung an die Baseline-Heuristik  <- begründet den fairen Vergleich
  5.3 Semantische Ebene (Kern des Kapitels)
      5.3.1 Auswertungsreihenfolge und Erreichbarkeit
      5.3.2 Namensauflösung: Wrapper-Definitionen und Argumentbindung
      5.3.3 Schleifen und Mengenauflösung
      5.3.4 Target-Verknüpfung: von der Registrierung zur Quelldatei
      5.3.5 Klassifikation des Testtreibers
      5.3.6 Bedingungskontext
  5.4 Ergebnisrepräsentation
      - Test-Inventar, Datenmodell, warum roh + aufgelöst
  5.5 Qualitätssicherung
      - Teststrategie, Regressionsschutz über den Datensatz, Determinismus
  5.6 Grenzen der Implementierung
```

**Warum diese Reihenfolge:** 5.2 etabliert, dass gleiche Heuristik + besserer Parser
bereits etwas bringt (kleiner, sauber messbarer Effekt). 5.3 baut darauf auf und
zeigt, was *nur* mit AST geht. 5.5 und 5.6 sichern die Aussagen ab.

**Faustregel je Unterabschnitt:** (1) Welches Problem im realen CMake-Code?
(2) Warum kann die Regex das prinzipiell nicht? (3) Wie löst es der AST-Ansatz?
(4) Was hat es im Datensatz gebracht? (5) Wo ist die Grenze?

---

## Teil C — Begründungsmuster

### C.1 Das Kernargument sauber schichten

Die Arbeit sollte **zwei Ebenen trennen** und nicht in einer Zahl vermischen:

| Ebene | Frage | Befund |
|---|---|---|
| syntaktisch | Parst der AST besser als die Regex bei *gleicher* Heuristik? | 14 Abweichungen, 4 inhaltlich |
| semantisch | Was kann der AST-Ansatz, was die Regex prinzipiell nicht kann? | Tiefensuche, Stufen 1–6 |

Ehrlich mitzuteilen: Auf der syntaktischen Ebene gewinnt der AST-Ansatz im strengen
Vergleich **keinen** Fall (4 FN gegen 0). Erst mit den semantischen Fähigkeiten dreht
sich das Bild (Level 2: 149 zu 2). Genau diese Schichtung macht die Aussage stark,
weil sie den Effekt der Technologie vom Effekt erweiterter Heuristiken trennt.

### C.2 Wiederkehrende Begründungsfiguren

- **Definition vs. Aufrufstelle.** Eine Regex kann nicht unterscheiden, ob
  `add_test` in einer Definition oder an einer ausgeführten Stelle steht. Beleg:
  Repo 7881.
- **Namensbindung braucht Kontext.** 74 % der `add_test`-Aufrufe enthalten Variablen.
  Deren Wert hängt von der Aufrufstelle ab — eine lexikalische Analyse hat keinen
  Begriff von „Aufrufstelle".
- **Struktur schlägt Textnähe.** Substring-Match trifft `ExternalData_add_test`;
  ein Knotenvergleich nicht. Umgekehrt matcht die Regex in Kommentaren und
  String-Literalen, der AST nicht.
- **Konservativität als Entwurfsprinzip.** Wo etwas statisch unbestimmbar ist, wird
  *nicht* gekürzt und *nicht* geraten, sondern markiert (`indeterminate_count`,
  `unresolved_directives`, `driver = unresolved`). Das ist begründungspflichtig und
  begründbar: False Negatives wären für die Fragestellung teurer als
  Über-Approximation.
- **Messen statt vermuten.** Mehrfach wurde eine geplante Maßnahme durch eine Messung
  widerlegt, bevor sie gebaut wurde (naive `set()`-Auflösung: 0 zusätzliche Treffer).
  Das ist methodisch erzählenswert.

### C.3 Was man *nicht* behaupten sollte

- Nicht „der AST-Ansatz ist genauer" pauschal — im strengen Vergleich ist er es nicht.
- Nicht „Fehlertoleranz löst das Problem malformierter Dateien" — Befund A.5.1 zeigt
  das Gegenteil.
- Nicht die Registrierungszahlen als „Anzahl der Tests" — es sind Obergrenzen über
  alle Konfigurationen (Befund A.5.3).

---

## Teil D — Wo Quellen gebraucht werden

**Wichtig:** `literatur.bib` existiert im Repository noch **nicht**, obwohl
`Konzeption.tex` sie via `\bibliography{literatur}` einbindet. Muss angelegt werden.

Bereits in der Konzeption verwendete Schlüssel: `Aho_Lam_Sethi_Ullman_2007`,
`Comparison_Parsers`, `General_Purpose_Static_Ana_Test`, `manning2008introduction`,
`Nunamaker_Chen_1990`, `SAGitHub`, `srcML`, `SWORDS_template_UP_2024`, `treesitter`,
`Venable_Pries-Heje_Baskerville_2017`.

### D.1 Belegpflichtig im Implementierungsteil

| Stelle im Kapitel | Wofür ein Beleg nötig ist | Quellentyp |
|---|---|---|
| 5.1 Architektur | Trennung syntaktische/semantische Analyse als übliches Vorgehen | Lehrbuch statische Analyse |
| 5.2.1 | Tree-sitter, GLR, inkrementelles Parsen | `treesitter` (vorhanden), ggf. Primärquelle zu GLR |
| 5.2.1 | **Query-Sprache / S-Expression-Muster** | Tree-sitter-Doku — **fehlt noch** |
| 5.2.2 | Konkrete Knotentypen der Grammatiken | `tree-sitter-cmake` / `tree-sitter-cpp` Repos — **fehlt noch** |
| 5.3.1 | **CMake-Auswertungsmodell**: `include`, `add_subdirectory`, `CMAKE_MODULE_PATH` | Offizielle CMake-Doku — **fehlt noch** |
| 5.3.2 | **CMake-Variablen- und Scope-Semantik**, Unterschied `macro` vs. `function`, `ARGN`/`ARGV` | Offizielle CMake-Doku — **fehlt noch** |
| 5.3.1/5.3.2 | **Fixpunkt-Iteration, Erreichbarkeitsanalyse, Call-Graph** | Lehrbuch Programmanalyse — **fehlt noch** |
| 5.3.x | **Over-Approximation / Soundness vs. Completeness** als Entwurfsentscheidung | Lehrbuch Programmanalyse — **fehlt noch** |
| 5.5 | **Differential Testing** als Evaluationsmethode | Methodenquelle — **fehlt noch** |
| 5.5 | Precision/Recall | `manning2008introduction` (vorhanden) |
| 5.5 | **Reproduzierbarkeit empirischer SE-Studien** (Determinismus-Befund) | Methodenquelle — **fehlt noch** |
| 5.6 | Grenzen statischer Analyse ohne Build-Umgebung | Lehrbuch / Studie zu Build-Systemen — **fehlt noch** |

### D.2 Konkrete Kandidaten (bibliographische Angaben selbst prüfen)

- **Programmanalyse, Fixpunkt, Datenfluss:** Nielson/Nielson/Hankin, *Principles of
  Program Analysis* — Standardwerk für Fixpunkt-Iteration und Over-Approximation.
  Alternativ die entsprechenden Kapitel in `Aho_Lam_Sethi_Ullman_2007` (bereits zitiert).
- **Differential Testing:** McKeeman, *Differential Testing for Software* (Digital
  Technical Journal, 1998) — die übliche Referenz für das Verfahren.
- **CMake:** offizielle Dokumentation (`cmake.org/cmake/help/latest`), namentlich die
  Seiten zu `add_test`, `add_subdirectory`, `include`, `macro`, `function`,
  `foreach`, `cmake-language(7)`, `cmake-variables(7)`. Version mitangeben.
- **Tree-sitter:** Projektdokumentation zur Query-Syntax und zur Fehlerbehandlung
  (`ERROR`/`MISSING`-Knoten) — relevant für Befund A.5.1.
- **Build-System-Forschung:** Für die Aussage „CMake-Projekte nutzen verbreitet
  Wrapper-Makros" wäre eine empirische Studie zu Build-Systemen wünschenswert;
  notfalls durch die **eigenen** Messungen belegen (33 Repos mit In-Repo-Wrappern,
  135 Wrapper-Namen) und als eigenen Beitrag ausweisen.

### D.3 Wo eigene Messungen den Beleg ersetzen

Diese Aussagen sind durch eigene Daten belegt und brauchen **keine** Fremdquelle —
sollten aber klar als eigene Erhebung gekennzeichnet werden: alle Zahlen in Teil E.

---

## Teil E — Zahlen zum Zitieren

Alle über die 206 Repos in `bar/` erhoben. Reproduzierbar über
`testing-artifact-detector-ts … --cmake-only --inventory-out …`.

### E.1 Datensatz und Ausgangslage

| Kennzahl | Wert |
|---|---|
| Repositories | 206 (davon 205 klonbar) |
| CMake-Dateien gesamt | 4.571 |
| Repos mit Testregistrierung | 76 |
| `add_test`-Aufrufe (textuell) | 891 |
| davon mit Variablen im Argument | 656 (74 %) |
| `COMMAND` direkt auf Target auflösbar (vorher) | 290 / 885 |
| zusätzlich per naiver `set()`-Auflösung | **0** |

### E.2 Vergleich Baseline ↔ AST

| Vergleich | Abweichungen gesamt | inhaltlich | nur Baseline | nur Tree-sitter |
|---|---|---|---|---|
| streng (gleiche Heuristik) | 14 | 4 | 4 | 0 |
| Level 1 (Deep CMake) | 20 | 10 | 4 | 6 |
| Level 2 (Deep + C++) | 161 | 151 | 2 | 149 |

### E.3 Ergebnisse der Tiefensuche

| Kennzahl | Wert |
|---|---|
| erreichbare CMake-Dateien | 70 % (3.281 / 4.571) |
| Dateien mit Syntaxfehlern | 57 in 46 Repos |
| rekonstruierte Testregistrierungen | 7.877 |
| verschiedene Testnamen | 4.815 |
| identifizierte Testquelldateien | 1.062 |
| Treiber `repo_target` (in scope) | 1.666 (21,2 %) |
| Treiber `external_tool` (out of scope) | 1.627 (20,7 %) |
| Treiber `unresolved` | 4.584 (58,2 %) |
| bedingt registriert | 5.116 (65 %) |
| verschiedene Bedingungen | 1.404 |
| In-Repo-Wrapper aufgelöst | 33 Repos, 135 Namen |
| Wrapper definiert, nie aufgerufen | 8 Repos |

### E.4 Fallstudien-Repos

| ID | Projekt | wofür |
|---|---|---|
| 7881 | cadet/CADET-Core | False Positive beider flacher Verfahren |
| 2352 | STEllAR-GROUP/hpx | 9 Textvorkommen → 2.355 verschiedene Testnamen |
| 2260 | ginkgo-project/ginkgo | Registrierungszahl als Obergrenze (4 Backends) |
| 1848 | Chaste/Chaste | Syntaxfehler verschluckt 580 Zeilen |
| 1371 | artivis/manif | saubere Wrapper-Kette, vollständig aufgelöst |
| 153 / 3959 | SlicerITKUltrasound / dune-mmesh | extern definierte Wrapper (Grenze) |

---

## Teil F — Grenzen (gehören explizit ins Kapitel)

- **Keine Build-Umgebung.** Extern definierte Wrapper (`dune_add_test`,
  `ExternalData_add_test`) sind unauflösbar → Konzeption §3.5.
- **Keine Scope-Simulation.** `set()` in Eltern-Scopes (`PARENT_SCOPE`) wird nicht
  nachgebildet; das erklärt den Großteil der 58 % `unresolved`.
- **Bedingungen werden nicht ausgewertet**, nur erfasst — ob `BUILD_TESTING` an ist,
  ist eine Eigenschaft der Konfiguration, nicht des Quelltexts.
- **`else` wird als `"else"` geführt**, nicht als Negation der Vorbedingungen.
- **Kein Katalog externer Wrapper-Namen** — bewusst, weil das die Namensheuristik
  wäre, die der Baseline vorgeworfen wird.
- **Schleifenexpansion begrenzt** (`MAX_LOOP_ITERATIONS = 64`,
  `MAX_EXPANSION_DEPTH = 8`).
- **`.cmake.in`-Templates** werden nicht ausgewertet.
