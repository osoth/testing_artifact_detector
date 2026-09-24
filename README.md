# TestingArtifactDetector

This is a command line tool that clones and analyses Git repositories.
Its aim is to identify testing artifacts in those repositories, with specialised
components for programming languages.

While its functionality could in principle be applied to separate Git repositories,
it currently relies on the output of the [joss-repo-miner](https://github.com/SE-UP/joss-repo-miner).

# Dependencies

This tool was built and tested using Python version `3.12` and `pytest` version `7.4.4`.
Other Python dependencies are pandas and the used version was `2.1.4`.
The tool itself requires a current version of `cloc` and works with version `1.98`.

# Installation

After cloning this repo into `dir`, the installation can be done with

```
cd dir
pip install -e .
```    

where `-e` unlocks the "developer mode".

# Running

## Basic use (one-shot)

To run it on all a CSV file `foo/joss_repo_miner_output.csv`, you can use the following command

> testing-artifact-detector --in-file foo/joss_repo_miner_output.csv --out-file foo/testing_artifact_detector_output.csv --clone-dir bar/

This runs the cloning and analysis on the file `foo/joss_repo_miner_output.csv` and writes the output to
`foo/testing_artifact_detector_output.csv`. Repositories are respectively cloned into `bar` as separate directories
with their `joss_id` as directory name.

Further details and options are given by

> testing-artifact-detector --help

# Advanced use

For bigger data sets (e.g. the whole JOSS corpus), it can make sense to separate the cloning process from the analysis.
In this case, the separation can be enforced by calling 

> testing-artifact-detector --in-file foo/joss_repo_miner_output.csv --out-file foo/testing_artifact_detector_joss_repo_miner_clone_output.csv --clone-dir bar/ --clone-only True

which does only the cloning-step.
In the next step

> testing-artifact-detector --in-file foo/testing_artifact_detector_joss_repo_miner_clone_output.csv --out-file foo/testing_artifact_detector_joss_repo_miner_output.csv --clone-dir bar/ --assume-cloned True

the cloned repositories are analysed and the final output is generated.

The tool provides an option `--cloc-config` to specify the languages to exclude by cloc. This parameter
takes the path to a configuration file which contains each excluded language in one line.
A sample configuration, i.e. the exclusions used for the eScience 2026 submission, can be found
in the root folder. If no configuration is given, default exclusions are set and printed to the
command line.

# Tree-sitter version (AST-based analysis)

An alternative, Tree-sitter/AST-based analysis path for CMake test-artifact detection
is available via `testing-artifact-detector-ts` (implemented in `cli2.py`, using the
modules under `src/testing_artifact_detector/treesitter_detector/`). It takes the same
kind of input/output as the regex-based tool above:

> testing-artifact-detector-ts --in-file foo/joss_repo_miner_output.csv --out-file foo/treesitter_output.csv --clone-dir bar/

It supports the same `--clone-dir`, `--assume-cloned`, `--clone-only`, and
`--cloc-config` options as `testing-artifact-detector` (see "Advanced use" above),
so the same one-shot vs. clone-then-analyse workflow applies. If repositories were
already cloned into `bar/` by a prior `testing-artifact-detector` run, that same
clone directory can be reused directly - no need to clone twice.

Beyond what the regex-based tool can express, it also resolves CMake wrapper
macros: a `macro(...)`/`function(...)` defined anywhere in the repository whose body
calls `add_test`/`gtest_discover_tests` is followed transitively, so calling such a
wrapper counts as registering a test. Because this requires telling a definition
apart from a call site, it is reported in its own columns
(`cmake_tests_via_wrapper`, `cmake_test_wrappers`, `cmake_unused_test_wrappers`)
rather than folded into `cmake_tests_found`. Wrappers defined outside the repository
(e.g. `dune_add_test` from dune-common) cannot be resolved without the build
environment, which is out of scope for this tool.

CMake is the tool's subject, matching the scope of the regex-based detector it is
compared against. The C++ source analysis is optional and lives in its own subpackage,
`treesitter_detector/cpp/`; it is kept as a demonstration that a second language plugs
in by adding an extraction and a result module, without touching the CMake analysis.
`--cmake-only` skips it entirely:

> testing-artifact-detector-ts --in-file foo/joss_repo_miner_output.csv --out-file foo/treesitter_output.csv --clone-dir bar/ --cmake-only

The C++ columns are then left empty rather than set to `False`, so "not analysed" stays
distinguishable from "analysed, found nothing". Roughly 97% of the parsing time is spent
on C++ sources, so this is considerably faster when iterating on the CMake analysis.

`--inventory-out` additionally writes a structured test inventory as JSON Lines, one
repository per line:

> testing-artifact-detector-ts --in-file foo/joss_repo_miner_output.csv --out-file foo/treesitter_output.csv --clone-dir bar/ --cmake-only --inventory-out foo/test_inventory.jsonl

Where the CSV carries per-repository counts, the inventory carries the reconstruction
itself: every test with its name, the wrapper chain that registered it, the definition
and call sites, the executable target and its source files, what drives the test
(a project binary or an external tool such as python or mpiexec), and the `if()`
condition guarding it.

Further details and options are given by

> testing-artifact-detector-ts --help

# Comparing the regex and Tree-sitter results

`comp_rgx_ts.py` (in `src/testing_artifact_detector/evaluation/`) compares
the CSV outputs of the two tools above and reports, per test-artifact indicator,
where they agree or disagree. It only compares the fields both tools derive the
same way (CMake-file-based signals: `find_package`, `add_test`,
`gtest_discover_tests`); the Tree-sitter tool's additional C++ source-level fields
have no regex-tool equivalent and are reported separately, for information only.

Run it after producing both output CSVs:

> testing-artifact-detector-compare --regex-file foo/testing_artifact_detector_output.csv --ts-file foo/treesitter_output.csv --diff-out foo/differences.csv

The same script can also be called directly, without installing the package:

> python src/testing_artifact_detector/evaluation/comp_rgx_ts.py --regex-file foo/testing_artifact_detector_output.csv --ts-file foo/treesitter_output.csv --diff-out foo/differences.csv

`--diff-out` is optional; when given, every disagreeing or missing-data row is
written to that CSV for manual review. See `CHANGELOG.md` for a worked example and
the resulting numbers over the full JOSS dataset.

That script answers "does the AST parse better than the regex, given the same
heuristics?". To instead ask "how much more does the AST-based tool find in total?",
use the deep comparison, which compares the baseline against everything the detector
knows - reachability-aware CMake analysis including wrapper resolution (level 1), and
additionally the C++ source-level scan (level 2):

> testing-artifact-detector-compare-deep --regex-file foo/testing_artifact_detector_output.csv --ts-file foo/treesitter_output.csv --diff-out foo/differences_deep.csv

Both scripts share their comparison machinery via `comparison.py`.

# Project Structure:

```
├── escience_cloc.cfg # cloc config for reproducing eScience2026 results
├── LICENSE
├── pyproject.toml
├── README.md
├── src
│   └── testing_artifact_detector
│       ├── cli.py
│       ├── clone_repo.py # Git cloning infrastructure
│       ├── config_parsers # Scripts for parsing configuration files
|       |   ├── cloc_config_parser.py
│       │   ├── cpp_test_config_parser.py
│       │   ├── __init__.py
│       │   ├── python_test_config_parser.py
│       │   └── r_test_config_parser.py
│       ├── detectors # Scripts for searching for testing artifacts, uses config_parsers
│       │   ├── check_cpp_test_artifacts.py
│       │   ├── check_python_test_artifacts.py
│       │   ├── check_r_test_artifacts.py
│       │   ├── check_test_types.py
│       │   ├── __init__.py
│       │   └── util.py
│       ├── evaluation # Compares the two detectors' outputs, not a detector itself
│       │   ├── comparison.py # Shared machinery of the two comparison scripts
│       │   ├── comp_rgx_ts.py # Strict comparison: same heuristics, AST vs regex
│       │   ├── comp_rgx_ts_deep.py # Full-capability comparison
│       │   └── __init__.py
│       ├── treesitter_detector # AST-based analysis (see "Tree-sitter version" above)
│       │   ├── cmake_ast.py # Node extraction via the Tree-sitter query API
│       │   ├── cmake_graph.py # Evaluation order: which files CMake actually reads
│       │   ├── cmake_parser.py # Orchestrates the syntactic and the semantic pass
│       │   ├── cmake_results.py # Data model of the analysis results
│       │   ├── cmake_semantics.py # Expansion, argument binding, classification
│       │   ├── common.py
│       │   ├── cpp # OPTIONAL, not part of the CMake detection path
│       │   │   ├── cpp_ast.py
│       │   │   ├── cpp_parser.py
│       │   │   ├── cpp_results.py
│       │   │   └── __init__.py
│       │   ├── __init__.py
│       │   ├── inventory.py # Serialises the test inventory as JSON Lines
│       │   ├── source_collector.py
│       │   └── tree_sitter_backend.py # Parser construction and query caching
│       ├── cli2.py # Entry point of the Tree-sitter version
│       ├── __init__.py
│       ├── __main__.py
│       └── repo_languages.py # cloc based implementation for language analysis
└── test_suite
    ├── __init__.py
    └── unit
        ├── __init__.py
        ├── test_data
        │   ├── cloc.cfg
        │   ├── config_data
        │   │   ├── Python # Sample test configuration files and source files for Python
        │   │   │   ├── empty_pytest.toml
        │   │   │   ├── pyproject.toml
        │   │   │   ├── pytest.ini
        │   │   │   ├── test
        │   │   │   │   └── test_unit.py
        │   │   │   └── tests
        │   │   │       ├── general_test.py
        │   │   │       ├── invalid_test_file.py
        │   │   │       └── unit
        │   │   │           └── test_unit.py
        │   │   └── R # Sample test configuration files for R
        │   │       ├── multi
        │   │       │   └── DESCRIPTION
        │   │       ├── runit
        │   │       │   └── DESCRIPTION
        │   │       ├── testthat
        │   │       │   └── DESCRIPTION
        │   │       └── tinytest
        │   │           └── DESCRIPTION
        │   └── sample_cloc.json
        ├── test_python_test_artifact_check.py
        ├── test_python_test_config_parsing.py
        ├── test_repo_languages.py
        └── test_r_test_config_parsing.py
```

# Data Validation and Consistency

The tool ensures the following properties:

- it will produce identical results for repeated runs on the same corpus (same input CSV, already cloned repositories).