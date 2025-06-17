import sys, os
print("PYTHONPATH:", os.environ.get("PYTHONPATH"))
print("sys.path:", sys.path)
import google.adk.cli  # See if this succeeds
print("google.adk.cli imported successfully")
