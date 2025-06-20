import os
import json
import subprocess # For launching listener.py
import threading  # For the internal Pub/Sub listener thread
import queue      # For passing messages from internal listener to main agent logic
import atexit
import datetime

from google.adk.agents import Agent
from dotenv import load_dotenv
from typing import Dict, Any, Optional
from .version_control_agent import VERSION_CONTROL_TOOL_FUNCTIONS
from .build_orchestration_agent import BUILD_AGENT_TOOL_FUNCTIONS, generate_signed_url_for_build
from .asset_preview_agent import ASSET_AGENT_TOOL_FUNCTIONS

load_dotenv() # Load environment variables from .env file

# --- Configuration for Google Cloud ---
# IMPORTANT: Replace with your actual Project ID and Topic ID
GOOGLE_CLOUD_PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT_ID")

# Define the model for agents
MODEL_GEMINI_2_0_FLASH = "gemini-2.0-flash" # Assuming this is the correct way to reference it

# --- Agent Definitions ---
class UnityAutomationOrchestrator(Agent):
    """
    The central agent for Unity game development automation.
    This agent orchestrates various tasks related to Unity builds and management.
    """

    listener_process: Optional[subprocess.Popen] = None # subprocess.Popen object
    listener_stderr_file_handle: Optional[Any] = None # File handle for listener's stderr
    stdout_reader_thread: Optional[threading.Thread] = None # Thread reading from subprocess stdout
    _stop_event: threading.Event # Signal for graceful thread shutdown
    
    build_status_queue: queue.Queue # Queue for raw JSON from subprocess stdout
    current_build_statuses: Dict[str, Dict[str, Any]] # Use commit hash as the primary key for caching purposes
    current_asset_bundle_statuses: Dict[str, Dict[str, Any]] # Use session id as the primary key

    # Needed for pydantic to not complain
    model_config = {"arbitrary_types_allowed": True}

    def __init__(
        self,
        name: str,
        model: str,
        description: str,
        instruction: str,
        sub_agents: list,
        tools: Optional[list] = None,
        **kwargs, # Accept any other kwargs that Pydantic might inject or we want to pass
    ):
        """
        Initializes the UnityAutomationOrchestrator.
        """

        print(f"Orchestrator ID: {id(self)}")  # in tool
        
        # Initialize the complex objects that Pydantic can't construct directly
        # or which have a specific initial state (e.g., empty queue, unset event).
        # These are then passed to super().__init__ as kwargs so Pydantic assigns them.
        initial_build_status_queue = queue.Queue()
        initial_current_build_statuses = {}
        initial_current_asset_bundle_statuses = {}

        if tools is None: tools = []

        # Register the shutdown method here when the orchestrator is created
        atexit.register(self.shutdown)

        # Wrapper for get_build_status.
        def get_build_status_tool(requestedCommit: Optional[str] = None) -> dict:
            """
            Retrieves the most recent build status. Ex: 'nobuild', 'success', 'failed'.
            If the user specifies a commit, look for that build. If not, look for the
            latest build they triggered. 
            
            Args:
                requestedCommit: optional, to ask for a certain commit's status
            Returns:
                dict: A dictionary containing the status of the requested build(s).
            """
            return self.get_build_status(requestedCommit==requestedCommit)
        
        # Wrapper for get_asset_signed_url, imported from build orchestration agent
        def get_asset_signed_url_tool(branch: str, commit: str,) -> str:
            """
            Produces a signed url from a Google Cloud Store bucket path.
            Reports the url.
            Args:
                build_id: The build_id for the requested build
            Returns:
                signed_url: The signed url where the user can access the asset
            """
            return generate_signed_url_for_build(branch, commit)

        
        # Append this *callable* to the tools list
        # If your ADK expects a list of tool *functions*, then pass this directly.
        # If it expects a specific Tool object, you'd instantiate that.
        # Assuming `tools` passed to __init__ is where you register them:
        if tools is None:
            tools = []
        tools.append(get_build_status_tool) # Add the wrapped function here
        tools.append(get_asset_signed_url_tool)

        # --- CRITICAL FIX FOR _before_agent_callback ---
        # Create a lambda that captures the 'self' of *this* Orchestrator instance.
        # When the ADK calls this lambda, the lambda in turn calls the
        # actual instance method self._before_agent_callback,
        # thereby correctly passing 'self' to it.
        bound_callback_for_adk = lambda **cb_kwargs: self._before_agent_callback(**cb_kwargs)

        # Pass all arguments, including your custom internal state, to the base Agent constructor.
        # Pydantic will handle the assignment to the declared fields.
        super().__init__(
            name=name,
            model=model,
            description=description,
            instruction=instruction,
            tools=tools,
            sub_agents=sub_agents,
            before_model_callback=bound_callback_for_adk,
            build_status_queue=initial_build_status_queue,
            current_build_statuses=initial_current_build_statuses,
            current_asset_bundle_statuses=initial_current_asset_bundle_statuses,
            **kwargs # Pass any remaining kwargs
        )

        # Initialize other custom internal state *directly on self*
        # after the super().__init__ call has completed.
        # These are instance attributes that are not passed to the Pydantic base model's __init__.
        self._stop_event = threading.Event()
        # self.listener_process = None # Already Optional[None]
        # self.stdout_reader_thread = None # Already Optional[None]
        # self.listener_stderr_file_handle = None # Already Optional[None]

        # Now that Pydantic has initialized the fields, you can access them.
        # Launch background services AFTER the agent instance is fully initialized
        # and its Pydantic fields are set.
        self.start_external_listener_subprocess()
        print(f"UnityAutomationOrchestrator initialized with name: {self.name}")
 
    def get_build_status(self, requestedCommit: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves the build status. Ex: 'nobuild', 'success', 'failed'.

        Args:
            requestedCommit: the user can optionally request the build status of a specific commit
        Returns:
            dict: A dictionary containing the status of the requested build(s).
        """ 
        if not self.current_build_statuses or len(self.current_build_statuses) == 0:
            return {"message": "No build status information available."}

        # --- Retrieve status from the current_build_statuses dictionary ---
        if isinstance(requestedCommit, str) and requestedCommit.strip():
            status_info = self.current_build_statuses.get(requestedCommit)
            if status_info:
                return {
                    "status": status_info.get('status', 'unknown'),
                }
            return {"requestedCommit": requestedCommit, "status": "not_found", "message": f"Build for commit '{requestedCommit}' status not found or not yet processed."}
        else: 
            # Find latest build by timestamp
            latest_commit = None
            latest_timestamp = None
            for commit, info in self.current_build_statuses.items():
                timestamp_str = info.get('timestamp')
                if timestamp_str:
                    try:
                        timestamp = datetime.datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        if latest_timestamp is None or timestamp > latest_timestamp:
                            latest_timestamp = timestamp
                            latest_commit = commit
                    except Exception as e:
                        print(f"Warning: Could not parse timestamp for commit {commit}: {e}")

            if latest_commit is None:
                return {"message": "No valid timestamp found for builds."}

            # Return status for latest commit
            status_info = self.current_build_statuses.get(latest_commit)
            return {
                "commit": latest_commit,
                "status": status_info.get('status', 'unknown'),
            }

    def start_external_listener_subprocess(self):
        """
        Launches listener.py as a separate, long-running process and starts
        a thread to continuously read its stdout.
        """
        listener_script_path = os.path.join(os.path.dirname(__file__), 'listener.py')
        
        try:
            # Open stderr to a file for debugging, or you can use subprocess.PIPE
            # if you want to read stderr in another thread/way.
            self.listener_stderr_file_handle = open("listener_stderr.log", "a")
            
            self.listener_process = subprocess.Popen(
                ["python", listener_script_path],
                stdout=subprocess.PIPE,
                stderr=self.listener_stderr_file_handle,
                text=True, # Decode stdout/stderr as text
                bufsize=1, # Line-buffered output for stdout
            )
            print(f"Launched listener.py process with PID: {self.listener_process.pid}")

            # Start a thread to read stdout from the listener process
            self.stdout_reader_thread = threading.Thread(target=self._read_listener_stdout, daemon=True)
            self.stdout_reader_thread.start()
            print("Started stdout reader thread for listener process.")

        except FileNotFoundError:
            print(f"Error: Python interpreter or listener.py not found at {listener_script_path}.")
            if self.listener_stderr_file_handle:
                self.listener_stderr_file_handle.close()
            self.listener_stderr_file_handle = None
        except Exception as e:
            print(f"An error occurred while launching listener.py: {e}")
            if self.listener_stderr_file_handle:
                self.listener_stderr_file_handle.close()
            self.listener_stderr_file_handle = None
   
    def _read_listener_stdout(self):
        """
        Continuously reads lines from the listener.py's stdout, parses them as JSON,
        and places them into self.build_status_queue. This runs in a separate thread.
        """

        # $completionPayload = @{
        #         session_id = "placeholder"
        #         commit = $commitHash
        #         branch = $branchName
        #         status = "success"
        #         is_test_build = $isTestBuild
        #         gcs_path = $finalGcsPath
        #         timestamp = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ')
        #         build_id = $receivedBuildId
        #     }

        if not self.listener_process or not self.listener_process.stdout:
            print("Listener process or its stdout not initialized. Cannot read stdout.")
            return

        print("Stdout reader thread started, waiting for output from listener.py...")
        while not self._stop_event.is_set():
            try:
                line = self.listener_process.stdout.readline()
                if line:
                    line = line.strip()
                    if line: # Ensure the line is not empty after stripping
                        print(f"[Listener STDOUT]: {line}") # For debugging
                        try:
                            notification = json.loads(line) # TODO: verify type etc
                            commit_hash = notification.get('commit')
                            session_id = notification.get('session_id')
                            if commit_hash:
                                # Update the orchestrator's internal build status dictionary with the latest status
                                self.current_build_statuses[commit_hash] = notification
                                print(f"  Processed update for commit: {commit_hash}, Status: {notification.get('status', 'N/A')}")
                            elif session_id:
                                # Update asset bundle status instead
                                self.current_asset_bundle_statuses[session_id] = notification
                                print(f"  Processed update for asset bundle for session: {session_id}, Status: {notification.get('status', 'N/A')}")
                            else:
                                print("Build status notif has neither commit hash nor session id")

                        except json.JSONDecodeError as e:
                            print(f"Failed to decode JSON from listener stdout: {line} - Error: {e}")
                else:
                    # If readline returns an empty string, the subprocess has likely exited.
                    if self.listener_process.poll() is not None:
                        print("Listener process has exited. Stopping stdout reader thread.")
                        break
                    # Small delay to prevent busy-waiting if no output
                    self._stop_event.wait(0.1) 
            except Exception as e:
                print(f"Error reading from listener stdout: {e}")
                break # Exit the thread on error

        print("Stdout reader thread stopping.")

    def shutdown(self):
        """
        Gracefully shuts down the listener subprocess and reader thread.
        """
        print("Initiating UnityAutomationOrchestrator shutdown...")
        # Signal the stdout reader thread to stop
        self._stop_event.set()

        # Terminate the listener process if it's running
        if self.listener_process and self.listener_process.poll() is None:
            print("Terminating listener.py process...")
            self.listener_process.terminate()
            try:
                self.listener_process.wait(timeout=5) # Wait for process to terminate
            except subprocess.TimeoutExpired:
                print("Listener process did not terminate gracefully, killing it.")
                self.listener_process.kill()
        
        # Join the stdout reader thread to ensure it finishes
        if self.stdout_reader_thread and self.stdout_reader_thread.is_alive():
            print("Joining stdout reader thread...")
            self.stdout_reader_thread.join(timeout=5)
            if self.stdout_reader_thread.is_alive():
                print("Warning: stdout reader thread did not terminate in time.")

        # Close the stderr file handle
        if self.listener_stderr_file_handle:
            self.listener_stderr_file_handle.close()
            self.listener_stderr_file_handle = None
            print("Closed listener_stderr.log file handle.")

        print("UnityAutomationOrchestrator shutdown complete.")
    def _before_agent_callback(self, **kwargs): pass


# Build Orchestration Agent
build_orchestration_agent = Agent(
    model=MODEL_GEMINI_2_0_FLASH,
    name="BuildOrchestrationAgent",
    instruction=(
        "You are the Unity Build specialist. Your role is to manage build requests for the Unity project.\n\n"
        "When a user asks to build the game, follow this structured process:\n\n"
        "1. **Determine the branch and commit hash**:\n"
        "- If the user says 'latest commit' or 'latest version' for a branch, use the `get_latest_commit_on_branch` tool to resolve it.\n"
        "- If the user gives a direct commit hash, use it as-is.\n\n"
        "2. **Clarify build type**:\n"
        "- Use context to determine if the user wants a 'test build' or 'full build'.\n"
        "- You must set the `is_test_build` field appropriately when initiating builds.\n\n"
        "3. **Confirm with the user before building**:\n"
        "- Once you know the branch, commit, and build type, confirm the request.\n"
        "- Say something like: 'Just to confirm, you want to build the game on branch `X`, commit `Y`, as a [test/full] build?' \n"
        "- Wait for user confirmation before continuing.\n\n"
        "4. **Check the cache**:\n"
        "- Use the `check_gcs_cache` tool with the confirmed branch and commit.\n"
        "- If the tool returns `True`, inform the user that the build is already cached.\n"
        "  - Offer to generate a signed URL by asking the user if they want to download it.\n"
        "  - If they say yes, use `generate_signed_url_for_build` and return the link.\n"
        "  - If they say to rebuild it anyway, use the `publish_build_request` tool with the correct `branch`, `commit`, and `is_test_build` values.\n"
        "- **If the tool returns `False` (cache miss)**, explicitly say:\n"
        "  - 'This build is not cached. I will now trigger a new build.'\n"
        "  - Then, use the `publish_build_request` tool with the correct `branch`, `commit`, and `is_test_build` values.\n"
        "  - Inform the user that the build is in progress and may take several minutes.\n\n"
        "5. When a user later asks about build status:\n"
        "- You will NOT handle that — the root UnityOrchestrationAgent handles status tracking and signed URL generation once builds are complete.\n\n"
        "Remember: never trigger a build without confirmation and cache check. Never offer a signed URL unless the build is complete or already cached."
    ),
    description="Manages user confirmation, checks GCS cache, initiates remote Unity project builds, and offers cached build downloads, including resolving latest commit hashes.",
    tools=BUILD_AGENT_TOOL_FUNCTIONS
)
print(f"✅ Agent '{build_orchestration_agent.name}' created.")

# Version Control Agent
version_control_agent = Agent(
    model=MODEL_GEMINI_2_0_FLASH, 
    name="VersionControlAgent",
    instruction=(
        "You are a Git Version Control Specialist. "
        "Your primary task is to assist the user with all queries related to Git branches, commits, and users. "
        "Use your specialized tools (`resolve_branch_name`, `get_latest_commit_on_branch`, `resolve_git_user`, `get_commit_details`, `list_available_branches`, `list_recent_commits_on_branch`) "
        "to accurately answer questions about Git history, branch status, and specific commits. "
        "Always aim to provide precise and helpful information based on the Git repository data. "
        "If a user asks to 'build' something, you should resolve the specific branch and commit details first, "
        "and then inform the user that you have the necessary information." # This part will be crucial for OrchestratorRootAgent delegation.
    ),
    description="Specializes in resolving Git branches, commits, and users, and providing Git history information.",
    tools=VERSION_CONTROL_TOOL_FUNCTIONS 
)
print(f"✅ Agent '{version_control_agent.name}' created.")

# Asset Preview Agent
asset_preview_agent = Agent(
    model=MODEL_GEMINI_2_0_FLASH,
    name="AssetPreviewAgent",
    instruction=(
        "You are the assistant for previewing custom game assets in Unity without requiring a full rebuild.\n\n"
        "When a user wants to preview a model or test an asset in the game, follow this step-by-step process:\n\n"
        "1. Retrieve the user's session ID by calling your `get_session_id` tool.\n\n"
        "2. Check if the user already has a downloaded game build (.exe):\n"
        "   - Ask: 'Do you already have the game build executable downloaded, or would you like to create one now?'\n"
        "   - If the user does not have the build or is unsure, guide them to first create a build by delegating to the BuildOrchestrationAgent or by providing clear instructions.\n\n"
        "3. Prompt the user to upload their asset:\n"
        "   - Confirm they have a .glb model file ready for upload (only .glb files are supported).\n"
        "   - Generate an upload URL using the `generate_upload_url` tool.\n"
        "   - Provide the user with the upload link and instruct them to upload their .glb file there.\n"
        "   - Make sure to tell them to open the link in a separate tab with Ctrl+Click."
        "   - Ask the user to notify you once the upload is complete. Do not trigger the build until you know the glb was uploaded.\n\n"
        "4. Trigger the asset bundle build:\n"
        "   - Once the user confirms upload completion, inform them that you will now start building a small asset bundle.\n"
        "   - Use the `publish_assetbundle_request` tool, passing in their session id.\n"
        "   - Let the user know this build usually takes 1 to 3 minutes, and they will see a notification on the left when \n\n"
        "       the asset bundle build is done. Say that they can let you know when the build is done and you can generate a download link."
        "5. Deliver the signed download URL:\n"
        "   - If the user later requests to download their asset, call the `generate_signed_url_for_bundle` tool to obtain a signed URL.\n"
        "   - Provide this signed URL with the instruction: 'To preview your asset in the game, unzip the folder and place all the contents"
        "     in a folder called MyAssetBundles in the same location as your .exe (executable). The folder must be named MyAssetBundles"
        "      If multiple bundles exist, only the first one will be loaded.'\n\n"
        "Always maintain a friendly, clear, and approachable tone. Assume the user might not be a developer, so offer brief, easy-to-understand guidance throughout the conversation."
    ),
    description="Helps users preview custom game assets by uploading .glb files, triggering Unity asset bundle builds, and delivering download links.",
    tools=ASSET_AGENT_TOOL_FUNCTIONS
)
print(f"✅ Agent '{asset_preview_agent.name}' created.")

# --- Root Unity Automation Orchestrator Agent ---
root_agent = None
agent = root_agent # needs a duplicate variable for pytest 
# Ensure build_orchestration_agent was created successfully
if build_orchestration_agent and version_control_agent and asset_preview_agent:
    try:
        # Instantiate your custom root agent class, passing all necessary arguments
        root_agent = UnityAutomationOrchestrator(
            name="UnityAutomationOrchestrator",
            model=MODEL_GEMINI_2_0_FLASH,
            description=(
                "The central agent for Unity game development automation. "
                "I understand user requests related to building Unity game versions, "
                "managing them, and providing **build status updates**." # Emphasize status here
            ),
            instruction=(
                "You are the main Unity Automation Orchestrator. Your role is to understand and coordinate the user's "
                "Unity game development requests. You may either:\n"
                "- Delegate tasks to the appropriate sub-agent\n"
                "- Handle the request directly using your available tools\n\n"

                "You have the following sub-agents:\n"
                "1. **BuildOrchestrationAgent**: Handles triggering new remote Unity builds via Pub/Sub.\n"
                "   - This agent **CANNOT check build status**, or answer questions about existing builds.\n"
                "   - If the user asks to build the game, clearly and precisely delegate to the BuildOrchestrationAgent.\n\n"

                "2. **VersionControlAgent**: Handles resolving ambiguous or natural language references to branches and commits.\n"
                "   - If a user requests a build but doesn’t specify both a branch and a commit, delegate to this agent first.\n\n"

                "3. **AssetPreviewAgent**: Handles guiding the user through generating assetbundles to preview their assets in the game."
                "   - If a user requests to preview an asset, or see their asset or art in the game, delegate to this agent."

                "You must handle build status questions directly."
                "- If the user asks about build statuses with phrases like:"
                "what is the status of the build queue, is build X complete?, did my build finish?, is the test build done?"
                "or similar, always call the `get_build_status_tool` to get the latest information."
                "- If the user does NOT specify a commit hash, treat the request as about the *most recent build*."
                "- If the build status is success or complete, offer the user a signed URL to download the build by asking:"
                "Would you like a signed URL to download this build?"
                "- If the user says yes, call the `get_asset_signed_url_tool` with the corresponding commit/build ID, and share the signed URL in your response."
                "- If the build status is not complete, inform the user politely that the build is still in progress or not found."
                "Your job is to be helpful, accurate, and clear in guiding the user through automated Unity workflows."

                "If a request doesn’t fall into these categories, explain that you cannot handle it.\n\n"
            ),
            tools=[], # Leave this empty because the stateful tools are added manually on init
            sub_agents=[build_orchestration_agent, version_control_agent, asset_preview_agent], # Pass your sub-agent instance here
        )
        agent = root_agent # needs a duplicate variable for pytest. don't worry about it

        print(f"✅ Root Agent '{root_agent.name}' created.")
    except Exception as e:
        print(f"❌ Could not create Root Unity Agent. Error: {e}")
    
else:
    print("❌ Cannot create Root Unity Agent because one or more subagents failed to start")

