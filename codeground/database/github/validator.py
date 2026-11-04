"""
URL validation and sanitization for GitHub repositories.
Prevents shell injection and rejects invalid remote targets.
"""
import re
from urllib.parse import urlparse
from typing import Tuple

# Matches standard GitHub repository formats:
# https://github.com/owner/repo or https://github.com/owner/repo.git
GITHUB_URL_PATTERN = re.compile(
    r"^https://github\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+?)(?:\.git)?/?$"
)

# Strict branch naming rules according to git-check-ref-format standards
BRANCH_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+$")


class GitHubValidationError(ValueError):
    """Raised when repository URL or branch fails security or format validation."""
    pass


def validate_github_url(url: str) -> Tuple[str, str, str]:
    """
    Validates a GitHub URL and extracts the canonical components.
    
    Returns:
        (canonical_url, owner, repo_name)
    Raises:
        GitHubValidationError if the URL is invalid or unsafe.
    """
    if not url or not isinstance(url, str):
        raise GitHubValidationError("Repository URL must be a non-empty string.")

    cleaned_url = url.strip()

    parsed = urlparse(cleaned_url)
    if parsed.scheme != "https" or parsed.netloc != "github.com":
        raise GitHubValidationError("Only secure HTTPS URLs from github.com are accepted.")

    match = GITHUB_URL_PATTERN.match(cleaned_url)
    if not match:
        raise GitHubValidationError(
            "Invalid GitHub repository URL format. Example: https://github.com/owner/repo"
        )

    owner, raw_repo_name = match.groups()

    # Reject path traversal artifacts in repo/owner names
    if ".." in owner or ".." in raw_repo_name:
        raise GitHubValidationError("Path traversal sequences are strictly rejected.")

    repo_name = raw_repo_name.removesuffix(".git")
    canonical_url = f"https://github.com/{owner}/{repo_name}.git"

    return canonical_url, owner, repo_name


def validate_branch_name(branch: str) -> str:
    """
    Validates git branch names to prevent command-line flag injection (e.g. --upload-pack).
    """
    cleaned_branch = branch.strip()
    if not cleaned_branch:
        return "main"

    if cleaned_branch.startswith("-"):
        raise GitHubValidationError("Branch name cannot begin with a dash.")

    if not BRANCH_NAME_PATTERN.match(cleaned_branch):
        raise GitHubValidationError("Branch name contains invalid or unsafe characters.")

    return cleaned_branch
    