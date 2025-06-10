import asyncio
from google.adk.runners import Runner, InMemorySessionService
from google.genai.types import UserContent
from pubsub_listener_agent import pubsub_loop_agent 

APP_NAME = "unity_build_orchestrator"

async def main():
    runner = Runner(app_name=APP_NAME, agent=pubsub_loop_agent, session_service=InMemorySessionService())

    await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id="dev_user_01",
        session_id="build_listener_session"
    )

    async_gen = runner.run_async(
        user_id="dev_user_01",
        session_id="build_listener_session",
        new_message=UserContent("Starting pub/sub listener agent")
    )
    async for event in async_gen:
        pass

if __name__ == "__main__":
    asyncio.run(main())
