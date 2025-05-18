import json
from contextlib import asynccontextmanager
from datetime import datetime
from threading import Thread, Lock
from typing import List, Dict, Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from kafka import KafkaConsumer

from data_processing_pipeline import data_processing_workflow

data_lock = Lock()
data_records: List[Dict[Any, Any]] = []

def consume_kafka():
    """Consume messages from the Kafka topic in a background thread"""
    try:
        consumer = KafkaConsumer(
            "processing-topic",
            bootstrap_servers=["kafka:19092"],
            auto_offset_reset="earliest",
            value_deserializer=lambda x: json.loads(x.decode("utf-8")),
            group_id="fastapi-consumer",
        )

        for message in consumer:
            data = message.value
            with data_lock:
                data_records.append(data)
                # Keep only the last 100 records to prevent memory issues
                if len(data_records) > 1000000:
                    data_records.pop(0)
    except Exception as e:
        print(f"Kafka consumer error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager to handle startup and shutdown events"""
    # Start the Kafka consumer thread when the application starts
    thread = Thread(target=consume_kafka, daemon=True)
    thread.start()
    yield

web_app = FastAPI(title="Real-time Data Visualization", lifespan=lifespan)

# Set up the templates directory
templates = Jinja2Templates(directory="templates")
web_app.mount("/static", StaticFiles(directory="static"), name="static")


@web_app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Root endpoint displaying charts of the data"""
    with data_lock:
        local_data = data_records.copy()

    if not local_data:
        return """
        <html>
            <head>
                <title>Real-time Data Visualization</title>
                <meta http-equiv="refresh" content="5">
                <style>
                    body { font-family: Arial, sans-serif; margin: 20px; text-align: center; }
                </style>
            </head>
            <body>
                <h2>Waiting for data from Kafka...</h2>
                <p>This page will automatically refresh every 5 seconds.</p>
            </body>
        </html>
        """

    df = pd.DataFrame(local_data)

    # Create multiple charts
    charts_html = ""

    # Chart 1: Mid values if available
    if "mid" in df.columns:
        fig1 = px.line(df, y="mid", title="Mid Value Over Time")
        charts_html += fig1.to_html(full_html=False, include_plotlyjs="cdn")

    # Chart 2: High and Low values if available
    if "high" in df.columns and "low" in df.columns:
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(y=df["high"], mode="lines", name="High"))
        fig2.add_trace(go.Scatter(y=df["low"], mode="lines", name="Low"))
        fig2.update_layout(title="High and Low Values Over Time")
        charts_html += fig2.to_html(full_html=False, include_plotlyjs="cdn")

    # Chart 3: Any other numeric columns
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    if len(numeric_cols) > 0 and set(numeric_cols) != {"mid", "high", "low"}:
        other_cols = [col for col in numeric_cols if col not in ["mid", "high", "low"]]
        if other_cols:
            fig3 = px.line(df, y=other_cols, title="Other Metrics Over Time")
            charts_html += fig3.to_html(full_html=False, include_plotlyjs="cdn")

    # Render complete HTML
    html_content = f"""
    <html>
        <head>
            <title>Real-time Data Visualization</title>
            <meta http-equiv="refresh" content="10">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #2c3e50; text-align: center; }}
                .chart-container {{ margin-bottom: 30px; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                .data-info {{ background-color: #f8f9fa; padding: 10px; border-radius: 5px; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <h1>Real-time Kafka Data Visualization</h1>
            <div class="data-info">
                <p>Displaying data from {len(local_data)} records | Last updated: {datetime.now().isoformat()}</p>
                <p>Data will refresh automatically every 10 seconds</p>
            </div>
            <div class="chart-container">
                {charts_html}
            </div>
        </body>
    </html>
    """
    return html_content


@web_app.get("/data")
async def get_data():
    """API endpoint to get the raw data as JSON"""
    with data_lock:
        return {"data": data_records}

@web_app.get("/run-processing")
async def run_processing():
    """API endpoint to trigger data processing"""
    # Placeholder for processing logic
    data_processing_workflow()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(web_app, host="0.0.0.0", port=8888)
