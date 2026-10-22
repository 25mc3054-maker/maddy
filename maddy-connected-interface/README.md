# MADDY-connected ALEXZA interface

This is the supplied single-file HTML prototype adapted to connect its assistant chat to the existing MADDY FastAPI API.

## What is connected
- Backend health check: `GET http://127.0.0.1:8000/health`
- Chat: `POST http://127.0.0.1:8000/api/chat`
- Reuses a browser-stored `conversation_id`
- Keeps the latest 40 chat bubbles in browser localStorage so the UI survives refreshes
- Shows a connection status and a readable error when the backend is unreachable

## Run it locally

1. Start the MADDY MCP server in its own terminal using your project's existing instructions.
2. Start FastAPI from `D:\My Projects\MADDY\maddy-backend` in another terminal (activate your venv first), using your normal command, e.g.:
   `uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
3. In `maddy-backend/app/main.py`, add these origins to the existing `allow_origins` list if they are not already present:
   - `http://localhost:5500`
   - `http://127.0.0.1:5500`
4. Open a terminal in this folder and run:
   `python -m http.server 5500`
5. Visit `http://localhost:5500`.

Do not open `index.html` directly as a `file://` URL: browsers can block API requests from that origin.

## Important current limitations
This original UI is plain HTML/CSS/JavaScript, not a Next.js app. The assistant chat is connected to MADDY's API; the smart-home devices, energy readings, medicine reminders, travel suggestions, and activity cards are still demo/simulated data. They do not control real devices or query live providers. Do not rely on the demo security or medicine features for real-world safety.

The browser stores the chat display locally, but actual AI context persistence across backend restarts depends on the backend `memory_service.py` being changed to persistent storage. We still need to inspect `app/database/db.py` before making that change safely.

## Configuration
By default the API base URL is `http://127.0.0.1:8000`. To override it, set `window.MADDY_API_URL` before the integration script runs.
