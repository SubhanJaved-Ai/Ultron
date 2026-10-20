"""Entry point to run the Jarvis 2.0 API and Hologram server directly."""

from __future__ import annotations

import uvicorn

from openjarvis.server.app import create_app


def main() -> None:
    app = create_app()
    print("=" * 65)
    print("  JARVIS 2.0 — Hologram Web & API Server is Starting")
    print("  Open 3D Hologram Interface: http://localhost:8000/hologram")
    print("  Interactive API Swagger:    http://localhost:8000/docs")
    print("=" * 65)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()
