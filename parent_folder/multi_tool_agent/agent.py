# agent.py

import os
import subprocess
import datetime
import asyncio
from zoneinfo import ZoneInfo # For potential time tools if you keep them
from typing import Optional

from google.adk.agents import Agent
from google.adk.runners import Runner, InMemorySessionService
#from google.adk.models.gemini import Gemini20Flash # Assuming this is where MODEL_GEMINI_2_0_FLASH comes from
from dotenv import load_dotenv
import git # For GitPython

load_dotenv() # Load environment variables from .env file

# --- Configuration ---
# IMPORTANT: Update these paths to match your system and Unity project
UNITY_GAME_APP_PATH = "/Users/christabellapalumbi/Documents/GoogleHackathon/BuildLLM/Builds/MyMacGame.app"
UNITY_PROJECT_PATH = "/Users/christabellapalumbi/Documents/GoogleHackathon/BuildLLM" # Your Unity project's root folder
# Path to your Unity Editor executable (adjust based on your Unity Hub installation)
# Example for Unity 2023.1.20f1, find yours via Unity Hub -> Installs -> "..." menu -> Show in Finder
UNITY_EDITOR_PATH = "/Users/christabellapalumbi/Desktop/Unity Editors/6000.0.50f1/Unity"

# Define the model if it's not defined elsewhere in your quickstart context
MODEL_GEMINI_2_0_FLASH = "gemini-2.0-flash"

# --- Build Orchestration Tools ---

def run_unity_game(scene_name: str) -> dict:
    """Launches the built Unity game application with a specified scene.

    Args:
        scene_name (str): The name of the Unity scene to start the game with.

    Returns:
        dict: status and result or error message.
    """
    mac_os_executable = os.path.join(UNITY_GAME_APP_PATH, "Contents", "MacOS", "BuildLLM")

    if not os.path.exists(mac_os_executable):
        return {
            "status": "error",
            "error_message": f"Unity game executable not found at {mac_os_executable}. Please check the path: {UNITY_GAME_APP_PATH}"
        }

    command = [
        mac_os_executable,
        "-startScene",
        scene_name
    ]

    try:
        print(f"--- Tool: run_unity_game called with scene: {scene_name} ---")
        # Use Popen to run the game in the background without blocking the agent
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) # Redirect output to devnull
        return {
            "status": "success",
            "message": f"Successfully launched Unity game with scene '{scene_name}'."
        }
    except FileNotFoundError:
        return {
            "status": "error",
            "error_message": f"Command not found or application path is incorrect: {command[0]}"
        }
    except Exception as e:
        return {
            "status": "error",
            "error_message": f"An unexpected error occurred while launching game: {e}"
        }


def trigger_unity_build() -> dict:
    """Triggers a Unity project build using the command line.
    This assumes your Unity project has a static method BuildScript.PerformBuild.

    Returns:
        dict: status and result or error message.
    """
    if not os.path.exists(UNITY_EDITOR_PATH):
        return {
            "status": "error",
            "error_message": f"Unity Editor not found at {UNITY_EDITOR_PATH}. Please verify the path."
        }
    if not os.path.exists(UNITY_PROJECT_PATH):
         return {
            "status": "error",
            "error_message": f"Unity Project not found at {UNITY_PROJECT_PATH}. Please verify the path."
        }

    # Example build command (adjust based on your BuildScript and target)
    build_command = [
        UNITY_EDITOR_PATH,
        "-batchmode",
        "-quit",
        "-projectPath", UNITY_PROJECT_PATH,
        "-executeMethod", "BuildScript.PerformBuild", # Make sure this method exists in your Unity project
        "-logFile", os.path.join(UNITY_PROJECT_PATH, "unity_build_log.txt"), # Log output to a file
        "-buildTarget", "StandaloneOSX" # Or "StandaloneWindows64", "WebGL", etc.
    ]

    try:
        print(f"--- Tool: trigger_unity_build called ---")
        # Run build command synchronously, it might take a while
        # Set timeout to prevent indefinite blocking in case of issues
        result = subprocess.run(build_command, capture_output=True, text=True, check=False, timeout=600) # 10 minute timeout

        if result.returncode == 0:
            return {
                "status": "success",
                "message": f"Unity build command executed successfully. Check {os.path.join(UNITY_PROJECT_PATH, 'unity_build_log.txt')} for details.",
                "build_log_summary": result.stdout[:500] + "..." if len(result.stdout) > 500 else result.stdout # Summarize log
            }
        else:
            return {
                "status": "error",
                "error_message": f"Unity build failed. Return code: {result.returncode}. Error output: {result.stderr[:500]}...",
                "full_error_log": result.stderr
            }
    except FileNotFoundError:
        return {
            "status": "error",
            "error_message": f"Unity Editor not found at specified path: {UNITY_EDITOR_PATH}"
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "error_message": "Unity build timed out after 10 minutes. It might be stuck or taking too long."
        }
    except Exception as e:
        return {
            "status": "error",
            "error_message": f"An unexpected error occurred during build: {e}"
        }

