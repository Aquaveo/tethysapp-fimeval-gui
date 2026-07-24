import io

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


class S3Storage:
    """Thin boto3 wrapper over a single S3/MinIO bucket.

    Constructed per request from the app's MinIO/S3 custom settings; every method
    operates on the one configured bucket.
    """

    def __init__(self, endpoint_url, access_key, secret_key, bucket,
                 public_endpoint_url=None):
        self._bucket = bucket
        self._client = boto3.client(
            's3',
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        # Presigned URLs are handed to the browser, so the presign client is
        # configured deliberately, independent of the main client:
        #  - SigV4 (signature_version='s3v4'): the default SigV2 folds
        #    Content-Type into the signature, and a browser PUT always sends a
        #    Content-Type, producing SignatureDoesNotMatch (403). SigV4 keeps it
        #    out of the signed headers, so the browser's header is ignored. The
        #    region is required for the SigV4 credential scope (MinIO ignores it).
        #  - endpoint: the browser-facing host when a public endpoint is set
        #    (production, where the browser reaches MinIO at a different address
        #    than the server does), else the same host as the main client (dev).
        self._presign_client = boto3.client(
            's3',
            endpoint_url=(public_endpoint_url or endpoint_url) or None,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name='us-east-1',
            config=Config(signature_version='s3v4'),
        )

    def upload_bytes(self, data: bytes, key: str) -> str:
        """Upload raw ``data`` bytes to ``key``; returns the key."""
        self._client.upload_fileobj(io.BytesIO(data), self._bucket, key)
        return key

    def upload_fileobj(self, fileobj, key: str) -> str:
        """Upload a file-like object to ``key`` (rewinds it first); returns the key."""
        fileobj.seek(0)
        self._client.upload_fileobj(fileobj, self._bucket, key)
        return key

    def list_prefix(self, prefix: str) -> list[str]:
        """Return every object key under ``prefix`` (handles pagination)."""
        paginator = self._client.get_paginator('list_objects_v2')
        keys = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get('Contents', []):
                keys.append(obj['Key'])
        return keys

    def list_prefix_with_sizes(self, prefix: str) -> list[tuple[str, int]]:
        """Return ``(key, size_bytes)`` for every object under ``prefix``
        (handles pagination). Used to confirm uploaded files actually landed."""
        paginator = self._client.get_paginator('list_objects_v2')
        out = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get('Contents', []):
                out.append((obj['Key'], obj['Size']))
        return out

    def key_exists(self, key: str) -> bool:
        """True if ``key`` exists; False on 404/NoSuchKey; re-raises other errors."""
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] in ('404', 'NoSuchKey'):
                return False
            raise

    def download_to_path(self, key: str, dest_path: str) -> None:
        """Download ``key`` to the local ``dest_path``."""
        self._client.download_file(self._bucket, key, dest_path)

    def get_object(self, key: str) -> dict:
        """Return the raw boto3 ``get_object`` response (its ``Body`` is a stream)."""
        return self._client.get_object(Bucket=self._bucket, Key=key)

    def presigned_url(self, key: str, expiry_seconds: int = 3600) -> str:
        """Return a time-limited presigned GET URL for ``key`` (default 1 hour)."""
        return self._presign_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self._bucket, 'Key': key},
            ExpiresIn=expiry_seconds,
        )

    def presigned_put_url(self, key: str, expiry_seconds: int = 3600) -> str:
        """Return a time-limited presigned PUT URL for ``key`` (default 1 hour),
        used by the browser to upload a file directly to storage."""
        return self._presign_client.generate_presigned_url(
            'put_object',
            Params={'Bucket': self._bucket, 'Key': key},
            ExpiresIn=expiry_seconds,
        )
