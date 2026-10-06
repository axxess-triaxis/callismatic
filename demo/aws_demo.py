"""One-command walkthrough that makes every AWS service Callismatic uses fire, live, and
prints the proof on screen -- built for recording a short demo video, not for production.

  1. Voicemails transcribed locally (AssemblyAI), all at once.
  2. AWS Lambda -- each transcript is sent, concurrently, to the deployed Function URL's public
     /mcp triage_message tool. Inside AWS, each invocation reads its credentials from
     AWS Secrets Manager at cold start, runs the Strands agent on Amazon Bedrock (Nova), and
     logs to Amazon CloudWatch. triage_message decides and reports; it never places a call.
  3. Proof from the AWS side -- if this machine has working AWS credentials, the script reads
     the CloudWatch Logs REPORT lines, the ECR image digest the Lambda runs, Secrets Manager
     metadata (never the value), and Bedrock's own Invocations metric. Without credentials it
     prints the AWS Console links to show the same things on screen instead.

No AWS credentials are needed on this machine for steps 1-2: the Lambda uses its own IAM role.

Usage (from the repo root):
    python demo/aws_demo.py
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from callismatic.triage import SUPPORTED_SUFFIXES, caller_number_from_filename  # noqa: E402
from callismatic.voicemails import transcribe_voicemail  # noqa: E402

FUNCTION_URL = "https://awpfsufk4dofdncv6cgqsaifwy0kvolm.lambda-url.us-east-1.on.aws"
FUNCTION_NAME = "callismatic"
AWS_REGION = "us-east-1"
SECRET_ID = "callismatic/prod"
BEDROCK_MODEL_ID = "amazon.nova-pro-v1:0"
CONSOLE = f"https://{AWS_REGION}.console.aws.amazon.com"


def banner(n: int, title: str) -> None:
    print("\n" + "#" * 72)
    print(f"#  [{n}/3]  {title}")
    print("#" * 72 + "\n")


def transcribe_all(paths: list[Path]) -> dict[Path, str]:
    banner(1, f"Transcribing {len(paths)} voicemails with AssemblyAI (concurrently)")
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=len(paths)) as pool:
        transcripts = dict(zip(paths, pool.map(transcribe_voicemail, paths)))
    for path, text in transcripts.items():
        print(f"{path.name}\n  \"{text[:110]}{'...' if len(text) > 110 else ''}\"\n")
    print(f"(transcribed in {time.monotonic() - started:.1f}s)")
    return transcripts


def triage_on_lambda(text: str, sender: str) -> dict:
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "triage_message", "arguments": {"text": text, "sender": sender}},
    }).encode()
    req = urllib.request.Request(
        f"{FUNCTION_URL}/mcp", data=body, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read())
    return json.loads(payload["result"]["content"][0]["text"])


def triage_all(transcripts: dict[Path, str]) -> None:
    banner(2, f"AWS Lambda -> Secrets Manager -> Amazon Bedrock: {len(transcripts)} triages in parallel")
    print(f"POST {FUNCTION_URL}/mcp   (tools/call triage_message x{len(transcripts)})\n")
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=len(transcripts)) as pool:
        futures = {
            path: pool.submit(triage_on_lambda, text, caller_number_from_filename(path))
            for path, text in transcripts.items()
        }
        results = {path: f.result() for path, f in futures.items()}
    for path, t in results.items():
        action = (
            "BLOCK" if t.get("block_recommended")
            else "NEEDS YOU" if t.get("needs_decision")
            else "CALLBACK" if t.get("callback_recommended")
            else "FILED"
        )
        print(f"{action:<10} {str(t.get('category')):<10} {path.name}")
        print(f"           {t.get('summary')}")
        if t.get("needs_decision"):
            print(f"           urgency: {t.get('urgency')}")
        if t.get("error"):
            print(f"           error: {t['error']}")
        print()
    print(f"({len(results)} Lambda invocations, each a full Bedrock agent run, in {time.monotonic() - started:.1f}s total)")


def aws_side_proof(since_ms: int, expected: int) -> None:
    banner(3, "Proof from the AWS side: CloudWatch, ECR, Secrets Manager, Bedrock metrics")
    try:
        import boto3

        session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"), region_name=AWS_REGION)
        session.client("sts").get_caller_identity()
    except Exception as exc:  # noqa: BLE001 -- any credential failure means "show the console instead"
        print(f"(No working local AWS credentials: {type(exc).__name__}. Show these in the AWS Console:)\n")
        print(f"CloudWatch Logs:  {CONSOLE}/cloudwatch/home?region={AWS_REGION}#logsV2:log-groups/log-group/$252Faws$252Flambda$252F{FUNCTION_NAME}")
        print(f"Lambda monitor:   {CONSOLE}/lambda/home?region={AWS_REGION}#/functions/{FUNCTION_NAME}?tab=monitoring")
        print(f"ECR image:        {CONSOLE}/ecr/repositories/private/227214487086/{FUNCTION_NAME}?region={AWS_REGION}")
        print(f"Secrets Manager:  {CONSOLE}/secretsmanager/secret?name={SECRET_ID}&region={AWS_REGION}")
        print(f"Bedrock metrics:  {CONSOLE}/cloudwatch/home?region={AWS_REGION}#metricsV2?graph=~()&namespace=~'AWS*2fBedrock")
        return

    logs = session.client("logs")
    events: list[dict] = []
    for _ in range(12):  # CloudWatch ingestion usually takes a few seconds
        events = logs.filter_log_events(
            logGroupName=f"/aws/lambda/{FUNCTION_NAME}", startTime=since_ms - 5000,
            filterPattern='"REPORT RequestId"',
        ).get("events", [])
        if len(events) >= expected:
            break
        time.sleep(5)
    print(f"CloudWatch Logs -- {len(events)} Lambda REPORT line(s) since this run started:")
    for e in events[-expected:]:
        print("  " + e["message"].strip().replace("\t", "  "))

    fn = session.client("lambda").get_function(FunctionName=FUNCTION_NAME)
    resolved = fn["Code"].get("ResolvedImageUri", "")
    print(f"\nLambda image (ECR): {resolved or fn['Code']['ImageUri']}")
    if "@" in resolved:
        repo, digest = resolved.split("/", 1)[1].split("@")
        img = session.client("ecr").describe_images(repositoryName=repo, imageIds=[{"imageDigest": digest}])["imageDetails"][0]
        print(f"  pushed {img['imagePushedAt']}, {img['imageSizeInBytes'] / 1e6:.0f} MB")

    meta = session.client("secretsmanager").describe_secret(SecretId=SECRET_ID)
    print(f"\nSecrets Manager: {meta['Name']} -- last accessed {meta.get('LastAccessedDate')} (value never read here)")

    now = datetime.now(timezone.utc)
    points = session.client("cloudwatch").get_metric_statistics(
        Namespace="AWS/Bedrock", MetricName="Invocations",
        Dimensions=[{"Name": "ModelId", "Value": BEDROCK_MODEL_ID}],
        StartTime=now - timedelta(minutes=30), EndTime=now, Period=300, Statistics=["Sum"],
    )["Datapoints"]
    print(f"\nBedrock: {int(sum(p['Sum'] for p in points))} invocation(s) of {BEDROCK_MODEL_ID} "
          "in the last 30 min (metrics can lag 1-2 min)")


def main() -> None:
    paths = [p for p in sorted(Path("sample_voicemails").iterdir()) if p.suffix.lower() in SUPPORTED_SUFFIXES]
    transcripts = transcribe_all(paths)
    started_ms = int(time.time() * 1000)
    triage_all(transcripts)
    aws_side_proof(started_ms, len(transcripts))
    print("\nDone.")


if __name__ == "__main__":
    main()
