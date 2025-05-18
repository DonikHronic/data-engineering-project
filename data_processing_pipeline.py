import json
from datetime import datetime
from os import getcwd
from pathlib import Path

import pandas as pd
from kafka import KafkaConsumer, KafkaProducer
from minio import Minio, S3Error
from pandas import DataFrame
from prefect import flow, task
from pyspark.sql import SparkSession
from pyspark.sql.functions import col


@task
def load_data():
    """
    This function loads data from a source.
    It can be a database, a file, or any other data source.
    """
    print("Loading data from INDIA VIX_minute Dataset")
    path_to_data = Path(getcwd()) / "data" / "INDIA VIX_minute.csv"

    dataset = pd.read_csv(path_to_data)
    print("Data loaded successfully")
    return dataset


@task
def ingest_data(df: DataFrame):
    """
    This function ingests the data into a Kafka topic.
    It uses the KafkaProducer to send messages to the topic.
    """
    producer = KafkaProducer(
        bootstrap_servers=["kafka:19092"],
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )

    df = df.head(1000)  # Limit to 1000 records for testing

    for record in df.iterrows():
        print("PUBLISHING")
        producer.send("ingestion-topic", record[1].to_dict())

    producer.send("ingestion-topic", {"finished": True})
    producer.flush()

    return True


@task
def store_data():
    consumer = KafkaConsumer(
        "ingestion-topic",
        bootstrap_servers=["kafka:19092"],
        group_id="1",
        auto_offset_reset="earliest",
        value_deserializer=lambda x: json.loads(x.decode("utf-8")),
    )

    data_records = []
    while True:
        try:
            message = next(consumer)
            consumer.commit()
            if message.value.get("finished"):
                break
            data_records.append(message.value)
        except StopIteration:
            break

    temp_df = pd.DataFrame(data_records)
    temp_file = "/tmp/temp_data.csv"
    temp_df.to_csv(temp_file, index=False)

    client = Minio(
        "minio:9000", access_key="minioadmin", secret_key="minioadmin", secure=False
    )

    bucket_name = "ingestion-bucket"
    object_name = f"ingested-data-at-{datetime.now().isoformat()}.csv"

    try:
        # Check if the bucket already exists
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
        print(f"Bucket '{bucket_name}' is ready")

        # Upload the file to the bucket
        client.fput_object(bucket_name, object_name, temp_file)
        print(
            f"File '{temp_file}' uploaded as '{object_name}' in bucket '{bucket_name}'"
        )
    except S3Error as err:
        print(f"Error occurred: {err}")


    return object_name


@task
def send_to_processing(stored_file: str):
    # Initialize the SparkSession with Hadoop AWS package
    spark = (
        SparkSession.builder.appName("ProcessData")
        .config(
            "spark.jars.packages",
            "org.apache.hadoop:hadoop-aws:3.3.1,com.amazonaws:aws-java-sdk-bundle:1.11.1026",
        )
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.access.key", "minioadmin")
        .config("spark.hadoop.fs.s3a.secret.key", "minioadmin")
        .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000")
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .getOrCreate()
    )

    # Read data from MinIO
    # minio_path = f"s3a://ingestion-bucket/{stored_file}"
    client = Minio(
        "minio:9000", access_key="minioadmin", secret_key="minioadmin", secure=False
    )
    client.fget_object("ingestion-bucket", stored_file, "/tmp/temp_data.csv")

    df = spark.read.csv('/tmp/temp_data.csv', header=True, inferSchema=True)

    # Data Preprocessing steps here
    df = df.withColumn("mid", (col("high") + col("low")) / 2)

    # Write processed data back to MinIO
    processed_data_file = f"processed-data-at-{datetime.now().isoformat()}.parquet"
    processed_minio_path = f"s3a://processed-bucket/{processed_data_file}"
    df.write.parquet(processed_minio_path)

    # Stop the Spark session
    spark.stop()

    return processed_minio_path

@task
def send_processed_to_kafka(processed_minio_path):
    # Initialize Spark session
    spark = (
        SparkSession.builder.appName("ProcessData")
        .config(
            "spark.jars.packages",
            "org.apache.hadoop:hadoop-aws:3.3.1,com.amazonaws:aws-java-sdk-bundle:1.11.1026",
        )
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.access.key", "minioadmin")
        .config("spark.hadoop.fs.s3a.secret.key", "minioadmin")
        .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000")
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .getOrCreate()
    )

    # Read processed data from MinIO
    processed_df = spark.read.parquet(processed_minio_path)
    processed_dict = processed_df.toPandas()

    # Initialize Kafka producer
    producer = KafkaProducer(
        bootstrap_servers=["kafka:19092"],
        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
    )

    # Send each record to Kafka

    for record in processed_dict.iterrows():
        print("PUBLISHING")
        producer.send("processing-topic", record[1].to_dict())
    producer.flush()

@flow
def data_processing_workflow():
    """
    This function orchestrates the data processing workflow.
    It includes data loading, preprocessing, and saving the processed data.
    """

    # Load data from the source
    loaded_data = load_data()
    # Ingest data into Kafka
    ingest_data(loaded_data)
    # Store data from Kafka to MinIO
    stored_data = store_data()

    # Creation of MinIO bucket for processed data
    client = Minio("minio:9000", access_key="minioadmin", secret_key="minioadmin", secure=False)
    if not client.bucket_exists("processed-bucket"):
        client.make_bucket("processed-bucket")
    print("Bucket 'processed-bucket' is ready")

    # Send the stored data to processing
    processed_file = send_to_processing(stored_data)

    # Send the processed data to Kafka
    send_processed_to_kafka(processed_file)


if __name__ == '__main__':
    data_processing_workflow()