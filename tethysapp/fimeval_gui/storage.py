import io

import boto3
from botocore.exceptions import ClientError


class S3Storage:
    def __init__(self, endpoint_url, access_key, secret_key, bucket):
        self._bucket = bucket
        self._client = boto3.client(
            's3',
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    def upload_bytes(self, data: bytes, key: str) -> str:
        self._client.upload_fileobj(io.BytesIO(data), self._bucket, key)
        return key

    def upload_fileobj(self, fileobj, key: str) -> str:
        fileobj.seek(0)
        self._client.upload_fileobj(fileobj, self._bucket, key)
        return key

    def list_prefix(self, prefix: str) -> list[str]:
        paginator = self._client.get_paginator('list_objects_v2')
        keys = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get('Contents', []):
                keys.append(obj['Key'])
        return keys

    def key_exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] in ('404', 'NoSuchKey'):
                return False
            raise

    def download_to_path(self, key: str, dest_path: str) -> None:
        self._client.download_file(self._bucket, key, dest_path)

    def presigned_url(self, key: str, expiry_seconds: int = 3600) -> str:
        return self._client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self._bucket, 'Key': key},
            ExpiresIn=expiry_seconds,
        )
