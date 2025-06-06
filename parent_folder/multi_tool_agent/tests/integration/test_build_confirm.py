import os
import pytest
from google.adk.evaluation.agent_evaluator import AgentEvaluator

# Determine the absolute path to your test JSON directory
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# Define the module where your main ADK agent is located.
AGENT_MODULE_PATH = "agent"


@pytest.mark.asyncio
async def test_build_confirmation_flow():
    """
    Tests the agent's initial response and tool call for a build request,
    expecting a confirmation prompt. (Single turn scenario)
    """
    # Point to the specific directory for this test scenario
    TEST_DATA_DIR = os.path.join(CURRENT_DIR, "eval_data_build_confirm")

    print(f"Attempting to evaluate agent from module: {AGENT_MODULE_PATH}")
    print(f"Using test data path: {TEST_DATA_DIR}")

    if not os.path.exists(TEST_DATA_DIR):
        pytest.fail(f"Test data path not found: {TEST_DATA_DIR}")

    try:
        await AgentEvaluator.evaluate(
            agent_module=AGENT_MODULE_PATH,
            eval_dataset_file_path_or_dir=TEST_DATA_DIR,
            num_runs=1,
        )
        print("ADK evaluation completed successfully for Build Confirmation Flow!")
    except Exception as e:
        pytest.fail(f"ADK evaluation for Build Confirmation Flow failed: {e}")


@pytest.mark.asyncio
async def test_multi_turn_build_and_status_flow():
    """
    Tests the agent's full multi-turn build and status check conversation flow.
    """
    # Point to the specific directory for this test scenario
    TEST_DATA_DIR = os.path.join(CURRENT_DIR, "eval_data_build_flow")

    print(f"Attempting to evaluate agent from module: {AGENT_MODULE_PATH}")
    print(f"Using test data path: {TEST_DATA_DIR}")

    if not os.path.exists(TEST_DATA_DIR):
        pytest.fail(f"Test data path not found: {TEST_DATA_DIR}")

    try:
        await AgentEvaluator.evaluate(
            agent_module=AGENT_MODULE_PATH,
            eval_dataset_file_path_or_dir=TEST_DATA_DIR,
            num_runs=1,
        )
        print("ADK evaluation completed successfully for Multi-Turn Flow!")
    except Exception as e:
        pytest.fail(f"ADK evaluation for Multi-Turn Flow failed: {e}")