import asyncio
import os
from google.adk.runners import Runner, InMemorySessionService
from google.adk.events import Event
from google.adk.agents import ParallelAgent, LlmAgent
from google.genai.types import ModelContent, UserContent
from pubsub_listener_agent import PubSubListenerAgent
from dotenv import load_dotenv
load_dotenv()
APP_NAME = os.getenv("APP_NAME", "default_app_name")

class RootAgent(LlmAgent):

    def __init__(self):

        pubsub_agent = PubSubListenerAgent()
        # Create the background listener fanout (just 1 agent here, but could be more)
        listener_fanout = ParallelAgent(
            name="ListenerFanout",
            description="Runs background agents",
            sub_agents=[pubsub_agent]
        )

        # LLM agent with the listener fanout as a sub-agent
        super().__init__(
            name="RootAgent",
            description="A helpful conversational agent that also monitors messages.",
            model="gemini-2.0-flash",
            sub_agents=[listener_fanout],
            instruction=(
                "You are a friendly and helpful AI assistant. Your main goal is to engage in natural "
                "conversations with the user. Additionally, you are constantly monitoring for incoming "
                "Pub/Sub messages from a sub-agent and will report any important information "
                "from those messages to the user in a timely and clear manner. "
                "Always be polite, proactive, and ready to assist."
            ),
        )

    async def _run_async_impl(self, ctx):
        # The LlmAgent's core functionality is to respond to the last user message.
        # This initial greeting should happen once at the beginning of an interactive session
        # or be triggered by the first user message.
        # Since the runner handles the "initial message" to kick things off,
        # the LLM's response to that first message will be its greeting.

        # This loop is specifically for handling events from the sub-agent (PubSubListenerAgent)
        listener_fanout = self.sub_agents[0]
        async for event in listener_fanout._run_async_impl(ctx):
            # When a message comes from the PubSubListenerAgent, it will be yielded here.
            # You might want to add some logic here to format the Pub/Sub messages
            # into a more user-friendly conversational response.
            print("test")
            yield event
        # If no new pub/sub messages, the agent will wait.
        # The LlmAgent will also be listening for new user input from the runner.
        # There's no need for an explicit asyncio.sleep(1) here as the runner manages the loop for user input.

# -------------- Runner ------------------

async def main():

    root_agent = RootAgent()
    runner = Runner(
        app_name=APP_NAME,
        agent=root_agent,
        session_service=InMemorySessionService()
    )

    user_id = "dev_user_01"
    session_id = "example_session"

    await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id
    )

    # Initial greeting from the agent by sending an empty message to trigger its first response
    # The LlmAgent's instruction should guide its initial conversational output.
    print(f"[{root_agent.name}] Initializing...")
    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=UserContent("")):
        if event.content and event.content.parts:
            print(f"[{event.author}] {event.content.parts[0].text}")

    print("\n--- Start chatting with the agent! (Type 'exit' to quit) ---\n")

    while True:
        user_input = await asyncio.to_thread(input, "You: ")
        if user_input.lower() == 'exit':
            break

        # Send the user's input to the agent
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=UserContent(user_input)
        ):
            if event.content and event.content.parts:
                # Assuming the content is text, access the first part's text
                print(f"[{event.author}] {event.content.parts[0].text}")
            elif event.author == "PubSubListenerAgent" and event.content:
                # Handle Pub/Sub events specifically if they have a different structure
                print(f"[PubSub Monitor] {event.content.parts[0].text}")

if __name__ == "__main__":
    asyncio.run(main())
