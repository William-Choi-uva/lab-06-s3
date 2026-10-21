
#!/bin/bash
set -euo pipefail

# Check that all three arguments were provided.
if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <book_url> <bucket_name> <expiration_seconds>"
    exit 1
fi

# Store command-line arguments.
BOOK_URL="$1"
BUCKET="$2"
EXPIRATION="$3"

# Get the filename from the URL.
FILENAME="${BOOK_URL##*/}"

# Create the books directory if needed.
mkdir -p "books"

# Download the book.
echo "Downloading $FILENAME..."
curl -fL --retry 3 "$BOOK_URL" -o "books/$FILENAME"

# Create the private bucket if it does not exist.
if aws s3 ls "s3://$BUCKET" > /dev/null 2>&1; then
    echo "Bucket already exists: $BUCKET"
else
    echo "Creating private bucket: $BUCKET"
    aws s3 mb "s3://$BUCKET" --region us-east-1
fi

# Upload the book without enabling public access.
echo "Uploading $FILENAME..."
aws s3 cp "books/$FILENAME" "s3://$BUCKET/$FILENAME" \
    --content-type "text/plain; charset=utf-8"

# Generate a temporary presigned URL.
echo "Presigned URL (expires in $EXPIRATION seconds):"
aws s3 presign "s3://$BUCKET/$FILENAME" \
    --expires-in "$EXPIRATION" \
    --region us-east-1
