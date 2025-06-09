# multi_tool_agent/tests/conftest.py
import pytest
from unittest.mock import MagicMock

# This fixture will be automatically discovered by pytest
# It runs *before* any test modules are imported.
@pytest.fixture(autouse=True)
def mock_gcs_client_globally(monkeypatch):
    """
    Globally mocks the google.cloud.storage.Client to prevent actual GCS
    interactions and authentication errors during test collection/import.
    """
    # Create a mock for the Blob object's generate_signed_url method
    # This will be the mock that the 'real' generate_signed_url in agent.py
    # (when it uses the mocked GCS client) will call.
    mock_blob_instance = MagicMock()
    mock_blob_instance.generate_signed_url.return_value = "https://mocked-by-conftest.example.com/bucket/blob?signature=CONTEST"

    # Create a mock for the Bucket object's blob method
    mock_bucket_instance = MagicMock()
    mock_bucket_instance.blob.return_value = mock_blob_instance

    # Create a mock for the Client object's bucket method
    mock_client_instance = MagicMock()
    mock_client_instance.bucket.return_value = mock_bucket_instance

    # Patch google.cloud.storage.Client at the point it's imported in 'agent.py'.
    # This assumes 'agent.py' does 'from google.cloud import storage'
    # and then calls 'storage.Client()'.
    # IMPORTANT: The string path here must match exactly how storage.Client is accessed
    # in your 'agent.py'. If 'agent.py' does 'import google.cloud.storage as gcs',
    # then it would be 'multi_tool_agent.agent.gcs.Client'.
    # If it does 'from google.cloud.storage import Client', then it would be
    # 'multi_tool_agent.agent.Client'.
    monkeypatch.setattr('google.cloud.storage.Client', MagicMock(return_value=mock_client_instance))

    # You could also explicitly mock the generate_signed_url method of the
    # UnityAutomationOrchestrator if it's consistently instantiated.
    # However, mocking the lowest-level dependency (GCS Client) is often more robust.
    pass