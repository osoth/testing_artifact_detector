# CHANGELOG

Entwicklung des AST-basierten Detektors (`treesitter_detector`) gegenüber dem
regexbasierten Referenzwerkzeug. Jeder Schritt wurde über alle 206 Repositories des
Datensatzes gegengeprüft; die Spalte `cmake_tests_found` musste dabei unverändert
bleiben, damit die Baseline-Parität erhalten blieb.

## 1. Umstellung auf die Tree-sitter-Query-API

- Manueller Baumdurchlauf durch Queries ersetzt.
- Behobener Fehler: Der Test `"command" in node_type` traf 20 Knotentypen der
  CMake-Grammatik, darunter `if_command` und `endif_command`.
- Behobener Fehler: Argumente wurden aus dem Zeilentext am Leerzeichen zerlegt,
  wodurch `add_test(NAME "my long test name")` zerriss.
- Optionale `argument_list` im Muster berücksichtigt, sonst fiel `enable_testing()`
  heraus.

## 2. Fehler: Abhängigkeitsdeklaration galt als Testfund

- `find_package(GTest)` allein setzte `gtests_found` und `tests_found`.
- Getrennt: Eine Abhängigkeit zu deklarieren ist kein registrierter Test.

## 3. Heuristiken exakt an die Baseline angeglichen

Vier Stellen, an denen die eigene Umsetzung über die Baseline hinausging. Alle vier
verengen sie:

- **A** `uses_gtest` wurde auch durch `gtest_discover_tests` gesetzt, die Baseline
  nutzt nur `find_package`.
- **B** `tests_found` wurde durch ein alleinstehendes `enable_testing()` gesetzt.
- **C** `find_package` prüfte alle Argumente statt nur den Paketnamen.
- **D** `has_cmakelists` zählte nur eine wörtliche `CMakeLists.txt`.

Damit misst der Vergleich allein den Wechsel der Parsing-Technologie und nicht
zusätzlich die Reichweite der Heuristik.

## 4. Vergleich mit der Baseline

| Indikator | Übereinstimmung | Abweichungen |
|---|---|---|
| `has_cmake_file` | 203 | 0 |
| `uses_gtest` | 202 | 1 |
| `uses_catch2` | 202 | 1 |
| `tests_found` | 201 | 2 |
| `gtests_found` | 203 | 0 |

- **14 Abweichungszeilen**, davon 4 inhaltlich; die übrigen 10 sind zwei Repositories
  mit einseitig fehlenden Daten.
- Alle vier inhaltlichen sind False Negatives der AST-Seite. Die Baseline trifft dort
  in auskommentiertem Quelltext (Repos 3061, 7957, siehe Schritt 11) oder per Substring
  auf Wrapper-Namen (Repos 153, 3959).
- **Befund:** Der Technologiewechsel allein bringt für diesen Datensatz keine breitere
  Erkennung. Jeder spätere Mehrbefund ist damit der semantischen Ebene zuzurechnen.

## 5. Refactoring ohne Logikänderung

- Ein Modul je Zuständigkeit statt zweier großer Dateien.
- Gemeinsame Teile in `common.py` und `tree_sitter_backend.py` zusammengefasst, das
  Backend kennt weder CMake noch den Untersuchungsgegenstand.
- Ergebnis über alle 206 Repositories unverändert.

## 6. Erreichbarkeit: welche Dateien CMake überhaupt liest

- Gerichteter Graph ab der `CMakeLists.txt` im Wurzelverzeichnis über
  `add_subdirectory`, `include` und `find_package`.
- Dateien mit der Endung `.in` sind Vorlagen und werden nie als CMake-Quelltext
  gelesen.
- **3281 von 4473 CMake-Dateien erreichbar (73 %).** Das verbleibende Viertel besteht
  überwiegend aus mitgelieferten Fremdbibliotheken und ungenutzten Hilfsmodulen.
- Drei konservative Sonderfälle, jeweils zugunsten der Erreichbarkeit entschieden:
  unauflösbares Argument (eine Ebene tief), Datei mit Syntaxfehlern, fehlende Wurzel
  (degradierter Modus, im Ergebnis vermerkt).

## 7. Aufrufgraph der Definitionen

Ein `add_test` im Rumpf eines Makros läuft nur, wenn das Makro aufgerufen wird. Die
Unterscheidung zwischen Definition und Aufrufstelle ist am Text nicht möglich.

- Zwei Fixpunktiterationen über die Definitionen des gesamten Repositorys: welche
  registrieren einen Test, und welche werden von der Dateiebene aus aufgerufen.
- Der Schnitt sind die aufgerufenen Test-Wrapper, die Differenz die nie aufgerufenen.
- Trägt wechselseitig rekursive Definitionen, bei denen ein einfacher Durchlauf nicht
  terminiert.
- **127 aufgerufene gegenüber 26 nie aufgerufenen Test-Wrappern** in acht
  Repositories.