# --- Version Control Tools (using GitPython) ---

def get_repo():
    """Helper to get the GitPython repository object."""
    try:
        repo = git.Repo(UNITY_PROJECT_PATH)
        return repo
    except git.InvalidGitRepositoryError:
        return None

def get_git_status() -> dict:
    """Retrieves the current status of the Git repository (e.g., untracked files, modified files)."""
    repo = get_repo()
    if repo is None:
        return {"status": "error", "error_message": "Unity project path is not a Git repository."}
    
    status_summary = []
    if repo.is_dirty():
        status_summary.append("Repository is dirty (uncommitted changes).")
    if repo.untracked_files:
        status_summary.append(f"Untracked files: {', '.join(repo.untracked_files)}")
    
    if not status_summary:
        status_summary.append("Repository is clean.")
        
    return {"status": "success", "message": "\n".join(status_summary), "is_dirty": repo.is_dirty(), "untracked_files_count": len(repo.untracked_files)}


def get_latest_commit_info() -> dict:
    """Retrieves information about the latest commit in the Unity project repository."""
    repo = get_repo()
    if repo is None:
        return {"status": "error", "error_message": "Unity project path is not a Git repository."}
    
    try:
        head_commit = repo.head.commit
        info = {
            "hash": head_commit.hexsha,
            "author": head_commit.author.name,
            "date": head_commit.committed_datetime.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "message": head_commit.message.strip().split('\n')[0] # First line of commit message
        }
        print(f"--- Tool: get_latest_commit_info called ---")
        return {"status": "success", "info": info, "message": f"Latest commit: {info['message']} by {info['author']} on {info['date']} ({info['hash'][:7]})"}
    except Exception as e:
        return {"status": "error", "error_message": f"Could not get latest commit info: {e}"}

