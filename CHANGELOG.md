# CHANGELOG

Chronologische Dokumentation der Entwicklungsschritte seit dem Ausgangsstand des
Tree-sitter-Prototyps, inklusive der iterativen Vergleiche gegen die Regex-Baseline
(`cli.py`) über die 206 JOSS-C++-Repositories (`foo/dataset_index.csv`, geklont in `bar/`).

## 1. Tree-sitter-Nutzung auf die Query-API umgestellt

Ausgangslage: `cmake_ast.py`/`cpp_ast.py` liefen manuell mit `node.walk()` über den
gesamten Baum und klassifizierten Knoten über Typ-Substring-Heuristiken
(`"command" in node_type`) sowie Text-Splitting statt über Tree-sitter-Queries — im
Kern wieder eine lexikalische Analyse, nur auf Knotentext statt auf Rohtext.

Änderungen:
- `tree_sitter_backend.py`: Language-Loading vereinheitlicht (`build_parser(module_name, human_name)`),
  toter `tree_sitter_languages`-Fallback entfernt (nicht in `pyproject.toml` deklariert,
  nicht installiert), Duplikat in `cpp_parser.py` entfernt.
- `cmake_ast.py`: `extract_commands` nutzt jetzt `Query`/`QueryCursor` mit
  `(normal_command (identifier) @command.name (argument_list (argument)* @command.arg)?)`.
- `cpp_ast.py`: `extract_commands` matcht strukturell zwei Makroformen
  (`function_definition→function_declarator` für `TEST(...){...}`, `call_expression`
  für `TEST_CASE(...)`-Aufrufe ohne Block) plus Includes über das `path`-Feld.

Dabei gefundene Bugs (durch Grammatik-Inspektion + Unit-Tests, vor jedem Vergleichslauf):
- `if(...)`/`function(...)`/`endif()` wurden fälschlich als eigene CMake-Commands erfasst
  (Substring-Match `"command" in type`).
- Anführungszeichen-Argumente mit Leerzeichen (`"my long test name"`) wurden am
  Leerzeichen falsch aufgesplittet.

Ergebnis: 26 Unit-Tests grün (zwei vorher bereits kaputte Tests durch echte
Parser-Tests ersetzt).

## 2. Erster Vergleichslauf: Baseline vs. Tree-sitter (naiv)

`comp_rgx_ts.py` (v1) erstellt und beide CLIs über den vollständigen Datensatz laufen lassen:
- `testing-artifact-detector --in-file foo/dataset_index.csv --out-file foo/baseline_regex.csv --clone-dir bar`
- `testing-artifact-detector-ts --in-file foo/dataset_index.csv --out-file foo/treesitter.csv --clone-dir bar`

Vergleich (Baseline vs. Tree-sitter `cpp_*` **oder** `cmake_*` kombiniert): **210 Abweichungen**
über 5 Indikatoren, u. a.:

| Indikator | nur Baseline=True | nur Tree-sitter=True |
|---|---|---|
| has_cpp_tests | 8 | 79 |
| uses_gtest | 0 | 47 |
| uses_catch2 | 0 | 27 |
| gtests_found | 0 | 39 |

Root-Cause der 79 `has_cpp_tests`-Abweichungen: 36 davon ausschließlich durch das
generische `"assert"`-Makro in `GENERIC_TEST_MACROS` getrieben (kein echtes
Test-Framework-Makro beteiligt).

Methodisches Problem erkannt (Review durch Nutzer): Die Baseline liest nie
C++-Quellcode (`cpp_test_config_parser.py` arbeitet ausschließlich auf
CMake-Dateien), Tree-sitter aber schon (`cpp_*`-Felder) — der Vergleich war
dadurch nicht repräsentativ, da nicht dieselbe Heuristik verglichen wurde.

## 3. Vergleichsmethodik korrigiert + `assert` entfernt

- `cpp_results.py`: `"assert"` aus `GENERIC_TEST_MACROS` entfernt (kein Testartefakt,
  sondern gewöhnlicher `<cassert>`-Laufzeit-Check).
- `comp_rgx_ts.py` (v2): Vergleich auf `cmake_*`-Felder von Tree-sitter beschränkt
  (gleiche Heuristik-Zielsetzung wie Baseline: `find_package`, `add_test`,
  `gtest_discover_tests`). `cpp_*`-Felder (Quellcode-Ebene) laufen nur noch informativ
  in einem separaten "beyond baseline scope"-Abschnitt, ohne in die
  Übereinstimmungs-Statistik einzufließen. `has_cmakelists` wird jetzt über
  `cmake_files_found > 0` verglichen statt über das engere `has_cmakelists`-Feld
  (Baseline zählt jede `*.cmake`-Datei, nicht nur `CMakeLists.txt`).

