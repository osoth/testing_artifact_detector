# Implementation Checklist — AST-basiertes Framework (aus Konzeption.tex)

Abgeleitet aus der Konzeption (Anforderungsanalyse §3.1, SDRM-Phasen §3.3, Evaluationsdesign §4).
Bezieht sich auf den aktuellen Stand in `src/testing_artifact_detector/treesitter_detector/` und `cli2.py`.
Ergänzt `REQUIREMENT.MD` (Status-Tracker) um konkrete, abhakbare Arbeitsschritte.

---

## 1. F01 — AST-Parsing (Must)

- [x] Tree-sitter Parser für CMake (`cmake_parser.py`, `build_cmake_parser`)
- [x] Tree-sitter Parser für C++ (`cpp_parser.py`)
- [ ] Sauberes Fehlerbild, wenn Grammatik-Pakete fehlen: aktuell wirft `build_cmake_parser`/`build_cpp_parser`
  einen `RuntimeError` zur Laufzeit statt beim Start klar zu melden, welches Paket installiert werden muss
  → einheitliche Prüfung/Fehlermeldung beim Programmstart statt beim ersten Dateiaufruf
- [ ] Parser-Instanzen wiederverwenden statt pro Repository/Datei neu aufzubauen (Vorbereitung für F. Performanz)
- [ ] Unit-Tests für "kaputte"/unvollständige Eingabedateien (nicht kompilierbarer C++-Code, unvollständige
  CMakeLists.txt) ergänzen, um die in §2.1/§2.3 postulierte Fehlertoleranz von Tree-sitter (GLR) auch am
  eigenen Code zu belegen

## 2. F02 — Strukturelle Suche (Must)

- [x] CMake-Kommandos strukturell extrahiert (`cmake_ast.py::iter_command_nodes`, `extract_command`)
- [x] C++ Test-Makros/Includes strukturell erkannt (`cpp_ast.py`, `cpp_results.py`: GTest/Catch2/generische Makros)
- [ ] Abgleich der SWORDS-Heuristiken (§3.4 „bereits im SWORDS-Projekt etablierte textbasierte Heuristiken“):
  vorhandene Regex-Detektoren in `src/testing_artifact_detector/detectors/` systematisch durchgehen und für
  jede Heuristik dokumentieren, ob/wie sie als AST-Knotenmuster in `cpp_ast.py`/`cmake_ast.py` reproduziert ist
  → Lückenliste erstellen (Basis für die "Suchmuster"-Definition aus §3.4)
- [ ] Explorative Stichprobenanalyse (§3.4, zweiter Baustein): manuelle Sichtung repräsentativer Repos aus dem
  JOSS-Datensatz auf zusätzliche strukturelle Muster, die über reine Textmuster hinausgehen (z. B. Test-Traits
  über Templates, benutzerdefinierte Assertion-Makros) — Ergebnisse als neue Knotentyp-Regeln einpflegen
- [ ] Boost.Test / CppUnit / doctest-Makros vervollständigen (aktuell nur teilweise in `GENERIC_TEST_MACROS`
  in `cpp_results.py`, z. B. `assert` ist kein Test-Framework-Makro und sollte geprüft/entfernt werden)

## 3. F03 — Cross-Language-Mapping (Must) — größte offene Lücke

Laut `REQUIREMENT.MD` aktuell nur **Partial**: CMake- und C++-Ergebnisse werden getrennt erhoben, es gibt
noch keine explizite Verknüpfung zwischen `add_test`/`gtest_discover_tests`-Targets und C++-Quelldateien.

- [ ] CMake-Zielauflösung: `add_executable`/`add_library`-Kommandos einlesen und Zielname → Quelldatei(en)
  abbilden (neue Funktion in `cmake_ast.py`, analog zu `extract_command`)
- [ ] `add_test`-Kommandos auf ihr referenziertes Executable-Target zurückführen (Zielname aus `COMMAND`-Argument)
- [ ] Mapping Target → Quelldatei(en) → C++-Datei-Analyseergebnis aus `cpp_results.py` verknüpfen
- [ ] Fälle behandeln, in denen `add_test` ein Nicht-C++-Artefakt aufruft (Python-/Shell-Skripte) und diese
  gemäß §4.4 explizit als **"out of scope"** markieren statt als Fehltreffer gegen das C++-Mapping zu werten
- [ ] `gtest_discover_tests`/CTest-generierte Test-Namen (Test-Suite/Test-Case-Namen) mit den in C++ gefundenen
  `TEST`/`TEST_F`-Makro-Namen abgleichen, nicht nur binär "Tests gefunden ja/nein"