def checkout_git_version(commit_identifier: Optional[str] = None, author: Optional[str] = None, date: Optional[str] = None) -> dict:
    """Checks out a specific version of the Unity project repository based on identifier, author, or date.
    Args:
        commit_identifier (str, optional): A Git commit hash, branch name, or tag name.
        author (str, optional): The author's name to find a commit.
        date (str, optional): A specific date (YYYY-MM-DD) to find a commit near.
    Returns:
        dict: status and result or error message.
    """
    repo = get_repo()
    if repo is None:
        return {"status": "error", "error_message": "Unity project path is not a Git repository."}
    
    if not (commit_identifier or author or date):
        return {"status": "error", "error_message": "Please provide a commit hash, author, or date to check out."}

    try:
        target_commit = None
        if commit_identifier:
            # Try to checkout directly by hash/branch/tag
            repo.git.checkout(commit_identifier)
            target_commit = repo.head.commit
        elif author or date:
            # Search for commit by author/date
            log_command = ["log", "--reverse", "--pretty=format:%H", "--max-count=1"]
            if author:
                log_command.append(f"--author={author}")
            if date:
                log_command.append(f"--before={date} 23:59:59") # End of day
                log_command.append(f"--after={date} 00:00:00") # Start of day

            result = repo.git.execute(log_command)
            commit_hash = result.strip().split('\n')[-1] if result else None

            if commit_hash:
                repo.git.checkout(commit_hash)
                target_commit = repo.head.commit
            else:
                return {"status": "error", "error_message": f"No commit found matching criteria (author: {author}, date: {date})."}

        if target_commit:
            # Placeholder for asset copying:
            # You would implement logic here to copy specific assets from the checked-out
            # repository into your designated Assets/RuntimeLoadedAssets/ folder if needed.
            # E.g., shutil.copytree or shutil.copy to move files.
            print(f"--- Tool: checkout_git_version called: Checked out to {target_commit.hexsha[:7]} ---")
            return {"status": "success", "message": f"Successfully checked out to commit {target_commit.hexsha[:7]} ('{target_commit.message.strip().splitlines()[0]}'). Assets might need to be copied manually or by a separate process."}
        else:
            return {"status": "error", "error_message": "Could not determine target commit for checkout."}

    except git.GitCommandError as e:
        return {"status": "error", "error_message": f"Git command failed: {e}. Check if the branch/commit exists or if local changes conflict."}
    except Exception as e:
        return {"status": "error", "error_message": f"An unexpected error occurred during Git checkout: {e}"}

# --- Build Orchestration Agent ---
build_orchestration_agent = None
try:
    build_orchestration_agent = Agent(
        model=MODEL_GEMINI_2_0_FLASH,
        name="BuildOrchestrationAgent",
        instruction=(
            "You are the Unity Build and Run specialist. Your ONLY task is to manage "
            "the execution of Unity game applications and trigger full game builds. "
            "Use the 'run_unity_game' tool to launch the game with a specified scene. "
            "Use the 'trigger_unity_build' tool to initiate a full build. "
            "Always confirm with the user before starting a build, as it can take time. "
            "Do not handle any version control tasks. If a scene name is not provided for 'run_unity_game', ask for it."
        ),
        description="Manages launching the Unity game with a specific scene and triggering full Unity project builds.",
        tools=[run_unity_game, trigger_unity_build],
    )
    print(f"✅ Agent '{build_orchestration_agent.name}' created.")
except Exception as e:
    print(f"❌ Could not create Build Orchestration Agent. Error: {e}")


# --- Version Control Agent ---
version_control_agent = None
try:
    version_control_agent = Agent(
        model=MODEL_GEMINI_2_0_FLASH,
        name="VersionControlAgent",
        instruction=(
            "You are the Unity Git Version Control specialist. Your ONLY task is to "
            "interact with the game's Git repository. "
            "Use 'get_latest_commit_info' to retrieve details about the most recent commit. "
            "Use 'checkout_git_version' to switch the project to a specific commit, branch, author, or date. "
            "Clarify with the user if they want to checkout by commit hash, author, or date. "
            "Do not build or run the game, or handle general questions."
        ),
        description="Manages the Unity project's Git repository, including checking out specific versions (by hash, author, or date) and getting commit info.",
        tools=[get_latest_commit_info, checkout_git_version, get_git_status], # Added get_git_status for completeness
    )
    print(f"✅ Agent '{version_control_agent.name}' created.")
except Exception as e:
    print(f"❌ Could not create Version Control Agent. Error: {e}")

# (You can include your original 'greeting_agent' and 'farewell_agent' here if you want them in the same team)

