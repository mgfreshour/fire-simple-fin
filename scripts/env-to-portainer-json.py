#!/usr/bin/env python3
"""Read a .env file and print a Portainer-style JSON array: [{"name": "K", "value": "V"}, ...].
Skips empty lines and # comments. Handles values with = and optional quotes."""
import json
import sys
from pathlib import Path


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".env")
    if not path.is_file():
        print("[]")
        return
    env: list[dict[str, str]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1].replace('\\"', '"')
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1].replace("\\'", "'")
        env.append({"name": key, "value": value})
    print(json.dumps(env))


if __name__ == "__main__":
    main()
