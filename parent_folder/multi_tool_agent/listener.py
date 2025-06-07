# listener.py

import asyncio
import json
import base64
import os
import sys # Import sys to explicitly write to stdout and stderr
from google.cloud import pubsub_v1

# --- Configuration Variables ---
# IMPORTANT: This must match the project ID where your Pub/Sub topic and subscription are.
# It's best practice to read this from environment variables.
GOOGLE_CLOUD_PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT_ID", "cool-ruler-461702-p8") # <-- REPLACE or set env var
UNITY_BUILD_COMPLETION_TOPIC_ID = "unity-build-completion-topic" # <-- Make sure this matches your VM's topic
APP_NAME = "unity_build_orchestrator" # Used for consistent subscription naming, same as agent.py

# --- Basic Pub/Sub Listener for Build Completions ---
async def listen_for_build_completions_simple(subscription_path: str):
    """
    Listens for messages on the build completion Pub/Sub subscription
    and outputs them as JSON to stdout. All debug/log messages go to stderr.
    """
    if not GOOGLE_CLOUD_PROJECT_ID or GOOGLE_CLOUD_PROJECT_ID == "your-gcp-project-id":
        sys.stderr.write("ERROR: GOOGLE_CLOUD_PROJECT_ID is not set. Please set it as an environment variable or hardcode.\n")
        sys.stderr.flush()
        return

    subscriber = pubsub_v1.SubscriberClient()

    sys.stderr.write(f"--- Starting simple Pub/Sub listener on: {subscription_path} ---\n")
    sys.stderr.flush() # Ensure this is written immediately

    def callback(message: pubsub_v1.subscriber.message.Message):
        # All logging/debugging for message reception and processing goes to stderr
        sys.stderr.write(f"--- Pub/Sub Listener: Received message ID: {message.message_id} ---\n")
        sys.stderr.flush()

        notification_payload = {}
        message_data_utf8_string = "" # Initialize for broader scope
        message_data_json_string = "" # Initialize for broader scope

        try:
            # Step 1: Decode the raw message data bytes to a UTF-8 string.
            # This string will contain the Base64 encoded JSON from the sender.
            message_data_utf8_string = message.data.decode('utf-8')
            sys.stderr.write(f"DEBUG: Listener received raw UTF-8 string (Base64 encoded): {message_data_utf8_string}\n")
            sys.stderr.flush()

            # Step 2: Base64 decode the string to get the original JSON string.
            message_data_json_string = base64.b64decode(message_data_utf8_string).decode('utf-8')
            sys.stderr.write(f"DEBUG: Listener received Base64-decoded JSON string: {message_data_json_string}\n")
            sys.stderr.flush()

            # Step 3: Attempt to parse the Base64-decoded string as JSON.
            try:
                notification_payload = json.loads(message_data_json_string)
                sys.stderr.write(f"DEBUG: Listener successfully parsed JSON.\n")
                sys.stderr.flush()

                # If successfully parsed, send the JSON to stdout for the parent process.
                try:
                    sys.stdout.write(json.dumps(notification_payload) + '\n')
                    sys.stdout.flush()
                    sys.stderr.write(f"--- Pub/Sub Listener Message: Dumped parsed JSON to stdout ---\n")
                    sys.stderr.flush()
                except BrokenPipeError:
                    sys.stderr.write("--- Pub/Sub Listener Error: Parent process pipe broken. Listener exiting gracefully.\n")
                    sys.stderr.flush()

            except json.JSONDecodeError as e:
                # Handle cases where the Base64-decoded string isn't valid JSON.
                sys.stderr.write(f"ERROR: Listener failed to parse JSON from Base64-decoded string. Error: {e}\n")
                sys.stderr.write(f"ERROR: Malformed JSON string that caused error: {message_data_json_string}\n")
                sys.stderr.write(f"ERROR: Original Base64 encoded string (before Base64 decode): {message_data_utf8_string}\n")
                sys.stderr.flush()

            except Exception as e:
                # Catch any other unexpected errors during JSON parsing or stdout write.
                sys.stderr.write(f"ERROR: An unexpected error occurred during message processing: {e}\n")
                sys.stderr.write(f"DEBUG: String being processed at time of error: {message_data_json_string}\n")
                sys.stderr.flush()

        except Exception as e:
            # Catch errors during initial decoding or Base64 decoding.
            sys.stderr.write(f"ERROR: Failed to decode initial message data or perform Base64 decode: {e}\n")
            sys.stderr.flush()
        finally:
            # ALWAYS acknowledge the message to prevent it from being redelivered.
            message.ack()
            sys.stderr.write(f"--- Pub/Sub Listener: Acknowledged message {message.message_id}. ---\n")
            sys.stderr.flush()

    # Start the subscriber in a non-blocking way
    future = subscriber.subscribe(subscription_path, callback)

    try:
        # Keep the listener running indefinitely
        # This will block until the subscription is cancelled or an error occurs
        sys.stderr.write(f"--- Pub/Sub Listener: Listening for messages on {subscription_path}... ---\n")
        sys.stderr.flush()
        await future.result()
    except TimeoutError:
        sys.stderr.write("--- Pub/Sub Listener timed out. ---\n")
        sys.stderr.flush()
        future.cancel()
        await subscriber.close()
    except Exception as e:
        sys.stderr.write(f"--- Pub/Sub Listener experienced an error: {e} ---\n")
        sys.stderr.flush()
        future.cancel()
        await subscriber.close()

# --- Main entry point for the listener script ---
async def main_listener():
    # Define the subscription path for the completion topic
    # The subscription name should be consistent for this listener.
    completion_subscription_name = f"unity-build-completion-subscription-{APP_NAME}"
    completion_subscription_path = f"projects/{GOOGLE_CLOUD_PROJECT_ID}/subscriptions/{completion_subscription_name}"

    # --- Create a subscription if it doesn't exist (helpful for local testing) ---
    subscriber_client = pubsub_v1.SubscriberClient()
    try:
        subscriber_client.get_subscription(request={"subscription": completion_subscription_path})
        sys.stderr.write(f"Subscription '{completion_subscription_path}' already exists.\n") # <-- CHANGED TO sys.stderr
        sys.stderr.flush()
    except Exception as e:
        sys.stderr.write(f"Subscription '{completion_subscription_path}' not found, creating it on topic '{UNITY_BUILD_COMPLETION_TOPIC_ID}'...\n") # <-- CHANGED TO sys.stderr
        sys.stderr.flush()
        topic_path_for_sub = subscriber_client.topic_path(GOOGLE_CLOUD_PROJECT_ID, UNITY_BUILD_COMPLETION_TOPIC_ID)
        subscriber_client.create_subscription(
            request={"name": completion_subscription_path, "topic": topic_path_for_sub}
        )
        sys.stderr.write(f"Subscription '{completion_subscription_path}' created.\n") # <-- CHANGED TO sys.stderr
        sys.stderr.flush()
    finally:
        subscriber_client.close()

    # Start the simple listener
    await listen_for_build_completions_simple(completion_subscription_path)

if __name__ == "__main__":
    asyncio.run(main_listener())