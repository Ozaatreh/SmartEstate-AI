"""Opt-in real-API smoke test for the AI gateway (it spends a few tokens — run it deliberately).

    python -m app.ai.smoke

Requires AI_ENABLED=true and ANTHROPIC_API_KEY in .env. Runs, through the gateway only:
1. the Models API health check for every configured model (no tokens), then
2. one tiny ``system_check`` request (a few dozen tokens on the configured default model).
Prints outcomes and usage metadata only — never the key, never the prompt.
"""

from __future__ import annotations

import sys

import app.db.models  # noqa: F401  (registers every table, so usage rows can be written outside the API process)
from app.ai.errors import AIError
from app.ai.gateway import AIGateway
from app.core.config import get_settings


def main() -> int:
    gateway = AIGateway(get_settings())
    if not gateway.config.enabled:
        print(f"AI smoke test NOT run: {gateway.config.reason}")
        return 2
    try:
        checks = gateway.check_health()
        for c in checks:
            print(f"models.retrieve {c.model}: {'ok' if c.ok else c.error_category}")
        result = gateway.generate_text(
            "system_check",
            system="You are a connectivity check. Reply with exactly: OK",
            messages=[{"role": "user", "content": "Connectivity check."}],
            max_tokens=256,
        )
    except AIError as exc:
        print(f"AI smoke test FAILED: {exc.category} ({exc.code})")
        return 1
    u = result.usage
    print(
        f"messages.create: ok · model {u.model} · tokens in/out {u.input_tokens}/{u.output_tokens} · "
        f"est. ${u.estimated_cost_usd} · {u.duration_ms} ms · reply {result.text.strip()[:20]!r}"
    )
    print(f"Availability: {gateway.availability().state}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
