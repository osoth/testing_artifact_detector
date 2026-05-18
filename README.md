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

# Project Structure:

```
├── LICENSE
├── pyproject.toml
├── README.md
├── src
│   └── testing_artifact_detector
│       ├── cli.py
│       ├── clone_repo.py # Git cloning infrastructure
│       ├── config_parsers # Scripts for parsing configuration files
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
│       ├── __init__.py
│       ├── __main__.py
│       └── repo_languages.py # cloc based implementation for language analysis
└── test_suite
    ├── __init__.py
    └── unit
        ├── __init__.py
        ├── test_data
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

The tool will produce identical results for repeated runs on the same corpus (same input CSV, already cloned repositories),
modulo ordering in the fields `py_testing_types`, `r_testing_types`, and`cpp_testing_types`. For checking the consistency,
we propose to use the tool `csv-diff` with the parameter `--key joss_id`, e.g.

> csv_diff run1.csv run2.csv --key joss_id

which will show the differences in the CSV files. The only differences should be the beforementioned fields
concerning the order.