- [ ] Ergebnisdatenmodell erweitern: neue Datenklasse (z. B. `CrossLanguageMapping`) mit Feldern
  `cmake_target`, `test_command`, `mapped_cpp_files`, `mapped_test_names`, `out_of_scope`
- [ ] Neues Reporting-Feld in `cli2.py::handle_cpp_and_cmake` für Mapping-Ergebnis (z. B.
  `cross_language_tests_mapped`, `cross_language_out_of_scope_count`)
- [ ] Unit-Tests mit synthetischen Mini-Repos (CMakeLists.txt + .cpp) für: 1-zu-1-Mapping, mehrdeutiges
  Mapping (mehrere Targets), Nicht-C++-Target (out of scope), fehlendes Mapping (Recall-Lücke)

## 4. F04 — Berichtsausgabe (Should)

- [x] CSV-Export der Analyseergebnisse (`cli2.py::process_csv_and_handle_repos`)
- [ ] Cross-Language-Mapping-Felder in den CSV-Output aufnehmen (siehe Abschnitt 3)
- [ ] Optionales strukturiertes Format (JSON) pro Repository für die spätere Evaluation/Differential-Testing
  ergänzen — CSV allein ist für den Abgleich einzelner Test-Artefakte (nicht nur Repo-Flags) zu grob
- [ ] Lauf-Metadaten im Report festhalten (Tree-sitter-Grammatik-Version, Analysedatum) für Reproduzierbarkeit

## 5. Nicht-funktionale Anforderungen

### 5.1 Fehlertoleranz
- [x] Datei-Ebene: Parse-Fehler brechen den Gesamtlauf nicht ab (`parse_cmake_file`/`parse_cpp_file`
  fangen Exceptions und schreiben in `parse_errors`)
- [ ] Fehlende Grammatik-Pakete führen aktuell zu einem harten `RuntimeError` beim Parser-Bau — sollte
  stattdessen sauber geloggt werden und die betroffene Sprache für den Lauf überspringen (Repo-Analyse
  für die jeweils andere Sprache soll trotzdem weiterlaufen)
- [ ] Verhalten bei fehlenden Abhängigkeiten (z. B. nicht aufgelöste `find_package`) explizit testen —
  Analyse darf nicht abbrechen, nur weil das Build-System nicht konfigurierbar ist (§3.2 NFR "Fehlertoleranz")

### 5.2 Modularität
- [ ] Gemeinsame Parser-Infrastruktur (`tree_sitter_backend.py`) so verallgemeinern, dass eine neue Sprache
  ausschließlich durch (a) Grammatik-Registrierung, (b) neue `*_ast.py`-Query-Datei, (c) neues
  `*_results.py`-Datenmodell hinzugefügt werden kann, ohne `*_parser.py`/`cli2.py` inhaltlich anzufassen
