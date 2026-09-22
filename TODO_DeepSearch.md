# TODO — Tiefensuche im CMake-AST

Arbeitsdokument für den Ausbau der semantischen CMake-Analyse.

## Kontext

Rückmeldung des Betreuers zum Stand nach CHANGELOG §1–§9:

- Der **starre Vergleich** (Tree-sitter statt Regex, identische Heuristik) ist gut und
  belegt die *syntaktischen* Vorteile — bleibt erhalten, ist aber nicht mehr der
  Schwerpunkt der Arbeit.
- Der Schwerpunkt liegt auf der **Tiefensuche durch den Baum**, weil dort die
  *semantischen* Vorteile der Technologie liegen. Das ist der eigentliche Beitrag.
- Die Arbeit konzentriert sich **auf CMake** — die Baseline-Implementierung deckt
  ebenfalls nur CMake ab.
- Die **C++-/Cross-Language-Korrelation** (Konzeption F03, §4.4) rückt in den
  Hintergrund und wird im Kapitel **Erweiterbarkeit** angeführt, nicht mehr als
  eigenes Evaluationsziel.

Ziel: die bestehende Wrapper-Auflösung (CHANGELOG §8) zu einer echten semantischen
Analyse ausbauen, die CMakes Auswertungsmodell nachbildet, und deren Ergebnis ein
**strukturiertes Test-Inventar** statt einer Ja/Nein-Spalte ist.

---

## Ausgangsmessung (Referenzwerte)

Erhoben per read-only Scan über alle 206 Repos in `bar/`. Gegen diese Zahlen wird der
Fortschritt gemessen — bei jeder Stufe die zugehörige Messgröße erneut erheben.

| Kennzahl | Ausgangswert |
|---|---|
| Repos mit Testregistrierung | 76 |
| `add_test`-Aufrufe gesamt | 891 |
| davon mit Variablen im Argument | **656 (74 %)** |
| `add_test` `COMMAND` direkt auf `add_executable`-Target auflösbar | **290 / 885** |
| zusätzlich per naiver `set()`-Auflösung auflösbar | **0** |
| `gtest_discover_tests`-Aufrufe | 74 (davon 40 direkt auf Target auflösbar) |
| CMake-Dateien erreichbar ab Root-`CMakeLists.txt` | **36 %** (1223 / 3357) |
| Repos mit `include()` / `add_subdirectory()` | 72 / 69 |
| Repos mit aufgelöstem Test-Wrapper (Stand §8) | 33 (135 Wrapper-Namen) |
| Repos mit nie aufgerufenem Test-Wrapper | 8 |

### Schlüsselbefund: warum `set()`-Auflösung nichts bringt

Die naive repo-weite `set()`-Auflösung liefert **0** zusätzliche Treffer. Die
Variablen in `add_test`-Argumenten zerfallen in drei Klassen, die je einen eigenen
Mechanismus brauchen:

| Klasse | Beispiele (Häufigkeit) | Mechanismus | Stufe |
|---|---|---|---|
| Schleifenvariablen | `${test_file}` (19×), `${test}` (4×), `${target}` | `foreach`-Bindung | 3 |
| Built-ins / Fremdwerkzeuge | `${EXECUTABLE_OUTPUT_PATH}` (17×), `${CMAKE_CURRENT_BINARY_DIR}` (8×), `${CMAKE_COMMAND}` (5×), `${Python3_EXECUTABLE}`, `${MPIEXEC_EXECUTABLE}` | klassifizieren, nicht auflösen | 5 |
| Wrapper-Parameter | `${cmd}` (6×), `${_cmd}`, `${_exe_name}`, `${NAME}` | Argumentbindung an der Aufrufstelle | 2 |

### Grammatik-Vorarbeit (bereits verifiziert)

- Variablenreferenzen sind **eigene Knoten**: `variable_ref → normal_var → variable`.
  Die Bindung kann strukturell statt per Regex erfolgen.
- `foreach_loop` → `foreach_command` (erstes Argument = Schleifenvariable, Rest = Liste)
  + `body` + `endforeach_command`.
- `if_condition` → `if_command` (argument_list = Bedingung) + `body` + `endif_command`.
- `macro_def`/`function_def` → `*_command` (erstes Argument = Name, Rest = Parameter)
  + `body`. **Achtung:** nur das *erste* Argument ist der Name — sonst tauchen
  Parameter als vermeintliche Wrapper auf (Fehler aus dem Vorab-Scan zu §8).

