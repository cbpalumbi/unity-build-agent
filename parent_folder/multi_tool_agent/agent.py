import os
import json
import subprocess # For launching listener.py
import threading  # For the internal Pub/Sub listener thread
import queue      # For passing messages from internal listener to main agent logic
import atexit

from google.adk.agents import Agent
from dotenv import load_dotenv
from typing import Dict, Any, Optional
from .version_control_agent import VERSION_CONTROL_TOOL_FUNCTIONS
from .build_orchestration_agent import BUILD_AGENT_TOOL_FUNCTIONS

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
    # --- Pydantic Field Declarations for internal state ---
    # These must be declared as fields if you want them managed by Pydantic
    # and passed in kwargs to the __init__ or have default values.
    # For types like queue.Queue, subprocess.Popen, threading.Event,
    # Pydantic cannot easily validate them, so they typically require
    # model_config = {"arbitrary_types_allowed": True}

    build_status_queue: queue.Queue # Queue for raw JSON from subprocess stdout
    listener_process: Optional[subprocess.Popen] = None # subprocess.Popen object
    stdout_reader_thread: Optional[threading.Thread] = None # Thread reading from subprocess stdout
    _stop_event: threading.Event # Signal for graceful thread shutdown
    current_build_statuses: Dict[str, Dict[str, Any]] = {} # Dictionary to store latest build statuses
    listener_stderr_file_handle: Optional[Any] = None # File handle for listener's stderr

    # Agents are also Pydantic fields if they are passed during initialization
    # and managed by the BaseAgent's Pydantic structure.
    # In your case, you pass 'sub_agents' as a list to the super().__init__,
    # so they might not need to be explicitly declared *here* unless they
    # are intended to be directly accessible as `self.build_orchestration_agent`
    # and validated by Pydantic. For now, let's assume `sub_agents` list is enough.

    # This is CRUCIAL for arbitrary types like queue.Queue, threading.Event, subprocess.Popen
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
        # Initialize the complex objects that Pydantic can't construct directly
        # or which have a specific initial state (e.g., empty queue, unset event).
        # These are then passed to super().__init__ as kwargs so Pydantic assigns them.
        initial_build_status_queue = queue.Queue()
        initial_stop_event = threading.Event()
        initial_current_build_statuses = {}

        if tools is None: tools = []

        # Register the shutdown method here when the orchestrator is created
        atexit.register(self.shutdown)

        # Wrapper for get_build_status.
        def get_build_status_tool(build_id: Optional[str] = None) -> dict:
            """
            Retrieves the most recent build status. Ex: 'nobuild', 'success', 'failed'.
            Does not take in a build id or report one. If the user says they'd like to wait, 
            say Sounds good. Let me know when you'd like to check the build status again.
            Args:
            Returns:
                dict: A dictionary containing the status of the requested build(s).
            """
            return self.get_build_status(build_id=build_id)
        
        # def get_asset_signed_url_tool(build_id: Optional[str] = None) -> str:
        #     """
        #     Produces a signed url from a Google Cloud Store bucket path.
        #     Reports the url.
        #     Args:
        #         build_id: The build_id for the requested build
        #     Returns:
        #         signed_url: The signed url where the user can access the asset
        #     """
        #     return self.get_asset_signed_url(build_id=build_id)

        
        # Append this *callable* to the tools list
        # If your ADK expects a list of tool *functions*, then pass this directly.
        # If it expects a specific Tool object, you'd instantiate that.
        # Assuming `tools` passed to __init__ is where you register them:
        if tools is None:
            tools = []
        tools.append(get_build_status_tool) # Add the wrapped function here
        #tools.append(get_asset_signed_url_tool)

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
 
    def get_build_status(self, build_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves the most recent build status. Ex: 'nobuild', 'success', 'failed'.
        Does not take in a build id or report one. 

        Args:
        Returns:
            dict: A dictionary containing the status of the requested build(s).
        """
        print(f"Tool 'get_build_status_tool' called. Processing pending queue updates...")

        # --- Step 1: Process ALL pending updates from the internal build_status_queue ---
        updates_applied = 0
        while not self.build_status_queue.empty():
            try:
                notification = self.build_status_queue.get_nowait()
                b_id = notification.get('build_id')
                if b_id:
                    # Update the orchestrator's internal dictionary with the latest status
                    self.current_build_statuses[b_id] = notification
                    self.current_build_statuses[b_id]['status'] = "success"
                    updates_applied += 1
                    print(f"  Processed update for build ID: {b_id}, Status: {notification.get('status', 'N/A')}")
                else:
                    print("Update from queue is missing build id.")
                # Optionally, you can add a small sleep to prevent busy-waiting
                # if the queue might be populated very rapidly, though get_nowait()
                # handles the empty case immediately.
                # await asyncio.sleep(0.01) # Small non-blocking sleep if needed
            except queue.Empty:
                # This should ideally not be hit with get_nowait() after checking .empty()
                break
            except Exception as e:
                print(f"  Error processing item from build_status_queue: {e}")
                # Consider putting the item back or logging the error detail
                
        if updates_applied > 0:
            print(f"Successfully applied {updates_applied} new build status updates from the queue.")
        else:
            print("No new build status updates were pending in the queue.")

        # --- Step 2: Retrieve status from the (now updated) current_build_statuses dictionary ---
        if build_id:
            status_info = self.current_build_statuses.get(build_id)
            if status_info:
                return {
                    "build_id": build_id,
                    "status": status_info.get('status', 'unknown'),
                    "gcs_path": status_info.get('gcs_path', 'N/A'),
                    "timestamp": status_info.get('timestamp', 'N/A')
                }
            # If no build_id is found after processing updates
            return {"build_id": build_id, "status": "not_found", "message": f"Build '{build_id}' status not found or not yet processed."}
        
        # If no build_id was provided, return all known statuses
        if not self.current_build_statuses:
            return {"message": "No build status information available."}
        
        # Return a copy to prevent external modification
        return {"all_build_statuses": self.current_build_statuses.copy()}
        


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
                            notification = json.loads(line) # TODO: verify type and stuff 
                            self.build_status_queue.put(notification)
                            print(f"Your build may have finished. Try asking about its status. Item was added to build queue")
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
        "You are the Unity Build specialist. Your primary task is to manage game build requests. "
        "When a user asks for a build, you must first determine the branch and commit hash. "
        "**If the user specifies 'latest commit' or phrases like 'latest version' for a specific branch, "
        "use the `get_latest_commit_on_branch` tool to resolve the precise commit hash for that branch.** "
        "If the user provides a direct commit hash, use that. "
        "Once you have both a specific branch and a resolved commit hash:\n"
        "1. **Confirm the build request with the user** (branch, commit, build type - test/full). "
        "   Always confirm, as builds can take time and resources.\n"
        "2. **Before publishing any build request, first use the `check_gcs_cache` tool** with the resolved branch and commit. "
        "   If the `check_gcs_cache` tool returns `True` (meaning the build is already in cache):\n"
        "   a. Inform the user that a new build is not needed as it's already cached.\n"
        "   b. Proactively ask the user if they would like to generate a signed URL to download this cached build. "
        "      If they confirm, **use the `generate_signed_url_for_build` tool**, providing it with the `branch` and `commit` of the cached build. "
        "      Provide the generated URL to the user.\n"
        "   c. Conclude the request.\n"
        "3. **If `check_gcs_cache` returns `False`** (not in cache), then **use the `publish_build_request` tool** to initiate a new build. "
        "   Inform the user that the build has been initiated and that it was not found in the cache. "
        "   You are responsible for determining whether the user wants a test build (`is_test_build` should be true) or a full build (`is_test_build` false) for `publish_build_request`.\n"
        "4. You can also provide signed URLs for successfully built assets (if that capability becomes available in your tools)."
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

# --- Root Unity Automation Orchestrator Agent ---
root_agent = None
agent = root_agent # needs a duplicate variable for pytest 
# Ensure build_orchestration_agent was created successfully
if build_orchestration_agent:
    try:
        # Instantiate your custom root agent class, passing all necessary arguments
        root_agent = UnityAutomationOrchestrator(
            name="UnityAutomationOrchestrator",
            model=MODEL_GEMINI_2_0_FLASH,
            description=(
                "The central agent for Unity game development automation. "
                "I understand user requests related to building Unity game versions, "
                "managing them, and providing **real-time build status updates**." # Emphasize status here
            ),
            instruction=(
                "You are the main Unity Automation Orchestrator. Your primary role is to understand "
                "the user's request related to Unity game development and delegate it "
                "to the most appropriate specialized sub-agent, or answer it directly using your tools.\n"
                "You have the following specialized sub-agents: \n"
                "1. 'BuildOrchestrationAgent': Handles **only triggering remote Unity builds** via Pub/Sub. "
                "**It CANNOT check build status.**\n\n" # Explicitly state its limitation
                "**If the user asks to build the game, clearly and precisely delegate to the 'BuildOrchestrationAgent'.**\n"
                "**If the user asks about the status of any build (e.g., 'what is the status of the build queue', "
                "'is build X complete?', 'tell me about recent builds'), "
                "you MUST use your 'get_build_status_tool' to retrieve and provide that information.** "
                "Do NOT delegate build status questions to any sub-agent.\n" # Direct instruction for status
                "2. 'Version Control Agent': Handles determining which branch and commit the user in interested in."
                "If the user asks about building without specifying a particular commit and branch, delegate"
                "to the Version Control Agent for resolution."
                "If a request doesn't fall into these categories, state that you cannot handle it."
            ),
            tools=[], # Leave this empty because the stateful tools are added manually on init
            sub_agents=[build_orchestration_agent, version_control_agent], # Pass your sub-agent instance here
        )
        agent = root_agent # needs a duplicate variable for pytest. don't worry about it
        print(f"✅ Root Agent '{root_agent.name}' created.")
    except Exception as e:
        print(f"❌ Could not create Root Unity Agent. Error: {e}")
    
else:
    print("❌ Cannot create Root Unity Agent because the BuildOrchestrationAgent failed to initialize.")

# --- Helper function for async interaction (from ADK quickstart) ---