Dabei gefundener Bug (Code-Review beim Umbau, vor dem nächsten Lauf):
- `update_framework_flags` (`cmake_ast.py`): `find_package(Catch2)` setzte fälschlich
  auch `uses_gtest=True`, weil `FRAMEWORK_KEYWORDS = {"gtest","googletest","catch2"}`
  als Ganzes für das gtest-Flag geprüft wurde. Fix: getrennte Prüfung pro Framework.

Neuer Lauf (Tree-sitter neu generiert, Baseline unverändert): **27 Abweichungen** (von 210).

## 4. Bug: `gtests_found`/`tests_found` durch bloße Abhängigkeitsdeklaration gesetzt

Root-Cause-Analyse der verbliebenen 27 Abweichungen (`differences.csv`): Repo `1371`
(`artivis/manif`) meldete `cmake_gtests_found=True`, obwohl im gesamten Repo kein
einziger `gtest_discover_tests`-Aufruf existiert. Ursache: `cmake_gtests_found`/
`cmake_tests_found` wurden bereits durch ein bloßes `find_package(GTest)` gesetzt —
eine reine Abhängigkeitsdeklaration wurde als "Test gefunden" gewertet.

Fix: `update_framework_flags` setzt nur noch `uses_gtest`/`uses_catch2`
(Abhängigkeit deklariert); `tests_found`/`gtests_found` werden ausschließlich durch
tatsächliche `add_test`/`gtest_discover_tests`/`enable_testing`-Kommandos gesetzt
(bereits vorhandene Logik in `detector.py`).

Regressionstests ergänzt (`test_treesitter_detector.py`): 4 neue Tests für die
Bugs aus Schritt 3 und 4. Gesamt: 29 Tests grün.

Neuer Lauf: **20 Abweichungen** (von 27). `gtests_found` erreicht **perfekte
Übereinstimmung** (11× gemeinsam True, 192× gemeinsam False, 0 Abweichungen).

## 5. Stand nach vier Iterationen

| Indikator | Übereinstimmung | Abweichungen |
|---|---|---|
| has_cmake_file | 138✓ / 65✗ | 0 |
| uses_gtest | 12✓ / 185✗ | 6 |
| uses_catch2 | 7✓ / 195✗ | 1 |
| tests_found | 76✓ / 125✗ | 2 |
| gtests_found | 11✓ / 192✗ | 0 |

Sanity-Check: `has_cpp`/`has_c` sind zwischen beiden Läufen für alle 206 Repos
identisch (0 Mismatches) — beide CLIs nutzen dieselbe `cloc`-basierte
Sprach-Erkennung, verbleibende Abweichungen liegen also ausschließlich an der
C++/CMake-Analyse selbst.

Stichprobenprüfung der verbliebenen 20 Abweichungen ergab keine weiteren
Implementierungsfehler mehr, sondern methodisch interessante Fälle für die
Fallstudien in §4.4 der Konzeption:
- Repo `7957` (`ethz-randomwalk/polytopewalk`): Baseline meldet `uses_catch2=True`,
  obwohl `find_package(Catch2 REQUIRED)` **auskommentiert** ist
  (`#find_package(...)`) — echter Baseline-False-Positive, Tree-sitter korrekt.
- Repo `3959` (`samuelburbulla/dune-mmesh`): Baseline meldet `tests_found=True`
  über das eigene Wrapper-Makro `dune_add_test(...)`, das per Substring-Match auf
  `"add_test"` matcht — richtiges Ergebnis aus falschem Grund. Tree-sitter matcht
  exakt auf den Kommandonamen und verpasst daher Wrapper-Makros.
- Repo `558` (`barbagroup/PetIBM`) u. a. (6 Fälle bei `uses_gtest`): moderne
  `FetchContent`+`gtest_discover_tests`-Setups ganz ohne `find_package(GTest)` —
  Baseline kann das strukturell nicht erfassen, Tree-sitter korrekt.

## 6. Heuristiken exakt an Baseline angeglichen

Rückfrage: Sind die verglichenen `cmake_*`-Felder jetzt wirklich exakt dieselbe
Heuristik wie die Baseline, sodass jede verbleibende Abweichung nur noch an
AST vs. Regex liegt — nicht an unterschiedlichen/breiteren Prüfbedingungen?
Antwort: nein, vier echte Heuristik-Unterschiede gefunden und angeglichen:

- **A)** `uses_gtest` wurde in Schritt 4/5 auch über `gtest_discover_tests`
  gesetzt (Repo `558` u. a., 6 Fälle). Baseline setzt `uses_gtest` ausschließlich
  über `find_package`. Entfernt (`detector.py`); bewusst nicht ersatzlos
  gelöscht, sondern als Kommentar an Ort und Stelle sowie hier dokumentiert —
  ist eine sachlich korrekte, aber über die Baseline hinausgehende
  Heuristik-Erweiterung, die für eine spätere, separate Auswertung (nicht den
  reinen Technologie-Vergleich) wieder aktiviert werden kann.
