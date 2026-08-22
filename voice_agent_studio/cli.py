from __future__ import annotations

import argparse

from .security import generate_master_key


def main() -> None:
    parser = argparse.ArgumentParser(prog="voice-agent-studio")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("generate-key", help="Generate a Fernet master key")
    args = parser.parse_args()
    if args.command == "generate-key":
        print(generate_master_key())


if __name__ == "__main__":
    main()
