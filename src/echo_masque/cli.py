"""Command-line entry point for local development."""

import argparse
import json
from collections.abc import Sequence

from echo_masque.config import get_settings


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(prog="echo-masque")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("info", help="Print the resolved non-secret configuration.")

    serve = subparsers.add_parser("serve", help="Run the FastAPI development server.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Execute an Echo Masque command."""

    args = build_parser().parse_args(argv)

    if args.command == "info":
        settings = get_settings()
        print(
            json.dumps(
                {
                    "name": settings.app_name,
                    "version": settings.app_version,
                    "environment": settings.environment,
                    "debug": settings.debug,
                    "log_level": settings.log_level,
                },
                indent=2,
            )
        )
        return 0

    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "echo_masque.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
