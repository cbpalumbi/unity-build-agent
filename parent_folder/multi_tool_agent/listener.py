# listener.py

import asyncio
import json
import base64
import os
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
    and simply prints them.
    """
    if not GOOGLE_CLOUD_PROJECT_ID or GOOGLE_CLOUD_PROJECT_ID == "your-gcp-project-id":
        print("ERROR: GOOGLE_CLOUD_PROJECT_ID is not set. Please set it as an environment variable or hardcode.")
        return

    subscriber = pubsub_v1.SubscriberClient()

    print(f"\n--- Starting simple Pub/Sub listener on: {subscription_path} ---")

    def callback(message: pubsub_v1.subscriber.message.Message):
        print(f"--- Pub/Sub Listener: Received message ID: {message.message_id} ---")
        try:
            # Decode the message data (payload)
            message_data_raw = message.data.decode('utf-8')
            print(f"--- Pub/Sub Listener: Raw message payload: {message_data_raw} ---")

            # Also print attributes, which contain build_id and session_id
            print(f"--- Pub/Sub Listener: Message attributes: {message.attributes} ---")

        except Exception as e:
            print(f"--- Pub/Sub Listener Error processing message {message.message_id}: {e} ---")
        finally:
            # ALWAYS acknowledge the message to prevent it from being redelivered.
            message.ack()
            print(f"--- Pub/Sub Listener: Acknowledged message {message.message_id}. ---")

    # Start the subscriber in a non-blocking way
    future = subscriber.subscribe(subscription_path, callback)

    try:
        # Keep the listener running indefinitely
        await future.result() # This will block until the subscription is cancelled or an error occurs
    except TimeoutError:
        print("--- Pub/Sub Listener timed out. ---")
        future.cancel()
        await subscriber.close()
    except Exception as e:
        print(f"--- Pub/Sub Listener experienced an error: {e} ---")
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
        print(f"Subscription '{completion_subscription_path}' already exists.")
    except Exception as e:
        print(f"Subscription '{completion_subscription_path}' not found, creating it on topic '{UNITY_BUILD_COMPLETION_TOPIC_ID}'...")
        topic_path_for_sub = subscriber_client.topic_path(GOOGLE_CLOUD_PROJECT_ID, UNITY_BUILD_COMPLETION_TOPIC_ID)
        subscriber_client.create_subscription(
            request={"name": completion_subscription_path, "topic": topic_path_for_sub}
        )
        print(f"Subscription '{completion_subscription_path}' created.")
    finally:
        subscriber_client.close()

    # Start the simple listener
    await listen_for_build_completions_simple(completion_subscription_path)

if __name__ == "__main__":
    asyncio.run(main_listener())