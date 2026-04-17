#!/usr/bin/env python3
"""Entry point – start the TN Election Watch server."""

import argparse
import uvicorn

from config import DATA_DIR


def main():
    parser = argparse.ArgumentParser(description="RTR's TN Election Watch 2026")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes")
    args = parser.parse_args()

    DATA_DIR.mkdir(exist_ok=True)

    # Ensure DB is initialised on first run
    from app.database import init_db
    init_db()

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
