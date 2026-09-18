import argparse
import os
import sys

import uvicorn


VERSION = "0.2.1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ge360-analitica",
        description="GE360 Analitica - dashboard analytics locale",
    )
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Avvia il servizio GE360")
    serve.add_argument("--host", default=os.getenv("GE360_HOST", "127.0.0.1"))
    serve.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("GE360_PORT", "8788")),
    )

    sub.add_parser("version", help="Mostra la versione")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "version":
        print(VERSION)
        return 0

    if args.command in (None, "serve"):
        host = getattr(args, "host", os.getenv("GE360_HOST", "127.0.0.1"))
        port = getattr(args, "port", int(os.getenv("GE360_PORT", "8788")))

        from app.main import app

        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level=os.getenv("GE360_LOG_LEVEL", "info"),
            proxy_headers=False,
            server_header=False,
        )
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
