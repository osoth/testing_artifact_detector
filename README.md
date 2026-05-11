# TestingArtifactDetector

This is a command line tool that clones and analyses Git repositories.
Its aim is to identify testing artifacts in those repositories, with specialised
components for programming languages.

While its functionality could in principle be applied to separate Git repositories,
it currently relies on the output of the [joss-repo-miner](https://github.com/SE-UP/joss-repo-miner).

# Installation

The installation can be done with

> pip install -e .    

where `-e` unlocks the "developer mode".

# Running

To run it on all a CSV file `foo/joss_repo_miner_output.csv`, you can use the following command

> testing-artifact-detector --in-file foo/joss_repo_miner_output.csv --out-file foo/testing_artifact_detector_output.csv

Further details and options are given by

> testing-artifact-detector --help

# Project Structure:

```
TestingArtifactDetector/
├─ src/
│  └─ testing_artifact_detector/
│     ├─ __init__.py
│     ├─ __main__.py
│     ├─ cli.py
│     ├─ clone_repo.py
│     └─ repo_languages.py
├─ test_suite/
│  ├─ unit/
│  │  ├─ test_data/
│  │  │  └─ sample_cloc.json
│  │  ├─ __init__.py
│  │  └─ test_repo_languages.py
│  └─ __init__.py
├─ LICENSE
├─ pyproject.toml
└─ README.md
```

requirements.txt is generated using pipreqs.

