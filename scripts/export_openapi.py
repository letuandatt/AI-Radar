"""Export the versioned public contract without loading runtime settings/services."""

import json
from pathlib import Path

from app.api.config import WebConfig
from app.api.factory import create_app


def main() -> None:
    """Write a reproducible schema for Orval, without a running API or providers."""
    schema = create_app(config=WebConfig(_env_file=None)).openapi()
    target = Path(__file__).resolve().parents[1] / "web" / "openapi.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"DONE: exported OpenAPI to {target}")


if __name__ == "__main__":
    main()
