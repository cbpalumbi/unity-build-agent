#!/bin/bash

# Default to web if no argument is passed
MODE="$1"

if [[ "$MODE" == "-web" ]]; then
  echo "🔵 Starting in web mode..."
  export APP_MODE="web"
  PYTHONPATH=multi_tool_agent/my_google_adk adk web --log_level WARNING

elif [[ "$MODE" == "-terminal" ]]; then
  echo "🟢 Starting in terminal mode..."
  export APP_MODE="terminal"
  PYTHONPATH=multi_tool_agent/my_google_adk adk run multi_tool_agent

else
  echo "⚠️  Usage: ./start_local.sh [-web | -terminal]"
  exit 1
fi
