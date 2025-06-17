FROM python:3.9-slim-buster

WORKDIR /app

COPY requirements.txt /app/requirements.txt

ENV PIP_CACHE_DIR=/root/.cache/pip

RUN pip install -r requirements.txt

# copy the rest of the source code, including my version of the google adk
COPY . /app

# Uninstall adk from PyPI if it snuck in via requirements.txt
RUN pip uninstall -y google-adk

# Install local modified ADK version
#RUN pip install /app/multi_tool_agent/my_google_adk

ENV PYTHONPATH="/app/multi_tool_agent/my_google_adk:/app"

COPY multi_tool_agent/my_google_adk /tmp/my_google_adk

# Install local modified ADK to site-packages (not depending on PYTHONPATH)
RUN pip install /tmp/my_google_adk
RUN python3 -c "import google.adk; print(google.adk.__file__)"

EXPOSE 8080

#CMD ["python3", "-c", "import google.adk; print('✅ ADK import success'); import os, sys; print('PYTHONPATH:', os.getenv('PYTHONPATH')); print('sys.path:', sys.path)"]
#CMD ["python", "multi_tool_agent/start_test.py"]

CMD ["adk", "web", ".", "--host", "0.0.0.0", "--port", "8080"]