# --- Root Unity Automation Orchestrator Agent ---
root_agent = None
# Ensure sub-agents were created successfully
if build_orchestration_agent and version_control_agent:
    try:
        root_agent = Agent(
            name="UnityAutomationOrchestrator",
            model=MODEL_GEMINI_2_0_FLASH, # A capable model is good for the orchestrator
            description="The central agent for Unity game development automation.",
            instruction=(
                "You are the main Unity Automation Orchestrator. Your primary role is to understand "
                "the user's request related to Unity game development and delegate it "
                "to the most appropriate specialized sub-agent. "
                "You have the following specialized sub-agents: \n"
                "1. 'BuildOrchestrationAgent': Handles launching the game and triggering builds. "
                "2. 'VersionControlAgent': Handles Git operations like checking out specific versions or getting commit information. "
                "Delegate clearly and let the sub-agent handle the detailed response. "
                "If a request doesn't fall into these categories, state that you cannot handle it."
            ),
            tools=[], # The root agent typically has no direct tools if its only job is delegation
            sub_agents=[build_orchestration_agent, version_control_agent]
            # Add greeting_agent and farewell_agent here if you want them in the same team:
            # sub_agents=[build_orchestration_agent, version_control_agent, greeting_agent, farewell_agent]
        )
        print(f"✅ Root Agent '{root_agent.name}' created with sub-agents: {[sa.name for sa in root_agent.sub_agents]}")
    except Exception as e:
        print(f"❌ Could not create Root Unity Agent. Error: {e}")
else:
    print("❌ Cannot create Root Unity Agent because one or more sub-agents failed to initialize.")

# --- Helper function for async interaction (from ADK quickstart) ---
async def call_agent_async(
    query: str, runner: Runner, user_id: str, session_id: str
) -> None:
    print(f"\n--- User: {query} ---")
    response = await runner.send_message(
        message=query, user_id=user_id, session_id=session_id
    )
    # The ADK response object has a `text` attribute for the agent's reply
    print(f"--- Agent: {response.text} ---")
    if response.tool_calls:
        for tool_call in response.tool_calls:
            print(f"--- Tool Call: {tool_call.tool_name}({tool_call.args}) ---")
    if response.tool_results:
        for tool_result in response.tool_results:
            print(f"--- Tool Result: {tool_result.result} ---")
    # For debugging, you might want to see the raw content:
    # print(f"--- Raw Response: {response.raw_content} ---")

# --- Interact with the Agent Team ---
if root_agent: # Only run if the root agent was successfully created
    async def run_unity_automation_conversation():
        print("\n--- Testing Unity Agent Team Delegation ---")
        session_service = InMemorySessionService()
        APP_NAME = "unity_automation_app"
        USER_ID = "dev_user_1"
        SESSION_ID = "session_001_unity"
        session = await session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )
        print(f"Session created: App='{APP_NAME}', User='{USER_ID}', Session='{SESSION_ID}'")

        runner_unity_team = Runner( # Or InMemoryRunner
            agent=root_agent,
            app_name=APP_NAME,
            session_service=session_service
        )
        print(f"Runner created for agent '{root_agent.name}'.")

        # --- Test Interactions ---
        await call_agent_async(
            query="Run the game at AssetViewerScene",
            runner=runner_unity_team, user_id=USER_ID, session_id=SESSION_ID
        )

        await call_agent_async(
            query="Please build the game for Mac.",
            runner=runner_unity_team, user_id=USER_ID, session_id=SESSION_ID
        )

        await call_agent_async(
            query="What's the latest commit?",
            runner=runner_unity_team, user_id=USER_ID, session_id=SESSION_ID
        )

        await call_agent_async(
            query="Check out the version by Alice from yesterday.",
            runner=runner_unity_team, user_id=USER_ID, session_id=SESSION_ID
        )
        
        await call_agent_async(
            query="What is the current status of the repo?",
            runner=runner_unity_team, user_id=USER_ID, session_id=SESSION_ID
        )


        await call_agent_async(
            query="Tell me a joke.", # Should be handled by root or unrecognized
            runner=runner_unity_team, user_id=USER_ID, session_id=SESSION_ID
        )


    # --- Execute the async function ---
    # Use asyncio.run() for standard Python scripts (.py)
    # If running in a notebook (like Colab/Jupyter), you can use `await run_unity_automation_conversation()` directly
    if __name__ == "__main__":
        print("Executing using 'asyncio.run()'...")
        try:
            asyncio.run(run_unity_automation_conversation())
        except Exception as e:
            print(f"An error occurred during conversation: {e}")