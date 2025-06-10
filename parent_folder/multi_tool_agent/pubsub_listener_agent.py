# pubsub_listener_agent.py

import asyncio
import os
import json
from google.cloud import pubsub_v1
from google.adk.agents import LoopAgent, BaseAgent
from google.adk.events import Event
from google.genai.types import ModelContent
from google.adk.agents.invocation_context import InvocationContext
from google.api_core.exceptions import DeadlineExceeded

# Pub/Sub config (make sure these are set in your env or manually here)
PROJECT_ID = os.getenv("PROJECT_ID", "default_project_id")
APP_NAME =  os.getenv("APP_NAME", "default_app_name")
SUBSCRIPTION_NAME = os.getenv("SUBSCRIPTION_NAME", "default_subscription_name")
USER_ID = "user_001"
SESSION_ID = "pubsub_listener_session"

SUBSCRIPTION_ID = f"{SUBSCRIPTION_NAME}-{APP_NAME}"
completion_subscription_path = f"projects/{PROJECT_ID}/subscriptions/{SUBSCRIPTION_ID}"

class PubSubBuildListenerAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="PubSubBuildListenerAgent", description="Listens to GCP Pub/Sub and emits ADK messages.")

        # initialize custom vars after base Pydantic setup
        object.__setattr__(self, 'subscriber', pubsub_v1.SubscriberClient())
        object.__setattr__(self, 'subscription_path', self.subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_ID))

    async def _run_async_impl(self, context: InvocationContext):
        print("Starting pub/sub listener...")
        while True:
            try:
                # Pull messages synchronously but with timeout to avoid blocking forever
                response = self.subscriber.pull(
                    request={
                        "subscription": self.subscription_path,
                        "max_messages": 1,
                    },
                    timeout=5.0  # non-blocking
                )

                if not response.received_messages:
                    # No messages, just wait a short bit before retrying
                    await asyncio.sleep(1)
                    continue

                for received_message in response.received_messages:
                    try:
                        payload = json.loads(received_message.message.data.decode("utf-8"))
                        print(f"[PubSub Agent] Received message: {payload}")

                        # Emit event for this message
                        yield Event(
                            content=ModelContent(f"🎉 Received pubsub notification: {payload}"),
                            author=self.name  # Proper ADK pattern
                        )

                    except Exception as e:
                        print(f"[PubSub Agent] Error processing message: {e}")

                    # Acknowledge the message
                    self.subscriber.acknowledge(
                        request={
                            "subscription": self.subscription_path,
                            "ack_ids": [received_message.ack_id],
                        }
                    )
            except DeadlineExceeded:
                # This happens if the server times out waiting for messages; just retry.
                await asyncio.sleep(1)
            except Exception as e:
                print(f"[PubSub Agent] Exception in run_async loop: {e}")
                await asyncio.sleep(5)  # Backoff on error


# Wrap it in a LoopAgent
pubsub_loop_agent = LoopAgent(
    name="PubSubLoopAgent",
    sub_agents=[PubSubBuildListenerAgent()],
    max_iterations=1000000,  # Simulate "forever"
)
