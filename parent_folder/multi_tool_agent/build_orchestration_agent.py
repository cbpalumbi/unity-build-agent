import json
import uuid
import os
from datetime import datetime

from dotenv import load_dotenv
from google.cloud import pubsub_v1, storage

load_dotenv()

GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
UNITY_BUILD_PUB_SUB_TOPIC_ID = os.getenv("UNITY_BUILD_PUB_SUB_TOPIC_ID")
GCS_BUILD_BUCKET_NAME = os.getenv("GCS_BUILD_BUCKET_NAME")

storage_client = storage.Client(project=GOOGLE_CLOUD_PROJECT)

def publish_build_request(
    command: str,
    branch_name: str,
    commit_hash: str,
    is_test_build: bool,
) -> dict:
    """Publishes a build request message to the Google Cloud Pub/Sub topic.

    This function is intended to be used as a tool by the BuildOrchestrationAgent. 
    It does not report build or request ids to the user.

    Args:
        command (str): The primary command for the VM (e.g., "start_build", "checkout_and_build").
        branch_name (str): The Git branch name to build from.
        commit_hash (str): The specific Git commit hash (full SHA preferred).
        is_test_build (bool): If True, indicates a test build (no actual Unity build).

    Returns:
        dict: Status and message or error details.
    """
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(GOOGLE_CLOUD_PROJECT, UNITY_BUILD_PUB_SUB_TOPIC_ID)

    build_id = str(uuid.uuid4()) # unique hash for this build request

    # Create a structured dictionary for the payload
    message_data = {
        "build_id": build_id, 
        "command": command,
        "branch_name": branch_name,
        "commit_hash": commit_hash,
        "is_test_build": is_test_build,
        "request_timestamp": datetime.now().isoformat(), # Add timestamp for logging/tracking
    }

    # Encode the dictionary to a JSON string, then to bytes
    data_bytes = json.dumps(message_data).encode('utf-8')
    attributes = {}

    try:
        print(f"--- Tool: publish_build_request for build_id: '{build_id}' ---")
        print(f"Payload: {json.dumps(message_data, indent=2)}") # For better logging
        future = publisher.publish(topic_path, data=data_bytes, **attributes)
        message_id = future.result()
        print(f"SUCCESS: Published message with Pub/Sub message ID: {message_id}")
        return {"status": "success", "build_id": build_id, "message_id": message_id}
    except Exception as e:
        print(f"ERROR: Failed to publish message: {e}")
        return {"status": "error", "message": str(e)}
    
def _get_build_object_path(branch: str, commit: str) -> str:
    """Constructs the expected GCS object path for a Unity build artifact
    following the scheme: game-builds/universal/<branch>/<commit>/<commit>.zip
    """
    # The file name is the commit hash followed by .zip
    file_name = f"{commit}.zip"
    return f"game-builds/universal/{branch}/{commit}/{file_name}"

    
def check_gcs_cache(branch: str, commit: str) -> bool:
    """Checks if a build for a specific branch and commit exists in the GCS cache.

    Args:
        branch: The Git branch name.
        commit: The Git commit hash.
    Returns:
        bool: True if the build is found in cache, False otherwise.
    """
    if not GCS_BUILD_BUCKET_NAME:
        print("[Cache Tool] GCS_BUILD_BUCKET_NAME environment variable not set. Cannot check cache.")
        return False # Or raise an error, depending on desired strictness

    print(f"[Cache Tool] Checking GCS cache for {branch}/{commit} in bucket '{GCS_BUILD_BUCKET_NAME}'...")
    try:
        bucket = storage_client.bucket(GCS_BUILD_BUCKET_NAME)
        # Check for the existence of the main build artifact
        blob_name = _get_build_object_path(branch, commit) # Assume a main build file
        blob = bucket.blob(blob_name)
        
        exists = blob.exists()
        print(f"[Cache Tool] Build for {branch}/{commit} {'FOUND' if exists else 'NOT FOUND'} in cache.")
        return exists
    except Exception as e:
        print(f"ERROR: Failed to check GCS cache: {e}")
        return False
    
BUILD_AGENT_TOOL_FUNCTIONS = [
    publish_build_request,
    check_gcs_cache
]