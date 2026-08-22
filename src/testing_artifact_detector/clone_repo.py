"""
This module contains functionality to clone a Git repository.
The main function is obviously `clone_repo`.
"""
import os
import time
import subprocess
import random
from typing import Optional, Tuple

# Prevents git from blocking on an interactive username/password prompt when a
# repository is private - it fails fast instead, which is what
# is_repo_accessible() relies on.
_GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}


def is_repo_accessible(repo_url: str, timeout: int = 15) -> Tuple[bool, str]:
    """
    Check whether a Git repository can be cloned before actually attempting it.

    :param repo_url: URL of the repository to check.
    :param timeout: Seconds to wait before giving up on the check.
    :return: (True, "") if the repository is accessible, otherwise (False, reason).
    """
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--exit-code", repo_url, "HEAD"],
            env=_GIT_ENV,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, "timed out while checking repository accessibility"

    if result.returncode == 0:
        return True, ""

    return False, "repository appears to be private, deleted, or otherwise inaccessible"


def clone_repo(project_id : str, repo_url : str, clone_path : str) -> Optional[Tuple[bool, str]]:
    """
    Clones the given Git repository into the specified path.

    :param project_id: The project ID (usually JOSS suffix) of the project.
    :param repo_url: URL of the repository to clone.
    :param clone_path: Path where repositories should be cloned into.
    :return: None on error and a boolean * string tuple which states if the repo was freshly cloned
             and in what path.
    """
    try:
        # Ensuring the clone path exists
        os.makedirs(clone_path, exist_ok=True)

        # Constructing the full clone path
        full_clone_path = os.path.join(clone_path, project_id)

        # Running the git clone command if the directory exists but is empty
        if os.path.exists(full_clone_path) and os.listdir(full_clone_path):
            print(f"Directory for repo {repo_url} already exists in {full_clone_path}")
            return False, full_clone_path

        accessible, reason = is_repo_accessible(repo_url)
        if not accessible:
            print(f"Skipping clone of {repo_url}: {reason}")
            return None

        time.sleep(random.uniform(2.0, 5.0))
        subprocess.run(["git", "clone", repo_url, full_clone_path], check=True)
        print(f"Successfully cloned: {repo_url} into {full_clone_path}")
        return True, full_clone_path

    except subprocess.CalledProcessError as e:
        print(f"An error occurred while cloning the repository: {e}")
        return None
