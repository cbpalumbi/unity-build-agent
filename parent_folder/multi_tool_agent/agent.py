import os
import asyncio
import json
import base64

from google.adk.agents import Agent
from google.adk.runners import Runner, InMemorySessionService
from google.cloud import pubsub_v1 # Import Pub/Sub client
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file

# --- Configuration for Google Cloud ---
# IMPORTANT: Replace with your actual Project ID and Topic ID
GOOGLE_CLOUD_PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT_ID", "cool-ruler-461702-p8")
# Confirm this topic ID in your GCP Console. It's the topic your VM's Pub/Sub subscription listens to.
UNITY_BUILD_PUB_SUB_TOPIC_ID = os.getenv("UNITY_BUILD_PUB_SUB_TOPIC_ID", "unity-build-trigger-topic")

# Define the model for agents
MODEL_GEMINI_2_0_FLASH = "gemini-2.0-flash" # Assuming this is the correct way to reference it

# --- Pub/Sub Publisher Tool (used by BuildOrchestrationAgent) ---

def publish_build_request(message_payload: str) -> dict:
    """Publishes a build request message to the Google Cloud Pub/Sub topic.

    This function is intended to be used as a tool by the BuildOrchestrationAgent.

    Args:
        message_payload (str): The string payload to send. Examples:
                               "start_build_for_unityadmin"
                               "checkout_and_build:main"
                               "checkout_and_build:abcdef1234567890abcdef1234567890"

    Returns:
        dict: Status and message or error details.
    """
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(GOOGLE_CLOUD_PROJECT_ID, UNITY_BUILD_PUB_SUB_TOPIC_ID)

    # The message payload is a string, which we'll Base64 encode before sending.
    # This aligns with how your PowerShell script expects it.
    data_bytes = message_payload.encode('utf-8')

    try:
        print(f"--- Tool: publish_build_request called with payload: '{message_payload}' ---")
        future = publisher.publish(topic_path, data=data_bytes)
        message_id = future.result()
        print(f"SUCCESS: Published message with ID: {message_id}")
        return {
            "status": "success",
            "message": f"Build request published to Pub/Sub with ID: {message_id}",
            "message_payload": message_payload
        }
    except Exception as e:
        print(f"ERROR: Failed to publish message to Pub/Sub: {e}")
        return {
            "status": "error",
            "error_message": f"Failed to publish build request: {e}"
        }

# --- Agent Definitions ---

# Build Orchestration Agent
build_orchestration_agent = Agent(
    model=MODEL_GEMINI_2_0_FLASH,
    name="BuildOrchestrationAgent",
    instruction=(
        "You are the Unity Build specialist. Your ONLY task is to trigger full game builds "
        "on the remote VM via Google Cloud Pub/Sub. "
        "Use the 'publish_build_request' tool to initiate a build on the remote VM. "
        "Always confirm with the user before publishing a new build request, as it can take time. "
        "Once a build request is published, inform the user that the build has been initiated. "
        "You are responsible for formulating the correct message payload for 'publish_build_request' "
        "based on the desired Git information (e.g., 'checkout_and_build:main' or 'checkout_and_build:specific_commit_hash')."
    ),
    description="Manages triggering remote Unity project builds via Pub/Sub.",
    tools=[publish_build_request], # Only the publishing tool here
)
print(f"✅ Agent '{build_orchestration_agent.name}' created.")

# --- Root Unity Automation Orchestrator Agent ---
root_agent = None
# Ensure build_orchestration_agent was created successfully
if build_orchestration_agent:
    try:
        root_agent = Agent(
            name="UnityAutomationOrchestrator",
            model=MODEL_GEMINI_2_0_FLASH, # A capable model is good for the orchestrator
            description="The central agent for Unity game development automation. "
                        "I understand user requests related to building Unity game versions.",
            instruction=(
                "You are the main Unity Automation Orchestrator. Your primary role is to understand "
                "the user's request related to Unity game development and delegate it "
                "to the most appropriate specialized sub-agent. "
                "You have the following specialized sub-agents: \n"
                "1. 'BuildOrchestrationAgent': Handles triggering remote Unity builds via Pub/Sub.\n\n"
                "Delegate clearly and precisely to the 'BuildOrchestrationAgent' if the request is about building the game. "
                "If a request doesn't fall into this category, state that you cannot handle it."
            ),
            tools=[], # The root agent typically has no direct tools if its only job is delegation
            sub_agents=[build_orchestration_agent]
        )
        print(f"✅ Root Agent '{root_agent.name}' created with sub-agent: '{build_orchestration_agent.name}'.")
    except Exception as e:
        print(f"❌ Could not create Root Unity Agent. Error: {e}")
else:
    print("❌ Cannot create Root Unity Agent because the BuildOrchestrationAgent failed to initialize.")

# --- Helper function for async interaction (from ADK quickstart) ---
async def call_agent_async(
    query: str, runner: Runner, user_id: str, session_id: str
) -> None:
    print(f"\n--- User: {query} ---")
    response = await runner.send_message(
        message=query, user_id=user_id, session_id=session_id
    )
    print(f"--- Agent: {response.text} ---")
    if response.tool_calls:
        for tool_call in response.tool_calls:
            print(f"--- Tool Call: {tool_call.tool_name}({tool_call.args}) ---")
    if response.tool_results:
        for tool_result in response.tool_results:
            print(f"--- Tool Result: {tool_result.result} ---")

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
        print("\n--- Test 1: Trigger a build for the 'main' branch ---")
        await call_agent_async(
            query="Please build the game for the 'main' branch.",
            runner=runner_unity_team, user_id=USER_ID, session_id=SESSION_ID
        )

        print("\n--- Test 2: Trigger a build for a specific commit hash ---")
        await call_agent_async(
            query="Can you build the game using commit 'abcdef1234567890abcdef1234567890'?",
            runner=runner_unity_team, user_id=USER_ID, session_id=SESSION_ID
        )

        print("\n--- Test 3: Request for a scene launch (should be out of scope for now) ---")
        await call_agent_async(
            query="Run the game in Level1.",
            runner=runner_unity_team, user_id=USER_ID, session_id=SESSION_ID
        )

        print("\n--- Test 4: General Query (should be out of scope) ---")
        await call_agent_async(
            query="Tell me a joke.",
            runner=runner_unity_team, user_id=USER_ID, session_id=SESSION_ID
        )


# --- Execute the async function ---
if __name__ == "__main__":
    print("Executing using 'asyncio.run()'...")
    try:
        asyncio.run(run_unity_automation_conversation())
    except Exception as e:
        print(f"An error occurred during conversation: {e}")