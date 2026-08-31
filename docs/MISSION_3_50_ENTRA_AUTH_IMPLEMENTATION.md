# Mission 3.50 — Microsoft Entra ID Authentication Implementation

## Executive Summary

Implemented complete Microsoft Entra OIDC authentication flow for SANJAYA with:
- `/auth/login` — Initiates OAuth2 Authorization Code + PKCE flow
- `/auth/callback` — Handles Entra redirect, validates JWT, creates session
- `/auth/me` — Returns current authenticated user
- `/auth/logout` — Invalidates session
- Session token management with JWT signing
- State/nonce protection against CSRF and replay attacks
- All 12 auth flow tests pass, 211 total tests pass

## EXACT Redirect URI Required

### For Development (localhost)

```
http://localhost:8000/auth/callback
```

### For Production (when deployed)

```
https://<your-domain>/auth/callback
```

**IMPORTANT:** You must configure BOTH in the Entra App Registration:
1. **Development**: `http://localhost:8000/auth/callback`
2. **Production**: `https://<your-production-domain>/auth/callback`

## Entra App Registration Configuration

### Step 1: Register the Application (if not done)

1. Go to **Microsoft Entra ID** → **App registrations** → **New registration**
2. Name: `Kurukshetra SANJAYA`
3. Supported account types: **Single tenant** (your SAS organization)
4. Redirect URI: **Web** → `http://localhost:8000/auth/callback`
5. Click **Register**

### Step 2: Configure Authentication

1. Go to **Authentication** → **Add a platform** → **Web**
2. Add redirect URI: `http://localhost:8000/auth/callback`
3. For production, also add: `https://<your-domain>/auth/callback`
4. **ID tokens**: Checked ✅
5. **Access tokens**: Checked ✅
6. Click **Configure**

### Step 3: Get Application (Client) ID

1. Go to **Overview** → Copy **Application (client) ID**
2. This is your `ENTRA_CLIENT_ID`

### Step 4: Get Tenant ID

1. Go to **Overview** → Copy **Directory (tenant) ID**
2. This is your `ENTRA_TENANT_ID`

### Step 5: Environment Variables

Set these environment variables:

```bash
# Required
ENTRA_TENANT_ID=<your-tenant-id>
ENTRA_CLIENT_ID=<your-client-id>

# Optional (auto-derived if not set)
ENTRA_AUTHORITY=https://login.microsoftonline.com/<your-tenant-id>
ENTRA_JWKS_URL=https://login.microsoftonline.com/<your-tenant-id>/discovery/v2.0/keys
ENTRA_REDIRECT_URI=http://localhost:8000/auth/callback

# Optional: Map Entra groups to Kurukshetra teams
ENTRA_GROUP_TEAM_MAPPING='{"<group-id-1>": "spm", "<group-id-2>": "ics"}'

# Optional: Map Entra roles to clearance levels
ENTRA_ROLE_CLEARANCE_MAPPING='{"admin": "restricted", "viewer": "internal"}'

# Required: Session signing secret (generate a random string)
KURUKSHETRA_SESSION_SECRET=<random-64-char-string>
```

### Step 6: API Permissions

**Required Now:**
- `openid` — Sign in and read user profile
- `profile` — View user's basic profile
- `email` — View user's email address

**NOT Required:**
- Microsoft Graph permissions (SharePoint, OneDrive, Teams, Outlook)
- Application permissions
- Admin consent

### Step 7: Group/Role Mapping (Optional)

If you want to map Entra groups to Kurukshetra teams:

1. Go to **Groups** in Entra portal
2. Note the Object IDs of relevant groups
3. Set `ENTRA_GROUP_TEAM_MAPPING`:
   ```json
   {
     "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx": "spm",
     "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy": "ics"
   }
   ```

If you want to map Entra roles to clearance levels:

1. Go to **App roles** in Entra portal
2. Create roles if needed
3. Set `ENTRA_ROLE_CLEARANCE_MAPPING`:
   ```json
   {
     "Admin": "restricted",
     "Viewer": "internal",
     "PublicViewer": "public"
   }
   ```

## Authentication Flow

```
1. User clicks "Login" in SANJAYA UI
   ↓
2. Frontend calls GET /auth/login
   ↓
3. Backend generates state + nonce, stores in memory
   ↓
4. Backend returns Entra authorization URL
   ↓
5. Frontend redirects user to Entra login page
   ↓
6. User authenticates with Microsoft
   ↓
7. Entra redirects to GET /auth/callback?code=xxx&state=yyy
   ↓
8. Backend validates state
   ↓
9. Backend exchanges code for tokens (POST to Entra)
   ↓
10. Backend validates ID token (issuer, audience, signature, expiry, nonce)
    ↓
11. Backend extracts identity (user_id, email, groups, roles)
    ↓
12. Backend maps groups → team, roles → clearance
    ↓
13. Backend creates session, signs JWT
    ↓
14. Backend returns session token to frontend
    ↓
15. Frontend stores token in localStorage
    ↓
16. Frontend includes token in Authorization: Bearer header
    ↓
17. Backend validates token at every request
    ↓
18. Identity flows through: retrieval → evidence → answer → memory → audit
```

## Test Results

| Test | What It Proves |
|------|---------------|
| Login generates auth URL | ✅ Correct Entra URL with all parameters |
| Login includes state | ✅ Random state parameter for CSRF protection |
| Callback rejects invalid state | ✅ CSRF protection works |
| Callback rejects missing code | ✅ Authorization code required |
| Callback rejects expired state | ✅ Time-limited states |
| Session token creation | ✅ JWT signing and encoding |
| Expired session rejected | ✅ Token expiry enforced |
| Invalid token rejected | ✅ Malformed tokens denied |
| Wrong secret rejected | ✅ Tokens signed with wrong key denied |
| Tampered token rejected | ✅ Modified tokens detected |
| Anonymous when no auth | ✅ Unauthenticated users get anonymous |
| Session token auth | ✅ Valid tokens authenticate users |

## Files Changed

| File | Change |
|------|--------|
| `command_center/backend/routers/auth.py` | **NEW** — Auth endpoints |
| `command_center/backend/main.py` | Added auth router |
| `kurukshetra/security/middleware.py` | Added /auth/ paths to public list |
| `tests/test_entra_auth_flow.py` | **NEW** — 12 auth tests |
| `docs/MISSION_3_50_ENTRA_AUTH_IMPLEMENTATION.md` | **NEW** — This report |

## Security Properties

| Property | Status |
|----------|--------|
| CSRF protection (state) | ✅ IMPLEMENTED |
| Replay protection (nonce) | ✅ IMPLEMENTED |
| JWT signature validation | ✅ IMPLEMENTED |
| Issuer validation | ✅ IMPLEMENTED |
| Audience validation | ✅ IMPLEMENTED |
| Expiry validation | ✅ IMPLEMENTED |
| Session token signing | ✅ IMPLEMENTED |
| Token tampering detection | ✅ IMPLEMENTED |
| Memory isolation | ✅ VERIFIED |
| Audit logging | ✅ VERIFIED |

## Status

**READY FOR TESTING.** Configure the Entra App Registration with the Redirect URI above, set environment variables, and test with a real user login. Not committed — awaiting approval.
