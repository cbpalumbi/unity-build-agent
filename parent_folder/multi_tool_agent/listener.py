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
        try:
            # Decode the message data (payload)
            message_data_raw = message.data.decode('utf-8')

            # IF this is the actual data you want the parent to process as JSON:
            try:
                notification_payload = json.loads(message_data_raw)
                # Convert back to JSON string to ensure it's on one line for readline()
                # Or, if you want the raw string, just print message_data_raw
                try:
                    sys.stdout.write(json.dumps(notification_payload) + '\n') # Send JSON to stdout
                    sys.stdout.flush() # Important for line-buffering to work consistently

                    sys.stderr.write(f"--- Pub/Sub Listener Message: dumped json to stdout ---\n")
                    sys.stderr.flush()
                except BrokenPipeError:
                    sys.stderr.write("--- Pub/Sub Listener Error: Parent process pipe broken. Listener exiting gracefully.")

            except json.JSONDecodeError:
                # If it's not JSON, perhaps you still want to send the raw string to stdout
                # Or handle this case by sending a specific error message/format
                
                # sys.stdout.write(message_data_raw + '\n') # Or a different format for non-JSON
                # sys.stdout.flush()
                # You can still use sys.stderr for internal debugging/warning messages:
                sys.stderr.write(f"--- Pub/Sub Listener Warning: Message data is not valid JSON. Treating as raw string. ---\n")
                sys.stderr.flush()


            sys.stderr.write(f"--- Pub/Sub Listener: Raw message payload: {message_data_raw} ---\n")
            sys.stderr.flush() # problem? 
            

            # # Add attributes to the payload. Attributes are often crucial for metadata.
            # # Convert Protobuf Map to a regular dictionary for JSON serialization
            # notification_payload["attributes"] = dict(message.attributes)

            # # Add message_id for traceability
            # notification_payload["message_id"] = message.message_id
            # sys.stderr.write("below")
            # # Output the complete notification payload as a single JSON line to stdout
            # json_output = json.dumps(notification_payload)
            # print(json_output)
            # sys.stdout.write(json_output + "\n")
            # sys.stdout.flush() # CRUCIAL: Flush stdout immediately so the parent process can read it

        except Exception as e:
            sys.stderr.write(f"--- Pub/Sub Listener Error processing message {message.message_id}: {e} ---\n")
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