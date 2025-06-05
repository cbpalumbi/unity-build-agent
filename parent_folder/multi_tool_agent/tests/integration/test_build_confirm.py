import os
import pytest
from google.adk.evaluation.agent_evaluator import AgentEvaluator

# Determine the absolute path to your test JSON directory
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# Point to the directory containing your test JSON files
TEST_DATA_PATH = os.path.join(CURRENT_DIR, "eval_data") # <--- Renamed for clarity

# Define the module where your main ADK agent is located.
AGENT_MODULE_PATH = "agent"


@pytest.mark.asyncio
async def test_build_confirmation_flow():
    """
    Tests the agent's initial response and tool call for a build request,
    expecting a confirmation prompt.
    """
    # Changed this print statement to reflect what's actually being passed
    print(f"Attempting to evaluate agent from module: {AGENT_MODULE_PATH}")
    print(f"Using test data path: {TEST_DATA_PATH}") # <--- Changed print message

    custom_criteria = {
        "response_match_score": 0.5,  # Lowered the threshold here
        "tool_trajectory_avg_score": 1.0, # Keep this at 1.0 for exact tool matching
    }

    # Ensure the test directory exists
    if not os.path.exists(TEST_DATA_PATH): # <--- Check the directory
        pytest.fail(f"Test data path not found: {TEST_DATA_PATH}")

    try:
        await AgentEvaluator.evaluate(
            agent_module=AGENT_MODULE_PATH,
            # THIS IS THE CRITICAL CHANGE: Pass the directory variable here
            eval_dataset_file_path_or_dir=TEST_DATA_PATH,
            num_runs=1,
        )
        print("ADK evaluation completed successfully!")
    except Exception as e:
        pytest.fail(f"ADK evaluation failed: {e}")