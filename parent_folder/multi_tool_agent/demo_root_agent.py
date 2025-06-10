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
            description="A simple root agent that chats and monitors messages.",
            model="gemini-2.0-flash",
            sub_agents=[listener_fanout],
            instruction=(
                "You are a helpful agent who is also using a subagent to listen for pub/sub messages and"
                "report any incoming messages back to the user"
            ),
        )

    async def _run_async_impl(self, ctx):
        yield Event(content=ModelContent("I'll keep an eye on background messages."), author=self.name)

        # Get sub-agent (listener fanout)
        listener_fanout = self.sub_agents[0]

        while True:
            async for event in listener_fanout._run_async_impl(ctx):
                yield event
            await asyncio.sleep(1)

# -------------- Runner ------------------

async def main():

    root_agent = RootAgent()
    runner = Runner(
        app_name=APP_NAME,
        agent=root_agent,
        session_service=InMemorySessionService()
    )

    await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id="dev_user_01",
        session_id="example_session"
    )

    # Start initial conversation
    async_gen = runner.run_async(
        user_id="dev_user_01",
        session_id="example_session",
        new_message=UserContent("Starting root agent")
    )

    async for event in async_gen:
        print(f"[{event.author}] {event.content.parts[0] if len(event.content.parts) > 0 else ''}")


if __name__ == "__main__":
    asyncio.run(main())