---

## Zielarchitektur

Der bestehende, pro Datei arbeitende syntaktische Pass bleibt; darüber kommt ein
repo-weiter semantischer Pass.

```
cmake_ast.py         (erweitern)  Knotenextraktion: Kommandos, Definitionen,
                                  NEU: Kontrollblöcke, Variablenreferenzen
cmake_graph.py       (neu)        Auswertungsreihenfolge: include / add_subdirectory /
                                  find_package-Graph ab Root-CMakeLists.txt
cmake_semantics.py   (neu)        Bindung (Wrapper-Argumente, foreach),
                                  Target-Verknüpfung, Klassifikation, Test-Inventar
cmake_results.py     (erweitern)  NEU: TestRegistration, ResolvedTarget, RepoTestInventory
cmake_parser.py      (anpassen)   ruft den semantischen Pass auf
```

---

## Stufe 0 — Vorbereitung ✅

- [x] `--cmake-only` in `cli2.py`: überspringt `analyse_cpp_repository`. Der C++-Code
      bleibt vollständig erhalten (Erweiterbarkeits-Kapitel). Die `cpp_*`-Spalten
      bleiben **leer statt `False`**, damit „nicht analysiert" von „analysiert, nichts
      gefunden" unterscheidbar bleibt.
      `collect_sources` läuft weiter mit (0,2 s auf 25 Repos), damit `cpp_files_found`
      korrekt bleibt.
- [x] Referenz-CSV für Regressionsvergleiche gesichert
      (`foo/treesitter_baseline_deep.csv`).

**Gemessene Zeitaufteilung** (25 Repos, 435 CMake- / 8.430 C++-Dateien):

| Phase | Stichprobe | hochgerechnet auf 206 Repos |
|---|---|---|
| CMake analysieren | 0,8 s | ~7 s |
| C++ analysieren | 25,5 s | ~210 s |
| cloc (Sprachanalyse) | 18,4 s | ~152 s |

→ **97 % der Parsing-Zeit entfällt auf C++.**

**Verifiziert am vollen Datensatz:**
- Laufzeit mit `--cmake-only`: **4 min 03 s** (vorher ~7–8 min)
- Alle **14 CMake-Spalten bit-identisch** zum Volllauf
- Alle C++-Spalten korrekt leer
- `testing-artifact-detector-compare` meldet weiterhin **14** Abweichungen, cloc-Sanity-Check 0

Nach `--cmake-only` ist **cloc mit ~152 s von 243 s der neue Engpass** (~63 %); die
CMake-Analyse selbst kostet ~7 s. Für Evaluationsläufe wird cloc gebraucht (der
Sanity-Check vergleicht `has_cpp`/`has_c`), für reine Entwicklungsiterationen nicht —
ein separater Schalter dafür wäre der nächste Hebel, falls nötig.

**Randnotiz:** Die bestehenden Flags `--assume-cloned`/`--clone-only` nutzen
`type=bool`, was in argparse nicht wie erwartet funktioniert (`--clone-only False`
ergibt `True`, weil `bool("False")` wahr ist). `--cmake-only` nutzt daher korrekt
`action="store_true"`. Die alten Flags wurden bewusst nicht angefasst — separate
Baustelle.

---

## Stufe 1 — Echte Erreichbarkeit (Fundament) ✅

