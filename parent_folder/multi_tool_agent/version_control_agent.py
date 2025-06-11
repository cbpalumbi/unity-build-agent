# version_control_agent.py
import os
from typing import Optional

from github import Github, Auth
from dotenv import load_dotenv

load_dotenv()
# --- Configuration for your specific repo ---
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") # Securely load from environment variable
REPO_OWNER = "cbpalumbi" 
REPO_NAME = "Google_ADK_Example_Game" 

# Initialize GitHub API client (do this once)
if GITHUB_TOKEN:
    auth = Auth.Token(GITHUB_TOKEN)
    g = Github(auth=auth)
    # Get the specific repository object once, as it's for a single repo
    try:
        # For an organization repo: g.get_organization(REPO_OWNER).get_repo(REPO_NAME)
        # For a user repo: g.get_user().get_repo(REPO_NAME) or g.get_repo(f"{REPO_OWNER}/{REPO_NAME}")
        # The f-string is usually safer for general user/org repos
        TARGET_REPO = g.get_repo(f"{REPO_OWNER}/{REPO_NAME}")
        print(f"[VC Tool] Connected to GitHub repo: {TARGET_REPO.full_name}")
    except Exception as e:
        TARGET_REPO = None
        print(f"Error connecting to GitHub repo {REPO_OWNER}/{REPO_NAME}: {e}")
else:
    TARGET_REPO = None
    print("GITHUB_TOKEN environment variable not set. Version Control tools will not function.")


# Mock data for demonstration purposes
MOCK_GIT_REPOS = {
    "my_unity_project": {
        "branches": {
            "main": {
                "latest_commit": "abcdef0123", "last_user": "alice",
                "commits": [
                    {"hash": "abcdef0123", "author": "alice", "message": "feat: Implement new main menu UI", "timestamp": "2025-06-11T10:00:00Z"},
                    {"hash": "fedcba9876", "author": "bob", "message": "fix: Critical bug fix for crash on startup", "timestamp": "2025-06-10T18:30:00Z"},
                    {"hash": "1234567890", "author": "charlie", "message": "refactor: Optimize asset loading", "timestamp": "2025-06-10T09:15:00Z"},
                    {"hash": "9876543210", "author": "alice", "message": "chore: Update build settings", "timestamp": "2025-06-09T14:00:00Z"},
                    {"hash": "543210fedc", "author": "bob", "message": "docs: Add README for new feature", "timestamp": "2025-06-08T11:00:00Z"},
                    {"hash": "0123456789", "author": "charlie", "message": "Initial commit", "timestamp": "2025-06-07T09:00:00Z"},
                ]
            },
            "develop": {
                "latest_commit": "abcdef9876", "last_user": "bob",
                "commits": [
                    {"hash": "abcdef9876", "author": "bob", "message": "feat: Add new enemy AI behavior", "timestamp": "2025-06-11T09:30:00Z"},
                    {"hash": "9876abcdef", "author": "alice", "message": "feat: Integrate new particle system", "timestamp": "2025-06-10T16:00:00Z"},
                ]
            },
            "feature/new-ui": {
                "latest_commit": "1234567890", "last_user": "alice",
                "commits": [
                    {"hash": "1234567890", "author": "alice", "message": "feat: Implement new user profile screen", "timestamp": "2025-06-11T08:00:00Z"},
                ]
            },
        },
        "users": {
            "alice": {"id": "alice@example.com", "default_branch": "feature/new-ui"},
            "bob": {"id": "bob@example.com", "default_branch": "develop"},
            "charlie": {"id": "charlie@example.com", "default_branch": "bugfix/login"},
        }
    }
}
# --- Tool Functions (defined as regular Python functions) ---
def _check_repo_connection():
    """Helper to ensure the repo is connected before making API calls."""
    if not TARGET_REPO:
        return {"error": "Version Control tools are not configured or failed to connect to the repository. Please set GITHUB_TOKEN and ensure repo details are correct."}
    return None

def get_latest_commit_on_branch(branch: str) -> str:
    """Retrieves the latest commit hash for a given branch in the specified repository.
    Use this when the user asks for 'latest' or 'head' of a branch.

    Args:
        branch: The name of the branch (e.g., "main", "feature/new-ui").
    Returns:
        The latest commit hash as a string, or an error message if the branch is not found.
    """
    error = _check_repo_connection()
    if error: return error.get("error")

    print(f"[VC Tool] Getting latest commit for branch: {branch} in repo: {TARGET_REPO.full_name}")
    try:
        # Get the branch object
        git_branch = TARGET_REPO.get_branch(branch)
        # Get the latest commit from that branch
        return git_branch.commit.sha
    except Exception as e:
        return f"Error: Branch '{branch}' not found or API error: {e}"

