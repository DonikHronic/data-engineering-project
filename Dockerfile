# Use Python 3.13 as base image
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY ./requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt


# Install OpenJDK
RUN apt-get update && apt-get install -y openjdk-17-jre wget

# Copy application code
COPY . .

# Create templates directory if it doesn't exist
RUN mkdir -p templates

# Expose port for the application
EXPOSE 8888

# Command to run the application
CMD ["uvicorn", "main:web_app", "--host", "0.0.0.0", "--port", "8888"]