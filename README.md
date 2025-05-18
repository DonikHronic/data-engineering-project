# Data Engineering Project

# Data Engineering Project

A comprehensive data engineering platform that implements a real-time data processing pipeline with visualization
capabilities.

## Overview

This project demonstrates modern data engineering practices with a containerized architecture for streaming data
ingestion, processing, storage, and visualization.

## Architecture Components

- **Kafka**: Message broker for real-time data streaming
- **Prefect**: Workflow orchestration engine
- **Spark**: Distributed data processing framework
- **MinIO**: S3-compatible object storage
- **FastAPI**: Web application for serving data visualizations

## Prerequisites

- Docker and Docker Compose installed on your system
- Git for cloning the repository

## Getting Started

1. Clone the repository
2. Navigate to the project directory
3. Start all services with Docker Compose:
    ```bash
    docker-compose up -d
    ```

## Accessing Services

- **Data Visualization Dashboard**: http://localhost:8888
- **Prefect Dashboard**: http://localhost:4200
- **Kafka UI**: http://localhost:8000/kafka-ui
- **Spark Master UI**: http://localhost:8080
- **MinIO Console**: http://localhost:9001 (login: minioadmin/minioadmin)

## Using the API

The web service exposes the following endpoints:

- `/`: Main visualization dashboard with real-time charts
- `/data`: Raw data in JSON format
- `/run-processing`: Trigger data processing workflow

### Trigger Data Processing

To manually trigger the data processing pipeline:

```bash
curl -X GET --location "http://localhost:8888/run-processing"
```

### Development
The project structure follows best practices for Python applications:

- FastAPI web application with auto-refreshing visualizations
- Plotly for interactive charts
- Containerized environment for consistent deployment