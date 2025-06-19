import json
import uuid
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from urllib.parse import quote, quote_plus
from google.cloud import pubsub_v1, storage
from google.adk.tools import ToolContext, FunctionTool
from google.genai.types import Part

load_dotenv()

GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
UNITY_BUILD_PUB_SUB_TOPIC_ID = os.getenv("UNITY_BUILD_PUB_SUB_TOPIC_ID")
GCS_BUILD_BUCKET_NAME = os.getenv("GCS_BUILD_BUCKET_NAME")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
APP_MODE = os.getenv("APP_MODE", "web")  # default to web mode

RUNNING_IN_TERMINAL = APP_MODE == "terminal"

storage_client = storage.Client(project=GOOGLE_CLOUD_PROJECT)

def get_session_id(tool_context: ToolContext):
    return tool_context._invocation_context.session.id

get_session_id_tool = FunctionTool(func=get_session_id)

def publish_asset_build_request(
    command: str,
    session_id: str
) -> dict:
    """Publishes an asset build request message to the Google Cloud Pub/Sub topic.

    This function is intended to be used as a tool by the AssetPreviewAgent.
    It requests the backend listener to create an asset bundle from user-uploaded models.

    Args:
        command (str): The command to execute, typically 'asset-build'.
        session_id

    Returns:
        dict: Status and message or error details.
    """
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(GOOGLE_CLOUD_PROJECT, UNITY_BUILD_PUB_SUB_TOPIC_ID)

    build_id = str(uuid.uuid4())

    gcs_asset_location_url = (
        f"gs://{GCS_BUILD_BUCKET_NAME}/user-asset-files/{session_id}/assets/"
    )

    # Create structured message payload
    message_data = {
        "build_id": build_id,
        "command": command,  # should be "asset-build"
        "gcs_asset_location_url": gcs_asset_location_url,
        "request_timestamp": datetime.now().isoformat(),
        "session_id": session_id  
    }

    data_bytes = json.dumps(message_data).encode('utf-8')
    attributes = {}

    try:
        print(f"--- Tool: publish_asset_build_request for build_id: '{build_id}' ---")
        print(f"Payload: {json.dumps(message_data, indent=2)}")
        future = publisher.publish(topic_path, data=data_bytes, **attributes)
        message_id = future.result()
        print(f"SUCCESS: Published message with Pub/Sub message ID: {message_id}")
        return {"status": "success", "build_id": build_id, "message_id": message_id}
    except Exception as e:
        print(f"ERROR: Failed to publish message: {e}")
        return {"status": "error", "message": str(e)}

def upload_dummy_glb_and_get_signed_url(session_id: str):
    """
    Upload a local dummy GLB file from disk to the GCS bucket for the session,
    then generate a signed PUT URL for it. Used for terminal version of app
    """

    dummy_path = "multi_tool_agent/dummy_glb/example.glb"  # local dummy file path

    if not os.path.exists(dummy_path):
        print(f"No glb file found at {dummy_path}")
        return
    
    dest_blob_path = f"user-asset-files/{session_id}/assets/my-asset.glb"

    bucket = storage_client.bucket(GCS_BUILD_BUCKET_NAME)
    blob = bucket.blob(dest_blob_path)

    # Upload the file to GCS (overwrite if exists)
    blob.upload_from_filename(dummy_path)
    print(f"Uploaded dummy GLB to gs://{GCS_BUILD_BUCKET_NAME}/{dest_blob_path}")
    
    return dest_blob_path

def generate_signed_put_url(session_id: str) -> tuple[str, str]:
    filename = f"user-asset-files/{session_id}/assets/my-asset.glb"
    client = storage.Client()
    blob = client.bucket(GCS_BUILD_BUCKET_NAME).blob(filename)

    signed_url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=60),
        method="PUT"
    )

    return signed_url, filename

def generate_upload_url(session_id: str) -> str:
    """
    Generates a url to an HTML form where the user can upload their glb file.

    Args: 
        session_id
    Returns:
        Part: text with link to html form
    """
    if RUNNING_IN_TERMINAL:
        # Terminal mode: skip web form, upload dummy file automatically and return dummy str
        path = upload_dummy_glb_and_get_signed_url(session_id)
        #Part.from_text(text="Terminal mode: uploading dummy GLB...")
        return path

    signed_url, filename = generate_signed_put_url(session_id)
    upload_url_base = f"{APP_BASE_URL}/api/upload?"
    upload_url = f"{upload_url_base}session_id={quote(str(session_id))}&signed_url={quote_plus(str(signed_url))}&gcs_path={quote_plus(str(filename))}"
    print(f"Generated upload URL: ", upload_url)
    
    #html = f'<a href="{upload_url}" target="_blank" rel="noopener noreferrer">Click here to upload your .glb file</a>'

    return upload_url


# def _get_build_object_path(branch: str, commit: str) -> str:
#     """Constructs the expected GCS object path for a Unity build artifact
#     following the scheme: game-builds/universal/<branch>/<commit>/<commit>.zip
#     """
#     # The file name is the commit hash followed by .zip
#     file_name = f"{commit}.zip"
#     return f"game-builds/universal/{branch}/{commit}/{file_name}"

# def generate_signed_url_for_build(branch: str, commit: str, expiration_minutes: int = 60) -> str:
#     """Generates a signed URL for a specific Unity build artifact in GCS.
#     Use this tool when a user asks for a download link for a cached build,
#     providing the branch and commit hash.

#     Args:
#         branch: The Git branch name for the build (e.g., "main").
#         commit: The Git commit hash for the build.
#         expiration_minutes: How long the signed URL should be valid for (in minutes). Defaults to 60.
#     Returns:
#         str: The signed URL, or an error message if generation fails.
#     """
#     if not GCS_BUILD_BUCKET_NAME:
#         return "Error: GCS_BUILD_BUCKET_NAME environment variable not set. Cannot generate URL."

#     print(f"[GCS Tool] Generating signed URL for build on {branch}/{commit}...")
#     try:
#         bucket = storage_client.bucket(GCS_BUILD_BUCKET_NAME)
#         # Use the helper to construct the full blob path
#         blob_name = _get_build_object_path(branch, commit)
#         blob = bucket.blob(blob_name)

#         if not blob.exists():
#             return f"Error: Build artifact '{blob_name}' not found in cache. Cannot generate URL."

#         expiration_time = datetime.now(tz=timezone.utc) + timedelta(minutes=expiration_minutes)
#         url = blob.generate_signed_url(expiration=expiration_time)
#         print(f"[GCS Tool] Generated signed URL (valid for {expiration_minutes} min): {url}")
#         return url
#     except Exception as e:
#         return f"Error generating signed URL: {e}"
    
ASSET_AGENT_TOOL_FUNCTIONS = [
    publish_asset_build_request,
    get_session_id_tool,
    generate_upload_url
    #generate_signed_url_for_build,
]