Ersetzt die repo-weite Namens-Näherung in `resolve_test_wrappers`
(CHANGELOG §8: „ignoriert die CMake-Auswertungsreihenfolge").

- [x] `cmake_graph.py`: Graph ab Root-`CMakeLists.txt`
  - [x] `add_subdirectory(d)` → `d/CMakeLists.txt`
  - [x] `include(F)` → `F.cmake` (Pfad, blanker Modulname, und Pfad mit führender
        Variable über den Dateinamen)
  - [x] `find_package(X)` → `FindX.cmake` im Repo
  - [x] implizite `CTestConfig.cmake` / `CPackConfig.cmake` / `CTestCustom.cmake`
  - [x] `.in`-Dateien als Templates markiert — werden nie als CMake ausgewertet
  - [x] Nicht auflösbare Direktiven gezählt **und konservativ behandelt**
- [x] `resolve_test_wrappers` und `tests_found_reachable` auf den Graph umgestellt

**Ergebnis:** Erreichbarkeitsquote **70 %** (3188 erreichbar / 1285 unerreichbar /
98 Templates). `cmake_tests_found` über alle 206 Repos unverändert.
`tests_found` = 76, `tests_reachable` = **73**.

### Drei Implementierungsfehler, die erst die Datensatzprüfung aufgedeckt hat

1. **`Path.resolve()` vs. relative Pfade** — `resolve()` liefert absolute Pfade,
   während `collect_sources` relative liefert; die Kandidatenmenge traf nie.
   Repo 1371 fiel dadurch von 16/19 auf 2/19. Fix: `os.path.normpath` statt `resolve`.
2. **Behauptete, aber nicht implementierte Konservativität** — bei
   `add_subdirectory(${d})` wurde die Direktive zwar als „unaufgelöst" gezählt, die
   Unterverzeichnisse aber trotzdem abgeschnitten. Repo 3061 nutzt
   `SUBDIRLIST(...)` + `foreach(d ${SUBDIRS}) add_subdirectory(${d})` und verlor
   dadurch seine Tests. Fix: unaufgelöste Direktive → alle *unmittelbaren*
   Unterverzeichnisse bleiben erreichbar. Bewusst nur **eine Ebene**, sonst würde
   eine einzige unaufgelöste Direktive in der Root das ganze Repo inkl. Vendor-Bäume
   als erreichbar markieren (und den 7881-Fund zerstören).
3. **Willkürliche Root-Wahl** — bei Repos ohne Root-`CMakeLists.txt` (Repo 6548, eine
   Sammlung unabhängiger Teilprojekte) wurde die flachste Datei als Root gewählt und
   der Rest gekappt. Fix: kein Root → alle Dateien erreichbar (degradierter Modus).

### Neuer Befund: Syntaxfehler verschlucken Kommandos still

**57 CMake-Dateien in 46 Repos** parsen mit ERROR-Knoten. Das war bisher nirgends
ausgewertet — obwohl die Konzeption §2.3 Tree-sitters Fehlertoleranz als Vorteil
führt.

Fallbeispiel Repo **1848** (Chaste): Zeile 608 enthält korrupten Quelltext —
`"${VS_11_INCLUnstalled libvtk-java and libvtk5-qt4-devDES}"`, jemand hat Text in
eine Variablenreferenz hineinkopiert. Tree-sitters Fehlerbehandlung liest ab dort
**580 Zeilen als Bracket-Argument-Rohtext**, wodurch drei `add_subdirectory`-Aufrufe
(Zeilen 785/803/819) für die Query unsichtbar werden.

Konsequenz: Dateien mit Syntaxfehlern dürfen nicht zum Kürzen herangezogen werden —
ihre Kommandoliste ist nachweislich unvollständig. Umgesetzt über dieselbe
Ein-Ebenen-Expansion wie bei unaufgelösten Direktiven. Neue Spalte
`cmake_files_with_syntax_errors`.

### Verbleibende Abweichungen flach vs. erreichbar (3 Repos, alle verifiziert)

| Repo | Grund | Bewertung |
|---|---|---|
| 7881 | `add_test` nur in String-Literal + nie erreichter Funktion (Vendor-Catch2) | korrekter FP-Fund |
| 2645 | einziges `add_test` in eingechecktem `CTestTestfile.cmake` (Build-Ausgabe in Vendor-zlib) | korrekt gekappt |
| 1063 | ITK-External-Module: `examples/` wird von ITK-Infrastruktur außerhalb des Repos eingebunden | dokumentierte Grenze, wie 153/3959 |

---

## Stufe 2 — Wrapper-Argumentbindung ✅

- [x] Aufrufstellen von Wrappern mit ihren Argumenten erfasst (`Command.byte_offset`
      trennt Aufruf auf Dateiebene von Kommando im Definitionsrumpf)
- [x] Parameter an Argumente gebunden (`MacroDefinition.parameters` + `body_commands`)
- [x] `${ARGN}` / `${ARGV0..n}` / `${ARGC}` / `${ARGV}` behandelt
- [x] Mehrere Aufrufstellen ergeben mehrere Registrierungen
- [x] Rekursion terminiert (`MAX_EXPANSION_DEPTH = 8`)
- [x] **`set()` im Rumpf erweitert die Bindung** — siehe unten

Neues Modul `cmake_semantics.py`, neues Ergebnismodell `TestRegistration`
(Name, Kommando, Rohform, Expansionskette, Definitions- und Aufrufort).
Neue Spalten `cmake_test_count`, `cmake_tests_resolved`, `cmake_test_names`.

**Ergebnis:** 5613 rekonstruierte Registrierungen in 73 Repos.

| Messgröße | nach Bindung | nach `set()`-Erweiterung |
|---|---|---|
| Name aufgelöst | 36 % | **42 %** |
| Command aufgelöst | 19 % | **27 %** |

`cmake_tests_found` erneut über alle 206 Repos unverändert.

### Nachbesserung innerhalb der Stufe: `set()` im Rumpf

Die erste Messung zeigte `${targetname}` (738×), `${test_target_name}` (673×) und
`${UnitTest_Executable_Name}` (81×) als häufigste unaufgelöste Variablen. Diese sind
keine Parameter, sondern werden **im Makrorumpf per `set()`** abgeleitet:

```cmake
set(targetname ${name}_test)
add_test(NAME ${name} COMMAND ${targetname})
```

Die Bindung verarbeitet `set()` jetzt in Quelltextreihenfolge (`body_commands` wird
nach `byte_offset` sortiert, da die Query-Reihenfolge nicht der Quelltextreihenfolge
entspricht). `${targetname}` halbierte sich dadurch von 738 auf 369.

Wichtig zur Einordnung: Die frühere Messung „globale `set()`-Auflösung bringt 0" bleibt
richtig — entscheidend ist die **lokale, reihenfolgetreue** Bindung im gerade
expandierten Rumpf, nicht eine repo-weite Variablentabelle.

### Befund: Registrierungszahlen sind Obergrenzen über alle Konfigurationen

Repo 2260 (ginkgo) hat nur **8 textuelle** `add_test`-Vorkommen, aber 400 Aufrufstellen
und 1369 Registrierungen. Das ist keine Überexpansion: `ginkgo_create_common_test` ruft
`ginkgo_create_common_test_internal` viermal auf — je einmal für OMP, HIP, CUDA und
SYCL, jeweils hinter `if(GINKGO_BUILD_*)`. 560 = 140 Aufrufstellen × 4 Backends.

Der reale Build registriert nur die Tests der aktivierten Backends. Die Zahl ist also
eine **Obergrenze über alle Konfigurationen** — Stufe 6 (Bedingungskontext) macht das
explizit auswertbar. Für die Arbeit ist das ein eigenständiges Ergebnis: Eine
textbasierte Zählung sieht hier 8 Vorkommen, die strukturelle Analyse 1369 potenzielle
Registrierungen mit benennbarer Bedingung.

### Verbleibende unaufgelöste COMMAND-Variablen (ordnen sich den Folgestufen zu)

| Variable | Anzahl | Zuständige Stufe |
|---|---|---|
| `${MPIEXEC_EXECUTABLE}`, `${CMAKE_COMMAND}`, `${CMAKE_BINARY_DIR}`, `${Python_EXECUTABLE}` | ~1300 | Stufe 5 (Fremdwerkzeuge) |
| `${test_target_name}`, `${targetname}`, `${cmd}`, `${test_name}` | ~2000 | Stufe 3 (`foreach`) bzw. `set()` in verschachtelten Blöcken |
| `${T8CODE_TEST_COMMAND_LIST}` | 98 | Stufe 3 (Listenvariable) |

---

## Stufe 3 — `foreach`-Bindung ✅

- [x] `foreach_loop` erkannt (`extract_loops`, Nesting über Body-Spans statt Baum)
- [x] Liste aufgelöst: literal, über `set()`, über Wrapper-Bindung
- [x] Je Iteration eine Testregistrierung
- [x] Unbestimmbare Liste → `indeterminate_count = True`, **nicht** geraten
- [x] `foreach(RANGE ...)`, `foreach(IN LISTS ...)`, `foreach(IN ITEMS ...)` abgedeckt
- [x] Verschachtelte Schleifen ergeben das Kreuzprodukt
- [x] `MAX_LOOP_ITERATIONS = 64` begrenzt Expansion über sehr lange Listen

| Messgröße | Stufe 2 | Stufe 3 |
|---|---|---|
| Registrierungen | 5622 | **7840** |
| vollständig aufgelöst | 1431 | **1821** |
| unbestimmte Anzahl | – | 1014 |
| verschiedene Testnamen datensatzweit | – | **4778** |

`cmake_tests_found` erneut unverändert. Neue Spalte `cmake_tests_indeterminate`.

**Zur Quote der Auflösung:** Sie sinkt nominell von 25 % auf 23 %, weil der Nenner
schneller wächst als der Zähler. Die Quote ist zwischen den Stufen nicht vergleichbar —
der Nenner bedeutet jetzt etwas anderes (tatsächliche Testanzahl statt Aufrufstellen).
Aussagekräftig ist die **absolute** Zahl aufgelöster Registrierungen: +27 %.

### Zwei Korrekturen innerhalb der Stufe

1. **Quelltextreihenfolge.** Erst wurden alle Kommandos, dann alle Schleifen
   verarbeitet — ein `set()` **nach** einer Schleife hätte fälschlich schon vorher
   gewirkt. Kommandos und Schleifen laufen jetzt in einer nach Byte-Offset sortierten
   Sequenz; abgesichert durch einen Test.
2. **Quotes in Werten.** `Command.arguments` tragen den Quelltext des Knotens, also
   auch die Anführungszeichen eines quoted argument. Ungestrippt gebunden ergab das
   in Repo 2352 (HPX) Namen wie `tests."examples".""1d_stencil"".1d_stencil_1`. Neue
   Funktion `unquote()` wird jetzt in `bind_arguments`, `_apply_set` und der
   Listenauflösung angewendet — danach: **0 von 2355** Namen mit Quotes.

### Fallbeispiel HPX (Repo 2352)

| | |
|---|---|
| textuelle `add_test`-Vorkommen | **9** |
| Aufrufstellen | 62 |
| rekonstruierte Registrierungen | **2394** |
| davon verschiedene Namen | **2355** |

Eine einzige Aufrufstelle (`examples/quickstart/CMakeLists.txt:167`) expandiert 732×.
Die Namen entsprechen HPX' realem CTest-Schema (`tests.examples.1d_stencil.1d_stencil_1`).
2355 verschiedene Namen aus 9 Textvorkommen ist das bislang deutlichste Beispiel
dafür, was eine strukturelle Analyse gegenüber einer textuellen Zählung leistet.

**Anmerkung zur Ausgabe:** `cmake_test_names` sprengt bei großen Repos das
CSV-Feldlimit (131072 Zeichen). Die Namensliste gehört ins geplante JSON-Inventar;
in der CSV sollte nur die Kennzahl bleiben.

---

## Stufe 4 — Target-Verknüpfung ✅

- [x] `add_executable(name src...)` erfasst — **im selben Expansionslauf**, weil
      Targets häufig erst im Wrapper entstehen (`add_executable(${targetname} ...)`)
      und nur mit der Bindung benennbar sind
- [x] `add_test(COMMAND foo)` → Target → Quelldateien (`link_targets`)
- [x] `$<TARGET_FILE:foo>` / `$<TARGET_FILE_NAME:…>` / `$<TARGET_FILE_DIR:…>` aufgelöst
- [x] `gtest_discover_tests(target)` analog verknüpft
- [x] Quelldateien relativ zum Repo-Root normalisiert

Neues Modell `ResolvedTarget`; `TestRegistration` um `target` und `target_sources`
erweitert. Neue Spalten `cmake_tests_with_target`, `cmake_test_source_count`,
`cmake_test_names_distinct`.

| Messgröße | Wert |
|---|---|
| Registrierungen | 7877 |
| vollständig aufgelöst | 1845 |
| **mit verknüpftem Target** | **1288 (16 %)** |
| **identifizierte Testquelldateien** | **924** |
| verschiedene Testnamen | 4815 |
| Repos mit Target-Verknüpfung | 42 |

`cmake_tests_found` erneut unverändert.

### Gravierender Nebenbefund: die Analyse war nicht reproduzierbar

Beim Prüfen einer unerwarteten Abweichung (Repo 1185: 5 → 7 Registrierungen, obwohl
Target-Erfassung die Registrierungszahl nicht ändern kann) kam heraus: `by_basename`
im Graph wurde durch **Iteration über ein Set** gebaut. Bei mehrdeutigen Dateinamen —
Repo 1185 hat eine `enabled.cmake` pro Modul — hing die Auswahl von der
Set-Reihenfolge ab und **variierte zwischen Läufen**.

Zwei Korrekturen:
1. `by_basename` wird über `sorted(candidates)` aufgebaut.
2. Ein mehrdeutiger `include()` löst jetzt auf **alle** Kandidaten auf statt auf einen
   willkürlichen. Welche Datei CMake nimmt, hängt von `CMAKE_MODULE_PATH` ab und ist
   statisch nicht bestimmbar — alle zu nehmen ist die konservative Richtung.

Verifiziert mit `PYTHONHASHSEED` 0/1/42/12345: identische Ergebnisse. Zwei
Regressionstests sichern das ab.

Nebeneffekt: erreichbare Dateien 3188 → 3281, Repo 1185 von 5 auf 21 Registrierungen.

**Für die Arbeit relevant:** Reproduzierbarkeit ist eine Voraussetzung der
Evaluationsläufe — ohne diesen Fund hätten wiederholte Messungen unerklärlich
geschwankt.

### Anmerkung zur Ausgabe

`cmake_test_names` wurde aus der CSV entfernt (sprengte bei großen Repos das
Feldlimit von 131072 Zeichen) und durch `cmake_test_names_distinct` ersetzt. Die
vollständige Namensliste gehört ins JSON-Inventar.

---

## Stufe 5 — Fremdwerkzeug-Klassifikation ✅

- [x] Werkzeugvariablen erkannt: `${CMAKE_COMMAND}`, `${CMAKE_CTEST_COMMAND}`,
      `${MPIEXEC}` und die `find_package`-Konvention `${<Pkg>_EXECUTABLE}`
- [x] Literale Interpreter (`python`, `bash`, `mpirun`, …) und Skript-Endungen
      (`.py`, `.sh`, `.cmake`, …)
- [x] `Namespace::Target` → importiertes Target einer Abhängigkeit
- [x] Registrierung als `driver = external_tool` → **`out of scope`-Markierung aus
      Konzeption §4.4 ist damit umgesetzt**
- [x] Getrennt von `driver = unresolved` (wirklich unbestimmbar)

Neue Spalten `cmake_tests_repo_target`, `cmake_tests_external_tool`,
`cmake_tests_driver_unresolved`. `cmake_tests_found` erneut unverändert.

| Treiber | Anzahl | Anteil | Bedeutung |
|---|---|---|---|
| `repo_target` | **1666** | 21,2 % | führt ein C++-Artefakt dieses Repos aus — **in scope** |
| `external_tool` | **1627** | 20,7 % | Interpreter/Fremdwerkzeug — **out of scope** (§4.4) |
| `unresolved` | 4584 | 58,2 % | statisch nicht bestimmbar |

46 Repos haben in-scope-Tests, 37 out-of-scope-Tests.

### Wichtige Unterscheidung bei den Variablen

Die unaufgelösten Variablen bedeuten **zweierlei**, und das Zusammenwerfen wäre ein
Fehler gewesen:

- `${Python3_EXECUTABLE}`, `${MPIEXEC_EXECUTABLE}` → **externes Werkzeug**
- `${CMAKE_BINARY_DIR}/solver_test`, `${EXECUTABLE_OUTPUT_PATH}/x` → **repo-eigenes
  Binary**, nur über Pfad statt Targetnamen referenziert

Deshalb löst `target_candidates()` zusätzlich über den Basisnamen auf. Wirkung:
Target-Verknüpfungen 1288 → **1666**, identifizierte Testquelldateien 924 → **1063**.

### Verbleibende 58 % unresolved

| Variable | Anzahl | Ursache |
|---|---|---|
| `${cmd}` | 2341 | in einem Scope gesetzt, dem die Expansion nicht folgt |
| `${test_target_name}`, `${test_name}`, `${targetname}` | ~1500 | dito |
| `${CMAKE_BINARY_DIR}` (ohne Basisnamen-Treffer) | 143 | Pfad ohne bekanntes Target |
| `${T8CODE_TEST_COMMAND_LIST}`, `${RUNDIFFTEST}` | ~190 | projektspezifische Listen |

Das ist kein Klassifikationsproblem mehr, sondern eine Grenze der Variablenbindung:
`set()` in einem umschließenden oder Eltern-Scope (`PARENT_SCOPE`), den die Expansion
nicht nachbildet. Eine vollständige Scope-Simulation wäre der nächste Hebel — sie
geht aber deutlich in Richtung CMake-Interpreter und damit über die in §3.5 gezogene
Abgrenzung hinaus. **Bewusst offengelassen und als Grenze dokumentiert.**

## Stufe 6 — Bedingungskontext ✅

- [x] `if`/`elseif`/`else`-Zweige erfasst (`extract_if_blocks`)
- [x] Registrierungen tragen `guarded_by = "<Bedingung>"`
- [x] Verschachtelte Bedingungen zusammengeführt (äußerste zuerst, `" AND "`)
- [x] Unbedingte Registrierungen klar getrennt (`guarded_by = None`)
- [x] Bedingung wird mit der Wrapper-Bindung expandiert (`if(ENABLE_${n})` → `ENABLE_mesh`)

Neue Spalten `cmake_tests_guarded`, `cmake_test_guards_distinct`.

| | Anzahl | Anteil |
|---|---|---|
| **bedingt registriert** | **5116** | 65 % |
| unbedingt | 2761 | 35 % |
| verschiedene Bedingungen | **1404** | |
| Repos mit Guards | 39 | |

**Zwei Drittel aller Testregistrierungen hängen an einer Build-Option.** Damit ist die
in Stufe 2 aufgeworfene Frage beantwortet: Die Registrierungszahlen sind Obergrenzen
über alle Konfigurationen, und die Bedingung ist jetzt benennbar.

Häufigste Bedingungen: `add_test_MPI_SIZE AND …` (673×), `MFEM_MGIS_HAVE_TFEL AND
MFEM_USE_MPI` (55×), `ASGARD_BUILD_TESTS` (40×), `ENABLE_VALGRIND_TESTING` (37×),
`BUILD_TESTING` (36×), `AMReX_OMP`/`AMReX_MPI` (je 33×), `MPI_FOUND` (32×).

### Umsetzung ohne Eingriff in die Expansion

Die Guards werden **per Byte-Offset zugeordnet**, statt die Expansion um If-Blöcke
umzubauen. Das war bewusst so gewählt: `if()` eröffnet in CMake keinen eigenen
Variablen-Scope, ein `set()` darin wirkt nach außen. Hätte ich If-Rümpfe als eigene
Scopes behandelt, wäre diese Semantik gebrochen.

Der Nachweis, dass es funktioniert hat: Der Datensatzvergleich meldet **keine einzige
geänderte bestehende Spalte** — die Registrierungen sind identisch, es kamen nur
Metadaten hinzu.

### Bekannte Vereinfachung

Der `else`-Zweig wird als `"else"` geführt (807×), nicht als Negation der
vorangehenden Bedingungen. Für die Frage „welche Option schaltet diesen Test" ist die
eigene Zweigbedingung das nützlichere Signal; die exakte Negation wäre bei
`elseif`-Ketten schnell unlesbar. Als Vereinfachung dokumentiert.

Kurios und erwähnenswert: 426× lautet die Bedingung `true STREQUAL "true"` — eine
tautologische Wache, die ein flacher Scan gar nicht erst sichtbar machen könnte.

## Ausgabe: Test-Inventar ✅

- [x] Neues Modul `inventory.py` (`repo_inventory`, `write_inventory`)
- [x] `--inventory-out <pfad.jsonl>` in `cli2.py`
- [x] Aggregierte CSV-Spalten vorhanden (`cmake_test_count`, `cmake_tests_resolved`,
      `cmake_tests_external_tool`, `cmake_tests_guarded`, …)

**Format: JSON Lines**, eine Zeile je Repository — statt eines einzelnen
JSON-Objekts. Damit bleibt die Datei pro Repo greppbar, lädt inkrementell (auch mit
`pandas.read_json(..., lines=True)`) und übersteht einen abgebrochenen Lauf.

**Erzeugt:** `foo/test_inventory.jsonl`, 4,0 MB, 205 Repos, 7877 Registrierungen,
1062 verschiedene Testquelldateien.

Jede Zeile enthält `project_id`, `repo_url`, eine `summary` mit allen Kennzahlen,
`test_wrappers`/`unused_test_wrappers` und die vollständige Liste der
Registrierungen. Pro Registrierung:

```json
{
  "test_name": "gtest_misc",
  "raw_name": "${target}",
  "command": "gtest_misc",
  "raw_command": "${target}",
  "registered_by": "manif_add_gtest -> add_test",
  "definition_site": "bar/1371/test/CMakeLists.txt:47",
  "call_site": "bar/1371/test/CMakeLists.txt:52",
  "target": "gtest_misc",
  "target_sources": ["test/gtest_misc.cpp"],
  "driver": "repo_target",
  "guarded_by": null,
  "indeterminate_count": false,
  "resolved": true
}
```

Sowohl die Rohform (`raw_name`, `raw_command`) als auch die aufgelöste Form sind
enthalten — für die manuelle Validierung ist beides nötig, weil man sonst nicht
nachvollziehen kann, *woher* ein Wert stammt.

**Hinweis zu den Zahlen:** Die CSV-Spalte `cmake_test_source_count` summiert
repo-weise Zählungen (1063), das Inventar zählt global verschiedene Pfade (1062).
Die Differenz ist `tests/main.cpp`, das in zwei Repos unter demselben relativen
Pfad existiert — kein Fehler, nur zwei verschiedene Aggregationen.

## Evaluationsdesign

- [ ] **Selbstvergleich flach vs. tief** über alle 206 Repos: Wo weicht die Tiefensuche
      vom flachen Scan ab, in welche Richtung, und warum? Liefert die Differenzmenge.
- [ ] **Manuell validierte Stichprobe**: ~30 Repos mit festem Seed ziehen, Zuordnung
      versioniert ablegen (reproduzierbar), Ground Truth von Hand feststellen. Daraus
      Precision/Recall **der Tiefensuche und der Baseline**. Das ist der eigentliche
      Zahlenbeleg (Konzeption §4.4, zweistufiges Design).
- [ ] **Fallstudien** ausarbeiten:
  - `7881` CADET-Core — unerreichbarer Wrapper + `add_test` im String-Literal
    (bereits dokumentiert in CHANGELOG §8)
  - `1371` artivis/manif — saubere Wrapper-Kette `manif_add_gtest`
  - `153` / `3959` — extern definierte Wrapper als dokumentierte Grenze
- [ ] `comp_rgx_ts_deep.py` wird der primäre Vergleich; `comp_rgx_ts.py` bleibt als
      Beleg der *syntaktischen* Ebene erhalten.

---

## Bewusste Grenzen (in der Arbeit dokumentieren)

- **Keine Build-Umgebung.** Extern definierte Wrapper (`dune_add_test` aus dune-common,
  `ExternalData_add_test` aus CMake selbst) bleiben unauflösbar. Repos 153 und 3959
  bleiben dokumentierte False Negatives — entspricht der Abgrenzung in Konzeption §3.5.
- **Kein Katalog externer Wrapper-Namen.** Das wäre wieder eine Namensheuristik, also
  genau der Mechanismus, den die Arbeit der Baseline vorwirft.
- **Keine vollständige CMake-Auswertung.** Bedingungen werden erfasst, aber nicht
  ausgewertet (`if(BUILD_TESTING)` wird nicht entschieden); Variablen werden nur
  gebunden, wo die Bindung strukturell ableitbar ist. Ziel ist statische Analyse, keine
  Interpretation.
- **Cache-/Umgebungsvariablen** (`option()`, `-D` auf der Kommandozeile) sind
  prinzipiell unbestimmbar.

---

## Regressionsschutz (bei jeder Stufe prüfen)

- [ ] `venv/bin/python3 -m pytest test_suite/ -q` grün
- [ ] `cmake_tests_found` (Paritätsspalte) über alle 206 Repos **unverändert** —
      spaltenweiser CSV-Vergleich wie in CHANGELOG §7/§8/§9
- [ ] `testing-artifact-detector-compare` meldet weiterhin exakt **14** Abweichungen
- [ ] cloc-Sanity-Check bleibt bei 0 Mismatches