def resolve_branch_name(user_query: str) -> str:
    """Resolves a natural language query (e.g., 'dev branch', 'my code', 'main') into a precise Git branch name.
    Always try to resolve the branch name first if it's unclear from the user's intent.

    Args:
        user_query: The natural language string from the user.
    Returns:
        The resolved Git branch name, or an indication that it could not be resolved.
    """
    error = _check_repo_connection()
    if error: return error.get("error")

    print(f"[VC Tool] Resolving branch name for query: '{user_query}' in repo: {TARGET_REPO.full_name}")
    query_lower = user_query.lower()

    try:
        # Get all branches and try to find a match
        branches = TARGET_REPO.get_branches()
        branch_names = [b.name for b in branches]

        # Prioritize exact matches or common aliases
        for branch_name in branch_names:
            if branch_name.lower() == query_lower or \
               f"branch {branch_name.lower()}" in query_lower:
                return branch_name

        if "main" in query_lower or "master" in query_lower or "prod" in query_lower:
            if "main" in branch_names: return "main"
            if "master" in branch_names: return "master"
        if "dev" in query_lower or "develop" in query_lower:
            if "develop" in branch_names: return "develop"
            if "dev" in branch_names: return "dev" # Assuming 'dev' might be a branch name

        # Try to extract potential branch names (e.g., "feature/new-ui branch")
        for branch_name in branch_names:
            if branch_name.lower() in query_lower:
                return branch_name

        if "my" in query_lower:
            # This would require user context (e.g., a logged-in user or stored preference)
            # For now, it will be hard to resolve without knowing "who is 'my'"
            return "Need user context to resolve 'my' branch."

        return "Unable to resolve branch name from query. Available branches: " + ", ".join(branch_names)

    except Exception as e:
        return f"Error resolving branch name from API: {e}"

def resolve_git_user(user_query: str) -> str:
    """Resolves a natural language query (e.g., 'John's code', 'changes by Alice') into a Git username or ID.

    Args:
        user_query: The natural language string from the user.
    Returns:
        The resolved Git user ID, or an indication that it could not be resolved.
    """
    error = _check_repo_connection()
    if error: return error.get("error")

    print(f"[VC Tool] Resolving Git user for query: '{user_query}' in repo: {TARGET_REPO.full_name}")
    query_lower = user_query.lower()

    # PyGithub doesn't have a direct "list all users in a repo" API
    # You'd typically find users from commits or contributors.
    # For a small, known team, you might hardcode a mapping or search commit authors.
    # Let's mock finding an author from recent commits for this example.
    try:
        recent_commits = TARGET_REPO.get_commits() # Gets up to 30 by default
        for commit in recent_commits:
            author = commit.author
            if author and (author.login.lower() in query_lower or author.name.lower() in query_lower):
                return author.login # Return GitHub username/login
        
        # Fallback to a predefined list if you have one
        known_users = {"alice": "alice", "bob": "bob", "charlie": "charlie"} # Map display name to GitHub login
        for display_name, github_login in known_users.items():
            if display_name.lower() in query_lower or github_login.lower() in query_lower:
                return github_login

        return "Unable to resolve Git user from query."
    except Exception as e:
        return f"Error resolving Git user from API: {e}"


def get_commit_details(commit_id: str) -> dict:
    """Retrieves detailed information (branch, author, message, timestamp) for a specific Git commit ID.
    Use this when the user provides a commit hash and asks for more details.

    Args:
        commit_id: The full or partial commit hash.
    Returns:
        A dictionary with commit details, or an error message.
    """
    error = _check_repo_connection()
    if error: return error.get("error")

    print(f"[VC Tool] Getting commit details for ID: {commit_id} in repo: {TARGET_REPO.full_name}")
    try:
        # PyGithub's get_commit can often resolve partial hashes if unique
        commit = TARGET_REPO.get_commit(commit_id)
        return {
            "hash": commit.sha,
            "author": commit.author.login if commit.author else "Unknown",
            "message": commit.commit.message,
            "timestamp": commit.commit.author.date.isoformat() + "Z" # ISO 8601 format
        }
    except Exception as e:
        return {"error": f"Commit '{commit_id}' not found or API error: {e}"}