- **B)** `tests_found` wurde durch ein bloßes `enable_testing()` gesetzt
  (`TEST_COMMANDS` enthielt `"enable_testing"`). Baseline prüft dafür nur
  `add_test`/`gtest_discover_tests`. `TEST_COMMANDS` auf diese zwei verengt
  (`results.py`); das separate `enable_testing`-Feld bleibt unverändert.
- **C)** `find_package`-Check prüfte alle Argumente des Aufrufs statt nur das
  erste (den Paketnamen), wie die Baseline-Regex (`group(2)`). Auf
  `arguments[0]` beschränkt (`cmake_ast.py::update_framework_flags`).
- **D)** `has_cmakelists` zählte nur eine literale `CMakeLists.txt`, Baseline
  zählt jede `CMakeLists.txt(.in)`/`*.cmake(.in)`-Datei. Feld auf `True` für
  jede erfolgreich gelesene CMake-Kandidatendatei umgestellt (`detector.py`);
  `CMakeLists.txt.in` zusätzlich in `source_collector.py::CMAKE_FILENAMES`
  aufgenommen, damit auch diese Dateien überhaupt erfasst/gescannt werden.

Regressionstests ergänzt: `enable_testing()` allein → `tests_found=False`;
`find_package(Foo COMPONENTS GTest)` → `uses_gtest=False`; nur `utils.cmake`
ohne `CMakeLists.txt` → `has_cmakelists=True`; bestehender
`gtest_discover_tests`-Test um `uses_gtest=False` korrigiert. 32 Tests grün.

Neuer Lauf: **14 Abweichungen** (von 20), davon nur noch **4 echte inhaltliche
Abweichungen** (die übrigen 10 sind zwei Repos mit fehlenden Daten auf einer
Seite). `has_cmake_file` und `gtests_found` jetzt beide bei **0 Abweichungen**.

| Indikator | Übereinstimmung | Abweichungen |
|---|---|---|
| has_cmake_file | 138✓ / 65✗ | 0 |
| uses_gtest | 11✓ / 191✗ | 1 |
| uses_catch2 | 7✓ / 195✗ | 1 |
| tests_found | 76✓ / 125✗ | 2 |
| gtests_found | 11✓ / 192✗ | 0 |

Die 4 verbleibenden Abweichungen bestätigen — nach Angleichung aller
Heuristiken — ausschließlich die schon in Schritt 5 identifizierten
Parsing-Technologie-Grenzen der Baseline, jetzt mit zwei zusätzlichen
Beispielen pro Kategorie:
- **Kommentierter Code wird von der Baseline mitgezählt:** Repo `7957`
  (`uses_catch2`, `#find_package(Catch2 REQUIRED)`) und neu Repo `3061`
  (`tumcms/Open-Infra-Platform`, `uses_gtest`, `#find_package(GTest REQUIRED)`).
- **Substring-Match auf Wrapper-Makros ist "richtig aus falschem Grund":**
  Repo `3959` (`dune_add_test(...)`) und neu Repo `153`
  (`KitwareMedical/SlicerITKUltrasound`, `ExternalData_add_test(...)`).

Damit ist der CMake-vs-CMake-Vergleich jetzt ein reiner Parsing-Technologie-Vergleich:
jede verbleibende Abweichung lässt sich auf eine der drei in Schritt 5 genannten
lexikalischen Grenzen der Baseline zurückführen, nicht mehr auf unterschiedliche
Prüfbedingungen zwischen den beiden Tools.

## Offene Punkte

- C++-Quellcode-Ebene (`cpp_*`) noch nicht in den fairen Vergleich integriert —
  geplant als eigener Auswertungsschritt für F03/Cross-Language-Mapping (§4.4),
  siehe `Checklist.md`.
- A) und B) aus Schritt 6 sind sachlich korrekte Heuristik-Erweiterungen über die
  Baseline hinaus (GTest-Erkennung über `gtest_discover_tests`; ggf. auch
  `enable_testing()` als schwaches Testindiz). Kandidaten für eine bewusste,
  separat ausgewiesene Erweiterung, sobald der reine Technologie-Vergleich
  abgeschlossen/dokumentiert ist.
- `dune_add_test`/`ExternalData_add_test`-artige Wrapper-Makros werden von
  Tree-sitter aktuell nicht aufgelöst (erfordert Makro-/Funktionsdefinitions-
  Resolution in CMake, außerhalb des aktuellen Scopes).
