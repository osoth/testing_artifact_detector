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

CMake is this tool's subject, matching the scope of the regex-based detector it is
compared against. There is no C++ path.

## What it adds over the regex-based tool

A regex answers whether a test command is written somewhere. This tool answers whether
that place is actually evaluated when CMake processes the project. Two things can
prevent it, and neither is visible in the text:

- the file is never loaded from the top-level `CMakeLists.txt`, or
- the `macro`/`function` whose body holds the command is never called.

The unit reported is therefore a **site**: a place where a test command is written,
together with the verdict on whether it is reached. A site is not a test - one inside a
`foreach()` registers as many tests as the loop has iterations, and that number is
deliberately not determined. The counts in the output are counts of sites.

Because this goes beyond what the regex baseline can express, the verdict is reported in
its own columns (`cmake_tests_reachable`, `cmake_test_sites`, `cmake_sites_invoked`,
`cmake_sites_file_unreachable`, `cmake_sites_wrapper_uncalled`) rather than folded into
`cmake_tests_found`, which keeps the baseline heuristics unchanged. Wrappers defined
outside the repository (e.g. `dune_add_test` from dune-common) cannot be recognised
without the build environment, which is out of scope for this tool.

## Structured site inventory

`--inventory-out` additionally writes the sites as JSON Lines, one repository per line:

> testing-artifact-detector-ts --in-file foo/joss_repo_miner_output.csv --out-file foo/treesitter_output.csv --clone-dir bar/ --inventory-out foo/test_sites.jsonl

Where the CSV carries per-repository counts, the inventory carries each site: its file
and line, whether it is an `add_test` or a `gtest_discover_tests`, the verdict, the
enclosing wrapper if any, the `if()` conditions it sits under (recorded as written, not
evaluated), and how deeply it is nested in `foreach()` loops.

Further details and options are given by

> testing-artifact-detector-ts --help

# Comparing the regex and Tree-sitter results

`comp_rgx_ts.py` (in `src/testing_artifact_detector/evaluation/`) compares
the CSV outputs of the two tools above and reports, per test-artifact indicator,
where they agree or disagree. It only compares the fields both tools derive the
same way (CMake-file-based signals: `find_package`, `add_test`,
`gtest_discover_tests`).

Run it after producing both output CSVs:

> testing-artifact-detector-compare --regex-file foo/testing_artifact_detector_output.csv --ts-file foo/treesitter_output.csv --diff-out foo/differences.csv

The same script can also be called directly, without installing the package:

> python src/testing_artifact_detector/evaluation/comp_rgx_ts.py --regex-file foo/testing_artifact_detector_output.csv --ts-file foo/treesitter_output.csv --diff-out foo/differences.csv

`--diff-out` is optional; when given, every disagreeing or missing-data row is
written to that CSV for manual review. `CHANGELOG.md` section 4 gives the resulting
numbers over the full JOSS dataset.

The script also reports, for information only, the resolved wrappers and the ones
never called.

The comparison machinery lives in `comparison.py`.

# Project Structure:

```
├── escience_cloc.cfg # cloc config for reproducing eScience2026 results
├── LICENSE
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── src
│   └── testing_artifact_detector
│       ├── cli.py # Entry point of the regex-based tool
│       ├── cli2.py # Entry point of the Tree-sitter version
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
│       │   └── __init__.py
│       ├── treesitter_detector # AST-based analysis (see "Tree-sitter version" above)
│       │   ├── cmake_ast.py # Node extraction via the Tree-sitter query API
│       │   ├── cmake_graph.py # Evaluation order: which files CMake actually reads
│       │   ├── cmake_parser.py # Orchestration and the wrapper call graph
│       │   ├── cmake_results.py # Data model, including TestSite
│       │   ├── cmake_sites.py # Verdict and context per test site
│       │   ├── common.py
│       │   ├── __init__.py
│       │   ├── sites_inventory.py # Serialises the sites as JSON Lines
│       │   ├── source_collector.py
│       │   └── tree_sitter_backend.py # Parser construction and query caching
│       ├── __init__.py
│       ├── __main__.py
│       └── repo_languages.py # cloc based implementation for language analysis
└── test_suite
    ├── __init__.py
    └── unit
        ├── conftest.py # Shared parser fixtures
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
        ├── test_r_test_config_parsing.py
        ├── test_repo_languages.py
        ├── test_treesitter_cmake.py # Tests of the Tree-sitter CMake detector
```

# Data Validation and Consistency

The tool ensures the following properties:

- it will produce identical results for repeated runs on the same corpus (same input CSV, already cloned repositories).