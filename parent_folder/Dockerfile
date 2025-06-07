# Use an official Python runtime as a parent image
FROM python:3.9-slim-buster

# Set the working directory in the container
# This WORKDIR will be the "current directory" for subsequent commands,
# mimicking where you run 'adk run .' locally.
WORKDIR /app

# Copy the requirements file into the container
# This assumes requirements.txt is directly in parent_folder
COPY requirements.txt /app/requirements.txt

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy your entire 'multi_tool_agent' directory into the container's WORKDIR (/app)
# This will result in /app/multi_tool_agent/... inside the container
COPY multi_tool_agent /app/multi_tool_agent

# Set the PYTHONPATH to include your application directory
# This helps Python find your modules when you import them
ENV PYTHONPATH="/app"

# Define the command to run your ADK web interface
#CMD ["bash", "-c", "adk web --port $PORT"]
CMD ["bash", "-c", "adk web . --host 0.0.0.0 --port $PORT"]