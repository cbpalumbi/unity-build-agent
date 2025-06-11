# version_control_agent.py
import re

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

def get_latest_commit_on_branch(branch: str, repo_name: str = "my_unity_project") -> str:
    """Retrieves the latest commit hash for a given branch in a specified repository.
    Use this when the user asks for 'latest' or 'head' of a branch.

    Args:
        branch: The name of the branch (e.g., "main", "feature/new-ui").
        repo_name: The name of the repository (defaults to "my_unity_project").
    Returns:
        The latest commit hash as a string, or an error message if the branch is not found.
    """
    print(f"[VC Tool] Getting latest commit for branch: {branch} in repo: {repo_name}")
    repo = MOCK_GIT_REPOS.get(repo_name)
    if not repo:
        return f"Error: Repository '{repo_name}' not found."
    
    branch_info = repo["branches"].get(branch)
    if branch_info:
        return branch_info["latest_commit"]
    return f"Error: Branch '{branch}' not found in repository '{repo_name}'."

def resolve_branch_name(user_query: str, repo_name: str = "my_unity_project") -> str:
    """Resolves a natural language query (e.g., 'dev branch', 'my code', 'main') into a precise Git branch name.
    Always try to resolve the branch name first if it's unclear from the user's intent.

    Args:
        user_query: The natural language string from the user.
        repo_name: The name of the repository (defaults to "my_unity_project").
    Returns:
        The resolved Git branch name, or an indication that it could not be resolved.
    """
    print(f"[VC Tool] Resolving branch name for query: '{user_query}' in repo: {repo_name}")
    query_lower = user_query.lower()
    repo = MOCK_GIT_REPOS.get(repo_name)
    if not repo:
        return f"Error: Repository '{repo_name}' not found."

    # Try exact matches first
    for branch_name in repo["branches"]:
        if branch_name.lower() == query_lower or \
           f"branch {branch_name.lower()}" in query_lower:
            return branch_name

    # Common aliases
    if "main" in query_lower or "master" in query_lower or "prod" in query_lower:
        return "main" if "main" in repo["branches"] else "master"
    if "dev" in query_lower or "develop" in query_lower:
        return "develop" if "develop" in repo["branches"] else "main"
    
    # Try to extract potential branch names (e.g., "feature/new-ui branch")
    for branch_name in repo["branches"]:
        if branch_name.lower() in query_lower:
            return branch_name

    # If user-specific logic is needed (e.g., "my default branch")
    # This would require user_id from ctx passed to the tool,
    # or the tool accessing a user-profile service.
    if "my" in query_lower:
        return "Need user context to resolve 'my' branch."

    return "Unable to resolve branch name from query."

def resolve_git_user(user_query: str, repo_name: str = "my_unity_project") -> str:
    """Resolves a natural language query (e.g., 'John's code', 'changes by Alice') into a Git username or ID.

    Args:
        user_query: The natural language string from the user.
        repo_name: The name of the repository (defaults to "my_unity_project").
    Returns:
        The resolved Git user ID, or an indication that it could not be resolved.
    """
    print(f"[VC Tool] Resolving Git user for query: '{user_query}' in repo: {repo_name}")
    query_lower = user_query.lower()
    repo = MOCK_GIT_REPOS.get(repo_name)
    if not repo:
        return f"Error: Repository '{repo_name}' not found."

    for user_name, user_info in repo["users"].items():
        if user_name.lower() in query_lower or user_info["id"].lower() in query_lower:
            return user_info["id"]

    return "Unable to resolve Git user from query."

def get_commit_details(commit_id: str, repo_name: str = "my_unity_project") -> dict:
    """Retrieves detailed information (branch, author, message, timestamp) for a specific Git commit ID.
    Use this when the user provides a commit hash and asks for more details.

    Args:
        commit_id: The full or partial commit hash.
        repo_name: The name of the repository (defaults to "my_unity_project").
    Returns:
        A dictionary with commit details, or an error message.
    """
    print(f"[VC Tool] Getting commit details for ID: {commit_id} in repo: {repo_name}")
    repo = MOCK_GIT_REPOS.get(repo_name)
    if not repo:
        return {"error": f"Repository '{repo_name}' not found."}

    for branch, info in repo["branches"].items():
        if info["latest_commit"].startswith(commit_id):
            return {
                "commit_id": info["latest_commit"],
                "branch": branch,
                "author": info["last_user"],
                "message": f"Mock commit message for {info['latest_commit']}",
                "timestamp": "2025-06-11T10:00:00Z"
            }
    return {"error": f"Commit '{commit_id}' not found in repository '{repo_name}'."}

def list_available_branches(repo_name: str = "my_unity_project") -> list:
    """Lists all available branches in the specified repository.
    Use this when the user asks 'What branches are there?' or 'List branches'.

    Args:
        repo_name: The name of the repository (defaults to "my_unity_project").
    Returns:
        A list of branch names, or an error message.
    """
    print(f"[VC Tool] Listing branches for repo: {repo_name}")
    repo = MOCK_GIT_REPOS.get(repo_name)
    if not repo:
        return [f"Error: Repository '{repo_name}' not found."]
    
    return sorted(list(repo["branches"].keys()))

def list_recent_commits_on_branch(branch: str, num_commits: int = 5, repo_name: str = "my_unity_project") -> list:
    """Lists the most recent commits on a given branch, similar to 'git log'.
    Use this when the user asks for a commit history or recent changes on a branch.

    Args:
        branch: The name of the branch to get commits from.
        num_commits: The number of most recent commits to retrieve (defaults to 5).
        repo_name: The name of the repository (defaults to "my_unity_project").
    Returns:
        A list of dictionaries, where each dictionary contains commit details (hash, author, message, timestamp).
        Returns an empty list or an error message if the branch is not found.
    """
    print(f"[VC Tool] Listing {num_commits} recent commits for branch: {branch} in repo: {repo_name}")
    repo = MOCK_GIT_REPOS.get(repo_name)
    if not repo:
        return [{"error": f"Repository '{repo_name}' not found."}]
    
    branch_info = repo["branches"].get(branch)
    if not branch_info:
        return [{"error": f"Branch '{branch}' not found in repository '{repo_name}'."}]
    
    # Sort commits by timestamp (most recent first) for mock data, if not already sorted
    sorted_commits = sorted(branch_info["commits"], key=lambda x: x["timestamp"], reverse=True)
    
    return sorted_commits[:num_commits]


# List of all Version Control related functions to be passed as tools
VERSION_CONTROL_TOOL_FUNCTIONS = [
    get_latest_commit_on_branch,
    resolve_branch_name,
    resolve_git_user,
    get_commit_details,
    list_available_branches,
    list_recent_commits_on_branch
]