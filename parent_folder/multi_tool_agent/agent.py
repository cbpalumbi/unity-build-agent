import os
import asyncio
import json
import uuid

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
        nobuild (bool): If True, sends a 'nobuild' attribute with the message,
                        indicating to the consumer that no actual build should occur.

    Returns:
        dict: Status and message or error details.
    """
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(GOOGLE_CLOUD_PROJECT_ID, UNITY_BUILD_PUB_SUB_TOPIC_ID)

    # The message payload is a string, which we'll Base64 encode before sending.
    # This aligns with how your PowerShell script expects it.
    data_bytes = message_payload.encode('utf-8')

    build_id = str(uuid.uuid4())
    nobuild = True # DEBUG SETTING HARDCODED !!! 

    # Prepare attributes. All attribute values must be strings.
    attributes = {
        "build_id": build_id
    }
    if nobuild:
        attributes["nobuild"] = "true" # Send "true" as a string

    try:
        print(f"--- Tool: publish_build_request called with payload: '{message_payload}', nobuild={nobuild} ---")
        future = publisher.publish(topic_path, data=data_bytes, **attributes) # Pass attributes using **
        message_id = future.result()
        print(f"SUCCESS: Published message with ID: {message_id}")
        return {
            "status": "success",
            "message": f"Build request published to Pub/Sub with ID: {message_id}",
            "message_payload": message_payload,
            "build_id": build_id,
            "nobuild_flag_sent": nobuild # Indicate if the flag was sent
        }
    except Exception as e:
        print(f"ERROR: Failed to publish message to Pub/Sub: {e}")
        return {
            "status": "error",
            "error_message": f"Failed to publish build request: {e}"
        }


def receive_build_completion(build_id: str, gcs_path: str) -> dict:
    """
    Receives a build completion message from the external system (e.g., VM).
    Updates the session state with the build's final status and GCS path.

    Args:
        build_id (str): The unique ID of the completed build.
        gcs_path (str): The Google Cloud Storage path where the build artifacts are located.

    Returns:
        dict: A status message indicating success or failure.
    """
    # NOTE: In a real scenario, this tool would be called internally by
    # a Pub/Sub listener that integrates with the ADK Runner.
    # For testing, we will simulate calling this tool via the Runner.

    print(f"--- Tool: receive_build_completion called with build_id: {build_id}, gcs_path: {gcs_path} ---")

    # This tool needs to access the session state to update it.
    # We can't directly access `session` or `runner` here in a standalone tool function
    # like this because tools are just functions. The ADK runner provides a way for tools
    # to access the current session state via `runner.set_session_state()`.
    # For now, let's keep it simple by assuming the agent (LLM) will use its
    # knowledge of the tool to formulate a response to the user.
    # The actual state update will be handled by the runner processing the tool's return.

    # This function just returns what the tool's result should be.
    # The runner will then decide how to update the session state based on this result.
    return {
        "status": "completed",
        "build_id": build_id,
        "gcs_path": gcs_path,
        "message": f"Build {build_id} is complete and available at {gcs_path}.",
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
        "You will receive build completion messages. When you receive a build completion message, "
        "inform the user that the build is complete and provide the GCS path. " 
        "based on the desired Git information (e.g., 'checkout_and_build:main' or 'checkout_and_build:specific_commit_hash')."
    ),
    description="Manages triggering remote Unity project builds via Pub/Sub.",
    tools=[publish_build_request, receive_build_completion] # Only the publishing tool here
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
            # --- Store the build_id if it's a publish_build_request result ---
            if tool_call.tool_name == "publish_build_request" and "build_id" in tool_result.result:
                build_id = tool_result.result["build_id"]

                # Retrieve the current session to update its state
                current_session = await runner.session_service.get_session(
                    app_name=runner.app_name,
                    user_id=user_id,
                    session_id=session_id
                )
                if "build_status" not in current_session.state:
                    current_session.state["build_status"] = {}
                current_session.state["build_status"][build_id] = "pending"

                # Update the session (important for persistence)
                await runner.session_service.update_session(current_session)

                print(f"--- Stored build_id: {build_id} in session state with status 'pending' ---")

