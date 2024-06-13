# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed dependencies specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

ARG TLG_TOKEN

# Define environment variable
ENV TLG_TOKEN=$TLG_TOKEN

# Run app when the container launches
CMD ["python", "pubBot.py"]