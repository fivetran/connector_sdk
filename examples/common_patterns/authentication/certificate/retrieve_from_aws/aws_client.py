"""
AWS S3 Client for retrieving objects from S3 buckets using AWS credentials.
You can use this client to fetch certificates stored in S3, which can then be used for authentication in your connector.
"""

# Import required for AWS S3 operations
import boto3

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log


class S3Client:
    def __init__(self, aws_access_key_id, aws_secret_access_key, region):
        """
        Initialize the S3 client with AWS credentials
        """
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.region = region
        self.endpoint = f"https://s3.{region}.amazonaws.com"
        self.namespace = "http://s3.amazonaws.com/doc/2006-03-01/"

        self.session = boto3.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region,
        )
        self.credentials = self.session.get_credentials()

    def get_object(self, bucket_name, object_key):
        """
        Retrieve an object from S3 using boto3
        """
        try:
            s3_client = self.session.client("s3")
            response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
            return response["Body"].read()
        except Exception as exception:
            raise exception

    def probe(self, bucket_name):
        """
        Probe the S3 bucket to check if it is accessible with the provided credentials
        """
        try:
            log.info(f"Testing S3 connection to bucket: {bucket_name}")
            s3_client = self.session.client("s3")
            # Attempt to list only one object in the bucket to verify connectivity and read permissions
            s3_client.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
            log.info("S3 connection test successful")
        except Exception as exception:
            raise ConnectionError(f"Failed to access S3 bucket: {exception}")
