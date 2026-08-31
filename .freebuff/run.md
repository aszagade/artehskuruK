# KURUKSHETRA Command Center — Preview Run Doc

## How to Reproduce Artifacts

No build step required. The FastAPI backend is pure Python.

1. Ensure `.venv` exists with dependencies installed:
   ```
   .venv/Scripts/python.exe -c "import uvicorn, fastapi; print('ok')"
   ```
2. If missing, install from `requirements.txt`:
   ```
   .venv/Scripts/pip.exe install -r requirements.txt
   ```

## How to Run the Server

```powershell
.venv/Scripts/python.exe -m uvicorn command_center.backend.main:app --host 127.0.0.1 --port 8000
```

- The Swagger UI is available at `http://127.0.0.1:8000/docs`
- The health endpoint is at `http://127.0.0.1:8000/api/health`

## Notes

- Port 8000 is the default. If occupied, try 8001, 8002, etc.
- The server runs in open mode by default (no auth required).
- To enable auth, set env vars: `KURUKSHETRA_AUTH_REQUIRED=1`, `KURUKSHETRA_API_KEYS=key1,key2`
