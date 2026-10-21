
#!/usr/bin/env python3
"""Download books and stage them in a public AWS S3 bucket."""

import json
import logging
import os
import sys
import time
from urllib.parse import urlparse

import boto3
import requests
from botocore.exceptions import ClientError

# Set up the logger.
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# Create one shared S3 client.
s3 = boto3.client("s3", region_name="us-east-1")


def parse_args():
    """Read the book list, index path, and bucket name."""
    if len(sys.argv) < 4:
        log.error(
            "Usage: python stage_books.py "
            "<book_urls.txt> <index.html> <bucket>"
        )
        sys.exit(1)

    return sys.argv[1], sys.argv[2], sys.argv[3]


def download_books(list_file, dest_dir):
    """Download books and return their local file paths."""
    os.makedirs(dest_dir, exist_ok=True)
    file_paths = []

    try:
        with open(list_file, "r") as f:
            urls = [line.strip() for line in f if line.strip()]
    except OSError as e:
        log.error(f"Error reading book list: {e}")
        return file_paths

    for url in urls:
        filename = os.path.basename(urlparse(url).path)
        path = os.path.join(dest_dir, filename)

        if os.path.exists(path):
            log.info(f"Skipping existing file: {path}")
            file_paths.append(path)
            continue

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            with open(path, "wb") as f:
                f.write(response.content)

            file_paths.append(path)
            log.info(f"Downloaded: {path}")

        except requests.RequestException as e:
            log.error(f"Error downloading {url}: {e}")
        except OSError as e:
            log.error(f"Error saving {path}: {e}")

        time.sleep(1)

    return file_paths


def create_bucket(bucket):
    """Create the bucket if it does not already exist."""
    try:
        s3.head_bucket(Bucket=bucket)
        log.info(f"Bucket already exists: {bucket}")
        return True

    except ClientError as e:
        code = e.response["Error"]["Code"]

        if code not in ("404", "NoSuchBucket", "NotFound"):
            log.error(f"Cannot access bucket {bucket}: {e}")
            return False

    try:
        # us-east-1 does not require LocationConstraint.
        s3.create_bucket(Bucket=bucket)
        log.info(f"Created bucket: {bucket}")
        return True

    except ClientError as e:
        log.error(f"Error creating bucket {bucket}: {e}")
        return False


def make_public(bucket):
    """Allow public read access to objects in the bucket."""
    try:
        s3.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": False,
                "IgnorePublicAcls": False,
                "BlockPublicPolicy": False,
                "RestrictPublicBuckets": False,
            },
        )

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{bucket}/*",
                }
            ],
        }

        s3.put_bucket_policy(
            Bucket=bucket,
            Policy=json.dumps(policy),
        )

        log.info(f"Bucket is public: {bucket}")
        return True

    except ClientError as e:
        log.error(f"Error making bucket public: {e}")
        return False


def upload_files(bucket, file_paths):
    """Upload book files and return the successful upload count."""
    count = 0

    for path in file_paths:
        key = os.path.basename(path)

        try:
            with open(path, "rb") as f:
                s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=f,
                    ContentType="text/plain; charset=utf-8",
                )

            count += 1
            log.info(f"Uploaded: {key}")

        except (ClientError, OSError) as e:
            log.error(f"Error uploading {path}: {e}")

    return count


def upload_index(bucket, index_path):
    """Upload the HTML index page to the bucket."""
    try:
        with open(index_path, "rb") as f:
            s3.put_object(
                Bucket=bucket,
                Key="index.html",
                Body=f,
                ContentType="text/html",
            )

        log.info("Uploaded index.html")
        return True

    except FileNotFoundError:
        log.error(f"Index file not found: {index_path}")
        return False

    except (ClientError, OSError) as e:
        log.error(f"Error uploading index: {e}")
        return False


def main():
    """Run the complete book staging process."""
    list_file, index_path, bucket = parse_args()

    file_paths = download_books(list_file, "books")

    if not file_paths:
        log.error("No books downloaded.")
        sys.exit(1)

    if not create_bucket(bucket):
        log.error("Could not create bucket.")
        sys.exit(1)

    if not make_public(bucket):
        log.error("Could not make bucket public.")
        sys.exit(1)

    count = upload_files(bucket, file_paths)
    index_success = upload_index(bucket, index_path)

    url = f"https://{bucket}.s3.amazonaws.com/index.html"

    if count == len(file_paths) and index_success:
        log.info("All files uploaded successfully!")
        log.info(f"Public URL: {url}")
    else:
        log.error("Some files failed to upload.")
        log.info(f"Index URL (if uploaded): {url}")
        sys.exit(1)


if __name__ == "__main__":
    main()
