"""
aws_utils.py

Provides utility functions to interact with AWS S3, securely fetching CSV data.
"""

import boto3
import pandas as pd
import io

def fetch_s3_csv(aws_key, aws_secret, bucket_name, file_key):
    """
    Connects to AWS S3, fetches a specific file given credentials,
    and returns a pandas DataFrame.
    
    Args:
        aws_key (str): AWS Access Key ID
        aws_secret (str): AWS Secret Access Key
        bucket_name (str): The name of the S3 bucket
        file_key (str): The object key (path) to the CSV file
        
    Returns:
        pd.DataFrame: DataFrame containing the CSV data.
    """
    if not all([aws_key, aws_secret, bucket_name, file_key]):
        raise ValueError("Missing one or more required AWS credentials/parameters.")

    s3_client = boto3.client(
        's3',
        aws_access_key_id=aws_key,
        aws_secret_access_key=aws_secret
    )

    s3_object = s3_client.get_object(Bucket=bucket_name, Key=file_key)
    csv_data = s3_object['Body'].read()
    
    df = pd.read_csv(io.BytesIO(csv_data))
    return df
