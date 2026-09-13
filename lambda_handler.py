"""Lambda entrypoint for the deployed Callismatic app (web.py).

Secrets come from AWS Secrets Manager (secret name in the CALLISMATIC_SECRET_ARN
environment variable, set at function creation -- not itself a secret, just a
pointer), fetched once at cold start and written into os.environ so every existing
module (models.py, tools.py, crm_sheets.py, etc.) keeps reading os.environ exactly
as it already does -- nothing about their code changes for this to work.

The Google service account key can't be a local file path in Lambda's read-only
filesystem outside /tmp, so its JSON content (GOOGLE_SERVICE_ACCOUNT_JSON in the
secret) is written to /tmp/service-account.json at cold start, and
GOOGLE_SERVICE_ACCOUNT_FILE is pointed at that path.
"""

from __future__ import annotations

import json
import os

import boto3
from mangum import Mangum


def _bootstrap_secrets() -> None:
    # /var/task (Lambda's deployment package) is read-only at runtime; only /tmp is
    # writable. See callismatic/paths.py for why this matters -- confirmed by a real
    # deployment failure (a read-only-filesystem error on the first live triage test),
    # not assumed up front.
    os.environ.setdefault("CALLISMATIC_DATA_DIR", "/tmp/callismatic-data")

    secret_arn = os.environ.get("CALLISMATIC_SECRET_ARN")
    if not secret_arn:
        return  # local/dev run -- .env / already-set env vars are used instead

    client = boto3.client("secretsmanager")
    secret = json.loads(client.get_secret_value(SecretId=secret_arn)["SecretString"])

    sa_json = secret.pop("GOOGLE_SERVICE_ACCOUNT_JSON", None)
    if sa_json:
        sa_path = "/tmp/service-account.json"
        with open(sa_path, "w", encoding="utf-8") as f:
            f.write(sa_json)
        os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"] = sa_path

    for key, value in secret.items():
        os.environ[key] = value


_bootstrap_secrets()

from callismatic.web import app  # noqa: E402 -- must come after secrets are in os.environ

handler = Mangum(app)
