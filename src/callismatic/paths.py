"""Where the local JSON stores (digest, blocklist, todos, reminders, corrections)
live on disk. Defaults to "outputs" (relative to the CLI's working directory,
unchanged from before this module existed) -- overridable via CALLISMATIC_DATA_DIR
for environments where that default isn't writable, e.g. AWS Lambda, where only
/tmp is writable at runtime (see lambda_handler.py, which sets this to
/tmp/callismatic-data).

Found via a real deployment failure, not a hypothetical: the first live Lambda
test of /api/triage/text got all the way through a real Bedrock call and then
failed on os.mkdir with a read-only filesystem error, because DIGEST_PATH was a
hardcoded relative "outputs/..." path resolving under /var/task, which Lambda
never allows writes to.
"""

from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("CALLISMATIC_DATA_DIR", "outputs"))
