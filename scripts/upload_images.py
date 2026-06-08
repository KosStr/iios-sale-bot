"""Upload product images from a local folder to Cloudflare R2.

Usage:
    python -m scripts.upload_images [folder]

`folder` defaults to ./images. Each file is uploaded with its filename as the
object key, so name them after product IDs, e.g. `iphone-15-pro.jpg`.

Requires these environment variables (see .env):
    R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
"""

from __future__ import annotations

import mimetypes
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_REQUIRED = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"]


def main() -> int:
    missing = [name for name in _REQUIRED if not os.getenv(name)]
    if missing:
        print(f"Missing env vars: {', '.join(missing)}")
        return 1

    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "images")
    if not folder.is_dir():
        print(f"Folder not found: {folder.resolve()}")
        return 1

    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )
    bucket = os.getenv("R2_BUCKET")

    uploaded = 0
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as fh:
            client.put_object(
                Bucket=bucket, Key=path.name, Body=fh, ContentType=content_type
            )
        print(f"  ✓ {path.name}  ({content_type})")
        uploaded += 1

    print(f"\nUploaded {uploaded} file(s) to bucket '{bucket}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
