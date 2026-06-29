"""
This module provides S3 client utilities for the Redshift UNLOAD connector.
It handles listing, reading, and deleting files from S3 buckets where
Redshift UNLOAD exports data.
"""

# Import for AWS S3 interaction
import boto3

# For configuring boto3 client (region and retry settings)
from botocore.config import Config

# Import for type hinting
from typing import List, Iterator, Dict, Any

# Import for Parquet file handling with memory-efficient S3 streaming
import pyarrow.parquet as pq
from pyarrow import fs as pa_fs

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log


class S3Client:
    """
    S3 client for managing files exported by Redshift UNLOAD.
    Handles listing, reading Parquet files, and cleanup operations.
    Uses PyArrow S3FileSystem for memory-efficient streaming reads.
    """

    def __init__(self, configuration: dict):
        """
        Initialize S3 client with configuration parameters.
        Args:
            configuration: Dictionary containing S3 connection parameters
        """
        self.bucket = configuration["s3_bucket"]
        self.region = configuration.get("s3_region")

        # Configure boto3 client with retry settings for reliability
        boto_config = Config(
            region_name=self.region,
            retries={"max_attempts": 3, "mode": "adaptive"},
        )

        aws_access_key = configuration.get("aws_access_key_id")
        aws_secret_key = configuration.get("aws_secret_access_key")

        if aws_access_key and aws_secret_key:
            # Boto3 client for listing and deleting files
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                config=boto_config,
            )

            # PyArrow S3FileSystem for memory-efficient streaming reads
            # This avoids loading entire Parquet files into memory
            self.pa_filesystem = pa_fs.S3FileSystem(
                access_key=aws_access_key,
                secret_key=aws_secret_key,
                region=self.region,
            )

            log.info(f"S3 client initialized for bucket: {self.bucket}")
        else:
            raise ValueError(
                "AWS access key ID and secret access key must be provided in the configuration."
            )

    def list_files(self, prefix: str) -> List[str]:
        """
        List all parquet files in the S3 bucket with the given prefix.
        You can modify this method to filter files based on your requirements.
        Args:
            prefix: S3 key prefix to filter files
        Returns:
            List of S3 keys matching the prefix
        """
        files = []
        paginator = self.s3_client.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            if "Contents" in page:
                for obj in page["Contents"]:
                    key = obj["Key"]
                    # Filter to only include Parquet files
                    if key.endswith(".parquet"):
                        files.append(key)

        log.info(f"Found {len(files)} Parquet file(s) at prefix: {prefix}")
        return files

    def read_parquet_file(self, key: str) -> Iterator[Dict[str, Any]]:
        """
        Read a Parquet file from S3 and yield records using memory-efficient streaming.
        Uses PyArrow S3FileSystem to stream data row-group by row-group without loading
        the entire file into memory.
        Args:
            key: S3 key of the Parquet file
        Yields:
            Dictionary records one at a time
        """
        # Construct the S3 path for PyArrow (without s3:// prefix)
        s3_path = f"{self.bucket}/{key}"
        log.info(f"Reading Parquet file with streaming: s3://{s3_path}")

        # Open the Parquet file using PyArrow S3FileSystem
        # This streams data directly from S3 without loading entire file into memory
        parquet_file = pq.ParquetFile(s3_path, filesystem=self.pa_filesystem)

        # Process row groups one at a time for memory efficiency
        num_row_groups = parquet_file.metadata.num_row_groups
        log.info(f"Parquet file has {num_row_groups} row group(s)")

        for row_group_idx in range(num_row_groups):
            # Read only one row group at a time to minimize memory usage
            table = parquet_file.read_row_group(row_group_idx)
            records = table.to_pylist()

            # Yield records one at a time
            yield from records

            # Clear reference to allow garbage collection
            del table, records

    def delete_files(self, keys: List[str]) -> int:
        """
        Delete multiple files from S3.
        Args:
            keys: List of S3 keys to delete
        Returns:
            Number of files deleted
        """
        if not keys:
            return 0

        deleted_count = 0
        # S3 delete_objects allows max 1000 keys per request
        batch_size = 1000

        for i in range(0, len(keys), batch_size):
            batch = keys[i : i + batch_size]
            delete_objects = {"Objects": [{"Key": key} for key in batch]}

            response = self.s3_client.delete_objects(Bucket=self.bucket, Delete=delete_objects)

            if "Deleted" in response:
                deleted_count += len(response["Deleted"])

            if "Errors" in response:
                for error in response["Errors"]:
                    log.warning(f"Failed to delete {error['Key']}: {error['Message']}")

        log.info(f"Deleted {deleted_count} file(s) from S3")
        return deleted_count

    def delete_prefix(self, prefix: str) -> int:
        """
        Delete all files under a given prefix.
        This deletes ALL files (parquet, manifest, and any other files) to ensure complete cleanup.
        Args:
            prefix: S3 key prefix to delete
        Returns:
            Number of files deleted
        """
        paginator = self.s3_client.get_paginator("list_objects_v2")
        files = []

        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            if "Contents" in page:
                for obj in page["Contents"]:
                    # Collect all files under the prefix for complete cleanup
                    files.append(obj["Key"])

        if files:
            return self.delete_files(files)
        return 0
