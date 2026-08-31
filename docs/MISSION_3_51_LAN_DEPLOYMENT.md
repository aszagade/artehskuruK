# Mission 3.51 — SANJAYA LAN Sharable UI + Deployment Foundation

## A. Files Changed

| File | Change |
|------|--------|
| `command_center/frontend/index.html` | Complete rewrite: same-origin API, login/logout, user display, feedback buttons, file upload, citations, knowledge source indicators |
| `command_center/backend/main.py` | Added `/api/config` endpoint, configurable `SANJAYA_HOST`/`SANJAYA_PORT` |
| `kurukshetra/security/entra_provider.py` | Added `client_secret` field (from previous mission), documented redirect URI configurability |
| `tests/test_lan_ui.py` | **NEW** — 15 tests for LAN deployment, UI, security, upload, feedback |

## B. UI Changes

The Command Center has been upgraded from a developer dashboard to a colleague-usable interface:

| Feature | Before | After |
|---------|--------|-------|
| API URL | `http://localhost:8000/api` hardcoded | Same-origin (`window.location.origin + '/api'`) |
| User identity | Not shown | Header shows name, team, auth status |
| Login/Logout | Not present | Login/Logout buttons in header |
| Answer format | Raw retrieval results | Natural-language answers with confidence |
| Citations | Not shown | Source citations with document IDs and snippets |
| Knowledge source | Not shown | Color-coded: organization/uploaded/conversation/model |
| Abstention | Not clear | Explicit abstention message with reason |
| Feedback | Not present | 👍/👎 buttons on every answer |
| File upload | Not present | Drag-and-drop upload zone with progress |
| Upload formats | Unknown | PDF, DOCX, DOC, XLSX, XLS, CSV, TXT, MD, PPTX, HTML, JSON, XML |

## C. LAN Changes

| Component | Change |
|-----------|--------|
| Backend host | `0.0.0.0` (was already LAN-ready) |
| Backend port | Configurable via `SANJAYA_PORT` (default: 8000) |
| CORS | `*` (already allows LAN access) |
| Frontend API | Same-origin (works on any hostname/IP) |

## D. Authentication Changes

| Component | Change |
|-----------|--------|
| Redirect URI | Configurable via `ENTRA_REDIRECT_URI` (default: `http://localhost:8000/auth/callback`) |
| Session token | Stored in `localStorage`, works across origins |
| Auth flow | Same — Authorization Code + PKCE + state + nonce |

## E. Security Implications

| Property | Status |
|----------|--------|
| User A cannot see User B's memory | ✅ VERIFIED |
| VisibilityFilter enforced | ✅ VERIFIED |
| GX10 receives only authorized evidence | ✅ VERIFIED |
| Feedback is user-scoped | ✅ VERIFIED |
| Upload goes through KnowledgeFabric | ✅ VERIFIED |
| Session invalidation works | ✅ VERIFIED |
| Authentication required in production | ✅ PRESERVED |

## F. Upload Behavior

Upload flow (unchanged):
```
User drops file → POST /api/knowledge/upload → KnowledgeFabric.ingest_file()
→ TextExtractor → Chunks → Embeddings → Graph → BM25 → Searchable
```

Supported formats: PDF, DOCX, DOC, XLSX, XLS, CSV, TXT, MD, PPTX, HTML, JSON, XML

UI feedback:
- "⏳ Processing filename..." → "✅ Indexed: DOC-XXXX (N chunks)" or "❌ Failed: reason"

## G. Exact Startup Command

```bash
python -m uvicorn command_center.backend.main:app --host 0.0.0.0 --port 8000
```

Or with environment variables:
```bash
set SANJAYA_HOST=0.0.0.0
set SANJAYA_PORT=8000
python -m uvicorn command_center.backend.main:app
```

## H. Exact LAN URL Format

From another computer on the same LAN, open:

```
http://172.27.211.88:8000
```

Or use the machine name:
```
http://<COMPUTER-NAME>:8000
```

## I. Required Windows Firewall Action

Run this command in an elevated Command Prompt:

```cmd
netsh advfirewall firewall add rule name="SANJAYA LAN" dir=in action=allow protocol=TCP localport=8000
```

To remove later:
```cmd
netsh advfirewall firewall delete rule name="SANJAYA LAN"
```

## J. Required Entra Portal Change

If testing authentication from LAN, add a second Redirect URI:

1. Go to Entra portal → App registrations → Kurukshetra SANJAYA → Authentication
2. Add platform: **Web**
3. Add redirect URI: `http://172.27.211.88:8000/auth/callback`
4. Click **Configure**

Set environment variable:
```bash
set ENTRA_REDIRECT_URI=http://172.27.211.88:8000/auth/callback
```

**Note:** HTTP is only appropriate for localhost and internal LAN testing. Production requires HTTPS.

## K. Environment Variables

```bash
# Required
ENTRA_TENANT_ID=<your-tenant-id>
ENTRA_CLIENT_ID=<your-client-id>
ENTRA_CLIENT_SECRET=<your-client-secret>
KURUKSHETRA_SESSION_SECRET=<random-64-char-string>

# LAN deployment
SANJAYA_HOST=0.0.0.0
SANJAYA_PORT=8000
SANJAYA_PUBLIC_URL=http://172.27.211.88:8000
ENTRA_REDIRECT_URI=http://172.27.211.88:8000/auth/callback

# Optional
KURUKSHETRA_CORS_ORIGINS=*
```

## L. Tests

| Suite | Count | Status |
|-------|-------|--------|
| test_lan_ui (NEW) | 15 | ✅ PASS |
| test_entra_auth_flow | 17 | ✅ PASS |
| test_entra_security | 15 | ✅ PASS |
| test_entity_quality | 18 | ✅ PASS |
| test_fabric_wiring | 8 | ✅ PASS |
| test_gx10_integration | 22 | ✅ PASS |
| test_identity_boundary | 32 | ✅ PASS |
| test_upload_ingestion | 20 | ✅ PASS (1 skipped) |
| **Total** | **147** | **✅ ALL PASS** |

## M. Known Limitations

1. **No HTTPS** — LAN deployment uses HTTP. Production requires a reverse proxy with TLS.
2. **No persistent sessions** — Sessions are stored in memory. Server restart loses all sessions.
3. **No user registration** — Users must be pre-configured in Entra ID.
4. **Upload visibility** — All uploaded documents are currently visible to all authenticated users. User-scoped uploads require additional work.
5. **Single-process DuckDB** — DuckDB does not support concurrent writes from multiple processes. Suitable for single-server deployment only.

## N. What You Must Manually Do

1. **Set environment variables** (see Section K)
2. **Add firewall rule** (see Section I)
3. **Add LAN Redirect URI in Entra** (see Section J) — only if testing auth from LAN
4. **Start the server** (see Section G)
5. **Open browser** from another computer: `http://172.27.211.88:8000`

## Status

**READY FOR LAN TESTING.** Not committed — awaiting approval.
