# Requirement Checklist

Status legend:
- `Done` = implemented in the current Tree-sitter code path
- `Partial` = some parts are implemented, but the requirement is not fully met
- `Missing` = not implemented yet

## Functional Requirements

- [x] **F01 AST-Parsing** `Done`
  - Tree-sitter parsing exists for C++ and CMake in `src/testing_artifact_detector/treesitter_detector/`.
  - CMake and C++ syntax trees are parsed and analyzed in `detector.py` and `cpp_parser.py`.

- [x] **F02 Strukturelle Suche** `Done`
  - Test-relevant information is extracted from AST/CST node types and node text, not from regex-only matching.
  - C++ includes, test macros, and CMake commands are processed structurally in `cpp_ast.py` and `cmake_ast.py`.

- [ ] **F03 Cross-Language-Mapping** `Partial`
  - The code analyzes C++ and CMake separately and reports both result sets.
  - It does not yet build an explicit link between a CMake test target and the corresponding C++ test source.

- [x] **F04 Berichtsausgabe** `Done`
  - The CLI writes analysis results to CSV in `cli2.py`.
  - The Tree-sitter output includes dedicated CMake/C++ columns for discovered artifacts.

## Non-Functional Requirements

- [ ] **Fehlertoleranz** `Partial`
  - File-level parse failures are handled without stopping the whole run.
  - Missing Tree-sitter grammar packages still raise runtime errors in parser construction.

- [ ] **Modularität** `Partial`
  - The package is split into small modules and supports separate parser/AST/result layers.
  - Additional languages are not implemented yet, so extensibility is architectural rather than complete.

- [ ] **Performanz** `Partial`
  - Tree-sitter is used for structured parsing, which is a better basis than regex.
  - The current implementation does not reuse incremental parse state across files or runs.

## Scope / Abgrenzung

- [x] **Identifikation und Analyse only** `Done`
  - The tool analyzes repositories and exports findings.
  - It does not execute tests or simulate build environments.

## SDRM / Methodik

- [ ] **Konzeptioneller Rahmen** `Partial`
  - The codebase provides the implementation substrate, but the conceptual framework itself lives in the thesis text.

- [ ] **Systemarchitektur entwickeln** `Partial`
  - The folder structure reflects a modular architecture, but the full architecture is not represented as code-level enforcement.

- [ ] **Analyse & Systemdesign** `Partial`
  - Tree-sitter result models and parser helpers exist.
  - A full knowledge-base/schema layer or alternative solution comparison is not implemented in code.

- [ ] **Bau des (Prototyp-)Systems** `Done`
  - The Tree-sitter CLI and detectors are implemented as a working prototype.

- [ ] **Beobachtung & Evaluation des Systems** `Missing`
  - The codebase contains analysis tooling, but not the evaluation workflow itself.

## Evaluation Design

- [ ] **Differential Testing** `Missing`
  - There is no automated baseline-vs-AST comparison pipeline in the code.

- [ ] **Precision / Recall Measurement** `Missing`
  - The repository exports CSV results, but it does not compute evaluation metrics.

- [ ] **Automatisierte Cross-Language-Validierung** `Partial`
  - CMake and C++ are both analyzed.
  - There is no explicit test-target-to-source validation logic.

- [ ] **Qualitative Case Studies** `Missing`
  - No case-study workflow is implemented in the repository.

- [ ] **Evaluierung der Erweiterbarkeit und Modularität** `Partial`
  - The code is organized so that new parsers could be added.
  - A proof-of-concept integration for Python is not implemented yet.

## Current Tree-sitter Coverage Summary

- [x] CMake AST parsing
- [x] C++ AST parsing
- [x] AST-based test artifact extraction
- [x] CSV export of analysis results
- [ ] Explicit cross-language mapping
- [ ] Incremental parse reuse
- [ ] Python/R Tree-sitter support
