import pytest
from unittest.mock import MagicMock, patch
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from agent import generate_signed_url

from agent import generate_signed_url

@patch("agent.storage.Client")
def test_generate_signed_url(mock_storage_client):
    # Set up mocks
    mock_blob = MagicMock()
    mock_blob.generate_signed_url.return_value = "https://signed.url/fake"

    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    mock_client_instance = MagicMock()
    mock_client_instance.bucket.return_value = mock_bucket

    mock_storage_client.return_value = mock_client_instance

    # Inputs
    bucket_name = "my-test-bucket"
    blob_name = "builds/game.zip"
    expiration_minutes = 30

    # Call the function
    signed_url = generate_signed_url(bucket_name, blob_name, expiration_minutes)

    # Assertions
    assert signed_url == "https://signed.url/fake"
    mock_storage_client.assert_called_once()
    mock_client_instance.bucket.assert_called_once_with(bucket_name)
    mock_bucket.blob.assert_called_once_with(blob_name)
    mock_blob.generate_signed_url.assert_called_once_with(
        version="v4",
        expiration=pytest.approx(
            signed_url_expiration_delta(expiration_minutes),
            rel=0.05  # Allow some timing fuzziness
        ),
        method="GET"
    )

# === Error: Empty bucket name ===
def test_generate_signed_url_empty_bucket():
    with pytest.raises(Exception):
        generate_signed_url("", "some/file.zip")


# === Error: Empty blob name ===
def test_generate_signed_url_empty_blob():
    with pytest.raises(Exception):
        generate_signed_url("my-bucket", "")


# === Error: Negative expiration time ===
def test_generate_signed_url_negative_expiration():
    with pytest.raises(ValueError):
        generate_signed_url("bucket", "file.zip", expiration_minutes=-5)


# === Simulate GCS exception ===
@patch("agent.storage.Client")
def test_generate_signed_url_gcs_failure(mock_storage_client):
    mock_storage_client.side_effect = Exception("GCS client failed")
    with pytest.raises(Exception, match="GCS client failed"):
        generate_signed_url("bucket", "file.zip")

@patch("agent.storage.Client")
def test_generate_signed_url_specific_asset(mock_storage_client):
    bucket_name = "my_adk_unity_hackathon_builds_2025"
    blob_name = (
        "game-builds/universal/main/1fe522b566d272fb22a71a30ade5f3bd8199d057/"
        "1fe522b566d272fb22a71a30ade5f3bd8199d057.zip"
    )

    mock_blob = MagicMock()
    mock_blob.generate_signed_url.return_value = "https://signed-url.com/specific.zip"
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    mock_storage_client.return_value = mock_client

    url = generate_signed_url(bucket_name, blob_name)

    assert url == "https://signed-url.com/specific.zip"
    mock_storage_client.assert_called_once()
    mock_client.bucket.assert_called_with(bucket_name)
    mock_bucket.blob.assert_called_with(blob_name)
    mock_blob.generate_signed_url.assert_called_once()


# Optional helper if you want stricter expiration checks
from datetime import timedelta

def signed_url_expiration_delta(minutes):
    return timedelta(minutes=minutes)
