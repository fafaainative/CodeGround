"""
Git repository fetcher with sandboxed subprocess execution,
size limit enforcement, and directory tree construction.
"""
import subprocess
import shutil
import os
from pathlib import Path
from typing import Dict, Any, List
from config.settings import (
    CLONES_DIR,
    MAX_REPO_SIZE_MB,
    SUBPROCESS_TIMEOUT_SECONDS
)
from codeground.github.validator import validate_github_url, validate_branch_name, GitHubValidationError


class FetchError(RuntimeError):
    """Raised when repository cloning or file scanning fails."""
    pass


class RepositoryFetcher:
    def __init__(self, base_clone_dir: Path = CLONES_DIR):
        self.base_clone_dir = base_clone_dir
        self.base_clone_dir.mkdir(parents=True, exist_ok=True)

    def get_target_path(self, project_id: int) -> Path:
        """Determines the isolated clone path for a specific project ID."""
        target = (self.base_clone_dir / f"proj_{project_id}").resolve()
        
        # Enforce sandbox containment: path must reside strictly within base_clone_dir
        if not str(target).startswith(str(self.base_clone_dir.resolve())):
            raise FetchError("Target directory escape detected.")
            
        return target

    def calculate_directory_size_mb(self, path: Path) -> float:
        """Calculates total disk space used by a directory in megabytes."""
        total_bytes = 0
        for root, _, files in os.walk(path):
            for f in files:
                fp = os.path.join(root, f)
                if not os.path.islink(fp):
                    total_bytes += os.path.getsize(fp)
        return total_bytes / (1024 * 1024)

    def clone_repository(self, project_id: int, repo_url: str, branch: str = "main") -> Path:
        """
        Executes a secure shallow clone (`--depth 1`) using an explicit argument list.
        """
        canonical_url, _, _ = validate_github_url(repo_url)
        safe_branch = validate_branch_name(branch)
        target_path = self.get_target_path(project_id)

        # Clear any prior state for this project
        if target_path.exists():
            shutil.rmtree(target_path, ignore_errors=True)

        cmd = [
            "git",
            "clone",
            "--depth", "1",
            "--branch", safe_branch,
            "--single-branch",
            canonical_url,
            str(target_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
                check=False
            )
        except subprocess.TimeoutExpired:
            shutil.rmtree(target_path, ignore_errors=True)
            raise FetchError(f"Cloning timed out after {SUBPROCESS_TIMEOUT_SECONDS}s.")
        except FileNotFoundError:
            raise FetchError("Git executable not found in system PATH.")

        if result.returncode != 0:
            shutil.rmtree(target_path, ignore_errors=True)
            err_msg = result.stderr.strip() or result.stdout.strip()
            raise FetchError(f"Git clone failed: {err_msg}")

        # Enforce storage limits
        repo_size = self.calculate_directory_size_mb(target_path)
        if repo_size > MAX_REPO_SIZE_MB:
            shutil.rmtree(target_path, ignore_errors=True)
            raise FetchError(
                f"Repository size ({repo_size:.2f} MB) exceeds limit of {MAX_REPO_SIZE_MB} MB."
            )

        return target_path

    def build_file_tree(self, root_path: Path, max_depth: int = 4) -> List[Dict[str, Any]]:
        """
        Builds a structured hierarchy of files and directories,
        filtering out VCS and cache directories.
        """
        ignored_directories = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "node_modules"}
        results = []

        root_path = root_path.resolve()

        for dirpath, dirnames, filenames in os.walk(root_path):
            # Prune ignored directories in-place
            dirnames[:] = [d for d in dirnames if d not in ignored_directories]

            current_p = Path(dirpath)
            depth = len(current_p.relative_to(root_path).parts)
            if depth > max_depth:
                dirnames.clear()
                continue

            for f in sorted(filenames):
                file_p = current_p / f
                rel_path = file_p.relative_to(root_path)
                results.append({
                    "path": str(rel_path),
                    "name": f,
                    "extension": file_p.suffix.lower(),
                    "size_bytes": file_p.stat().st_size if file_p.exists() else 0
                })

        return sorted(results, key=lambda x: x["path"])
