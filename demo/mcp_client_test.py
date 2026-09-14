"""Real MCP client, not a mock: connects to Callismatic's live MCP server over
Streamable HTTP, does a genuine protocol handshake, lists the real tools, and
calls triage_message with a real voicemail transcript -- the same proof
pattern this project already uses for CALL-E (demo/live_callback_test.py):
prove the real transport, not just the underlying business logic.

Usage:
    python -m callismatic.mcp_server &      # start the server (or point --url elsewhere)
    python demo/mcp_client_test.py [--url http://127.0.0.1:8001/]
"""

from __future__ import annotations

import argparse
import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def run(url: str) -> None:
    async with streamable_http_client(url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            init_result = await session.initialize()
            print(f"Connected. Negotiated MCP protocol version: {init_result.protocol_version}")
            print(f"Server: {init_result.server_info.name} v{init_result.server_info.version}")

            tools = await session.list_tools()
            print(f"\n{len(tools.tools)} tool(s) available:")
            for t in tools.tools:
                print(f"  - {t.name}: {(t.description or '').splitlines()[0]}")

            print("\nCalling triage_message with a real scam transcript...")
            result = await session.call_tool(
                "triage_message",
                {
                    "text": (
                        "This is an urgent automated notice from the Federal Fraud Prevention "
                        "Department. Your account will be suspended within 24 hours unless you "
                        "verify your information. Purchase a $500 Google Play gift card and call "
                        "back with the code."
                    ),
                    "sender": "+15550001111",
                },
            )
            payload = json.loads(result.content[0].text) if result.content else {}
            print(json.dumps(payload, indent=2))
            # Live LLM call -- assert only the category, not every field, since a
            # real model's exact structured output can vary run to run (the same
            # tolerance this project's other real-call tests already give Bedrock/
            # Nova and Groq elsewhere).
            assert payload.get("category") == "scam", f"expected scam, got {payload.get('category')}"
            print(f"\nReal triage_message call over Streamable HTTP: category={payload.get('category')} -- verified.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8001/")
    args = parser.parse_args()
    asyncio.run(run(args.url))