def list_available_branches() -> list:
    """Lists all available branches in the specified repository.
    Use this when the user asks 'What branches are there?' or 'List branches'.

    Args:
        repo_name: The name of the repository (defaults to "my_unity_project").
    Returns:
        A list of branch names, or an error message.
    """
    error = _check_repo_connection()
    if error: return error.get("error")

    print(f"[VC Tool] Listing branches for repo: {TARGET_REPO.full_name}")
    try:
        branches = TARGET_REPO.get_branches()
        return sorted([b.name for b in branches])
    except Exception as e:
        return [f"Error listing branches from API: {e}"]

def list_recent_commits_on_branch(branch: str, num_commits: int = 5) -> list:
    """Lists the most recent commits on a given branch, similar to 'git log'.
    Use this when the user asks for a commit history or recent changes on a branch.

    Args:
        branch: The name of the branch to get commits from.
        num_commits: The number of most recent commits to retrieve (defaults to 5).
    Returns:
        A list of dictionaries, where each dictionary contains commit details (hash, author, message, timestamp).
        Returns an empty list or an error message if the branch is not found.
    """
    error = _check_repo_connection()
    if error: return error.get("error")

    print(f"[VC Tool] Listing {num_commits} recent commits for branch: {branch} in repo: {TARGET_REPO.full_name}")
    try:
        # Get commits for the specified branch, limit to num_commits
        commits = TARGET_REPO.get_commits(sha=branch)[:num_commits] # sha=branch gets commits from head of branch
        
        results = []
        for commit in commits:
            results.append({
                "hash": commit.sha,
                "author": commit.author.login if commit.author else "Unknown",
                "message": commit.commit.message,
                "timestamp": commit.commit.author.date.isoformat() + "Z"
            })
        return results
    except Exception as e:
        return [{"error": f"Error listing commits for branch '{branch}' from API: {e}"}]

def resolve_latest_commit(branch: str, user_query: Optional[str] = None) -> dict:
    """
    Resolves the latest commit on a given branch, optionally filtered by a specific user.
    Use this when the user asks for 'the latest commit', 'my latest commit', or 'Jeff's latest commit'.

    Args:
        branch: The name of the branch to check (e.g., "main", "develop").
        user_query: Optional. A natural language query to resolve the user (e.g., "my", "Jeff", "Alice").
                    If provided, the tool will try to find the latest commit by that user on the branch.
    Returns:
        A dictionary containing the commit hash, author, message, and timestamp,
        or an error message if the branch/user/commit is not found.
    """
    print(f"[VC Tool] Resolving latest commit for branch: {branch}")

    target_user_id = None
    if user_query:
        # Re-use your existing resolve_git_user tool to get the precise user ID/login
        resolved_user_id = resolve_git_user(user_query) # Assuming this returns a string like "alice" or "bob"
        if "Unable to resolve" in resolved_user_id or "Error" in resolved_user_id:
            return {"error": f"Could not resolve user '{user_query}': {resolved_user_id}. Please try again."}
        target_user_id = resolved_user_id
        print(f"[VC Tool] Resolved user '{user_query}' to '{target_user_id}'.")


    # --- Logic for fetching commits (replace with real API calls if not already) ---
    repo = MOCK_GIT_REPOS.get("my_unity_project") # Or use TARGET_REPO for real API
    if not repo:
        return {"error": "Repository not configured."}

    branch_info = repo["branches"].get(branch)
    if not branch_info or not branch_info.get("commits"):
        return {"error": f"Branch '{branch}' not found or has no commits."}

    # Iterate through commits to find the latest, potentially filtered by user
    # Assumes commits are already sorted by timestamp (most recent first) in mock data
    for commit in branch_info["commits"]:
        commit_author = commit.get("author") # Or commit.author.login for PyGithub

        if target_user_id:
            # If a user was specified, only consider commits by that user
            if commit_author and commit_author.lower() == target_user_id.lower():
                return commit # Return the first (latest) matching commit
        else:
            # If no user was specified, just return the absolute latest commit
            return commit

    if target_user_id:
        return {"error": f"No commits found by user '{target_user_id}' on branch '{branch}'."}
    else:
        return {"error": f"No latest commit found on branch '{branch}'."}


# List of all Version Control related functions to be passed as tools
VERSION_CONTROL_TOOL_FUNCTIONS = [
    get_latest_commit_on_branch,
    resolve_branch_name,
    resolve_git_user,
    get_commit_details,
    list_available_branches,
    list_recent_commits_on_branch,
    resolve_latest_commit
]