- Eigene Spalten (`cmake_tests_via_wrapper`, `cmake_test_wrappers`,
  `cmake_unused_test_wrappers`), damit die Parität aus Schritt 3 erhalten bleibt.
- Extern definierte Wrapper wie `dune_add_test` bleiben unauflösbar.

## 8. Urteil und Einordnung je Fundstelle

Berichtseinheit ist die **Fundstelle**: eine Stelle, an der ein Testkommando
geschrieben steht, samt Urteil, ob sie ausgewertet wird. Eine Fundstelle ist kein Test
— eine in einer Schleife registriert so viele, wie die Schleife Durchläufe hat, und
diese Zahl wird bewusst nicht bestimmt.

- Drei Urteile: `invoked`, `file_unreachable`, `wrapper_uncalled`.
- Kontext je Fundstelle: umschließender Wrapper, `if`-Bedingungen (als Text erfasst,
  nicht ausgewertet), Verschachtelungstiefe in `foreach`-Schleifen.
- Zuordnung über Byte-Offsets, nicht über eine Umstrukturierung des Baums: Ein
  `if`-Block öffnet in CMake keinen Variablenbereich, die Bedingung ist damit eine
  Eigenschaft der Position.

**Ergebnis über den Datensatz:**

| | |
|---|---|
| Fundstellen insgesamt | 965 |
| davon nachgewiesen ausgewertet | 914 |
| verworfen, Datei nicht erreichbar | 32 |
| verworfen, Wrapper nie aufgerufen | 19 |
| ausgewertet, direkt auf Dateiebene | 791 |
| ausgewertet, in einem Wrapper | 123 |
| ausgewertet, unter einer Bedingung | 392 (43 %) |
| ausgewertet, in einer Schleife | 90 (10 %) |

Auf Repository-Ebene: 76 mit einem textuellen Testkommando, **73 mit einem nachgewiesen
ausgewerteten**. Die drei Repositories 1063, 2645 und 7881 entscheidet die Analyse
anders als jedes zeilenbasierte Verfahren; ihre Testkommandos liegen in einem nie
eingebundenen Beispielverzeichnis, in generierter Build-Ausgabe einer Fremdbibliothek
beziehungsweise in einem mitgelieferten Catch-Helfer.

## 9. Fundstellenverzeichnis

- Zusätzlich zur CSV ein Verzeichnis im Format JSON Lines, eine Zeile je Repository.
- Je Fundstelle: Datei und Zeile, Kommandoart, Urteil, umschließender Wrapper,
  Bedingungen, Schleifentiefe.
- Je Repository eine Zusammenfassung mit denselben Kennzahlen wie in der CSV, sodass
  jede aggregierte Zahl auf die Einzeleinträge zurückführbar ist.

## 10. Behobene Fehler und Qualitätssicherung

- Pfade werden mit `os.path.normpath` zusammengesetzt und nicht mit `Path.resolve()`,
  das absolute Pfade gegen relative Kandidaten liefert.
- Nicht reproduzierbare Läufe: Bei mehrdeutigen Dateinamen in einem `include` wurde über
  eine ungeordnete Menge iteriert, sodass je Lauf eine andere Datei als erreichbar galt.
  Die Kandidaten werden jetzt sortiert und sämtlich als erreichbar behandelt, was
  zugleich der Über-Approximation entspricht.
- **Reproduzierbarkeit geprüft:** Läufe mit `PYTHONHASHSEED` 0, 1 und 42 erzeugen ein
  bytegleiches Verzeichnis (`3bf8ddd0e3c7fc1c33eedb178edca99a`) und eine zeilengleiche
  CSV.
- **Befund zur Fehlertoleranz:** 57 Dateien in 46 Repositories enthalten `ERROR`- oder
  `MISSING`-Knoten. Im Repository 1848 fasst die Fehlerbehandlung 582 der 1182 Zeilen zu
  einem einzigen `ERROR`-Knoten zusammen. Fehlertoleranz sichert zu, dass der Parser
  nicht abbricht, nicht dass ein lokaler Fehler lokale Auswirkungen hat.
- 36 Modultests auf synthetischen Kleinstprojekten, die jeweils genau eine Konstruktion
  enthalten.

## 11. Befund zur Deklaration von Test-Frameworks

- Elf Repositories binden GoogleTest oder Catch2 ausschließlich über `FetchContent` ein,
  ein weiteres über `CPMAddPackage`. Die nach Angleichung A auf `find_package` verengte
  Prüfbedingung erfasst das nicht — in neun dieser elf melden **beide** Werkzeuge
  übereinstimmend keinen Befund und liegen beide falsch.
- In zwei Fällen (Repos 3061, 7957) steht die alte `find_package`-Zeile noch als
  Kommentar da. Die Baseline trifft darauf und kommt zufällig zum richtigen Ergebnis.
  Das sind zwei der vier Abweichungen aus Schritt 4; ihre Ursache liegt damit in der
  Prüfbedingung und nicht im Analyseverfahren.