- [ ] Diese Erweiterbarkeit als konkreten Schnittstellenvertrag dokumentieren (z. B. Protocol/ABC für
  „Language Analyzer"), da §5.4 (Evaluierung der Erweiterbarkeit) genau diesen Aufwand als Machbarkeitsnachweis
  braucht

### 5.3 Performanz
- [ ] Inkrementelles Parsen (Tree-sitter `parser.parse(bytes, old_tree)`) evaluieren/einbauen, aktuell wird
  pro Datei ein kompletter Neu-Parse ohne Wiederverwendung von Zustand durchgeführt
- [ ] Laufzeitmessung über den JOSS-Datensatz (206 Repos) etablieren, um „akzeptable Zeit" (§3.2) quantitativ
  zu belegen (z. B. Gesamtlaufzeit, Median pro Repo, Ausreißer)

## 6. Architektur (SDRM Phase 2–4, §3.3, Abb. „Architekturdesign.png“)

- [ ] Implementierten Code-Aufbau mit dem in `img/Architekturdesign.png` dargestellten Schema abgleichen;
  Abweichungen dokumentieren oder Diagramm aktualisieren, bevor es in der Arbeit zitiert wird
- [ ] Datenfluss "Quellcode-Aufnahme → Tree-sitter → sprachspezifische Queries → Report" als klar benannte
  Pipeline-Funktion (Orchestrator) abbilden, damit die Architektur im Text 1:1 auf eine Funktion/Modul verweisen kann
- [ ] `clone_repo.py` (aktuell laut Git-Status verändert) gegenprüfen: stellt sicher, dass Clone-Fehler
  (private Repos, gelöschte Repos, Rate-Limits) den Gesamtlauf über 206 Repos nicht abbrechen

## 7. Evaluationspipeline (§4) — eigenständige Implementierung, nicht nur Framework selbst

Das Evaluationsdesign in Konzeption §4 verlangt zusätzliche Tooling-Komponenten, die über das
Kern-Framework hinausgehen:

### 7.1 Baseline (lexikalische Analyse, SWORDS)
- [ ] Bestehendes SWORDS-/Regex-Tool (`src/testing_artifact_detector/detectors/*.py`) als eigenständig
  aufrufbare Baseline reproduzierbar machen (gleicher CLI-Eintrittspunkt/Datensatz wie das AST-Tool)
- [ ] Sicherstellen, dass Baseline und AST-Framework denselben Datensatz (206 JOSS-C++-Repos) mit identischer
  Repo-Auswahl/-Version verarbeiten (gleicher Commit-Stand pro Repo für Vergleichbarkeit)

### 7.2 Differential Testing (§4.3)
- [ ] Automatisierten Vergleich der beiden Ergebnismengen (Baseline-CSV vs. AST-CSV) implementieren
- [ ] Differenzmenge extrahieren: Repos/Artefakte, bei denen Baseline und AST-Framework abweichende
  Ergebnisse liefern
- [ ] Tooling/Format für die manuelle Validierung der Differenzmenge (z. B. annotierbare Tabelle/CSV mit
  Spalten für "korrektes Ergebnis", "Begründung")

### 7.3 Metriken (§4.3, Precision/Recall nach Manning et al.)
- [ ] Precision-/Recall-Berechnung auf Basis der manuell validierten Differenzmenge + der Übereinstimmungsmenge
  implementieren (separates Auswertungsskript, nicht Teil des Kern-Frameworks)
- [ ] False-Positive-/False-Negative-Listen je Ansatz (lexikalisch vs. AST) exportieren für die Diskussion im
  Ergebniskapitel

### 7.4 Automatisierte Cross-Language-Validierung (§4.4, Punkt 1)
- [ ] Aufbauend auf Abschnitt 3 (Cross-Language-Mapping): automatisierten Abgleich "CMake definiert
  `add_test` → C++-Artefakt muss vom Framework gefunden werden" über den gesamten Datensatz laufen lassen
- [ ] Sensitivität (Recall) speziell für diese Ground-Truth-Teilmenge berechnen und getrennt von der
  allgemeinen Precision/Recall-Auswertung ausweisen

### 7.5 Qualitative Fallstudien (§4.4, Punkt 2)
- [ ] Auswahlkriterien/Skript zur Identifikation "komplexer" Repos (z. B. Template-basierte Tests,
  Makro-lastiger Code) definieren, um die Case-Study-Stichprobe systematisch statt willkürlich zu ziehen
- [ ] Struktur/Vorlage für die manuelle Fehleranalyse je Fallstudie festlegen (Repo, gefundene/verpasste
  Artefakte, Ursache)

### 7.6 Erweiterbarkeits-PoC (§5.4)
- [ ] Proof-of-Concept: zusätzliche Sprache (Python, wie im Text vorgeschlagen) exemplarisch in die
  bestehende Architektur integrieren, um die in Abschnitt 5.2 geforderte Modularität praktisch zu belegen
- [ ] Implementierungsaufwand (LOC, Anzahl neuer Dateien/Queries, Zeitaufwand) für die neue Sprache im
  Vergleich zu C++/CMake dokumentieren — direkte Grundlage für die Argumentation in §5.4

## 8. Abgrenzung — Nicht-Ziele (§3.5, zur Erinnerung, keine Umsetzung nötig)

- Keine Testausführung
- Keine vollständige Compiler-Simulation/Build-Korrektheitsprüfung

## 9. Testabdeckung des eigenen Tools

- [ ] `test_suite/unit/test_treesitter_cmake.py` / `test_treesitter_cpp.py` erweitern: Abdeckung für
  `cmake_ast.py`, `cpp_ast.py` und das neue Cross-Language-Mapping (Abschnitt 3) gegenprüfen und
  Lücken schließen
- [ ] Für `source_collector.py` (Dateierfassung) und `tree_sitter_backend.py` (Parserbau, Query-Cache)
  existieren bislang **gar keine** Tests — beide sind zentral für jedes Analyseergebnis
- [ ] Regressionstests mit den synthetischen Mini-Repos aus Abschnitt 3 dauerhaft im Repository ablegen
  (`test_suite/unit/test_data/...`), analog zum bestehenden Python-Test-Datenmuster
