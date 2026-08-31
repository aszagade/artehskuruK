# Mission 3.50 — Client Secret + PKCE Implementation

## A. Exact Files Changed

| File | Change |
|------|--------|
| `kurukshetra/security/entra_provider.py` | Added `client_secret` field to EntraConfig, read from `ENTRA_CLIENT_SECRET` env var |
| `command_center/backend/routers/auth.py` | Added PKCE generation, `client_secret` in token exchange, `code_verifier` in token exchange, validation for missing secret |
| `tests/test_entra_auth_flow.py` | Added 5 new tests: PKCE generation, PKCE storage, missing secret validation, secret not in logs, PKCE in auth URL |

## B. Exact Security Changes

### 1. Client Secret (NEW)

**Line 87 of entra_provider.py:**
```python
client_secret = os.environ.get("ENTRA_CLIENT_SECRET", "")  # NEVER log this
```

**Lines 272-278 of auth.py:**
```python
if not config.client_secret:
    logger.error("ENTRA_CLIENT_SECRET not configured")
    raise HTTPException(
        status_code=500,
        detail="Server configuration error: ENTRA_CLIENT_SECRET not set."
    )
```

**Line 285 of auth.py:**
```python
"client_secret": config.client_secret,
```

### 2. PKCE (NEW — Defense-in-Depth)

**Lines 155-165 of auth.py:**
```python
def _generate_pkce() -> tuple[str, str]:
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(96)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge
```

**Lines 185-186 of auth.py (login endpoint):**
```python
code_verifier, code_challenge = _generate_pkce()
```

**Lines 196-197 of auth.py (authorization URL):**
```python
"code_challenge": code_challenge,
"code_challenge_method": "S256",
```

**Line 286 of auth.py (token exchange):**
```python
"code_verifier": state_data["code_verifier"],
```

### 3. Security Properties Preserved

| Property | Status |
|----------|--------|
| State validation | ✅ PRESERVED (line 224-227) |
| Nonce validation | ✅ PRESERVED (line 299) |
| Issuer validation | ✅ PRESERVED (line 305) |
| Audience validation | ✅ PRESERVED (line 304) |
| Signature/JWKS validation | ✅ PRESERVED (lines 280-293) |
| Expiry validation | ✅ PRESERVED (line 303) |
| Tenant restriction | ✅ PRESERVED (issuer contains tenant_id) |
| Secret never logged | ✅ VERIFIED (test passes) |
| Missing secret fails safely | ✅ VERIFIED (test passes) |

## C. Exact Environment Variables Required

```bash
# REQUIRED — must be set
ENTRA_TENANT_ID=<your-tenant-id>
ENTRA_CLIENT_ID=<your-client-id>
ENTRA_CLIENT_SECRET=<your-client-secret>
KURUKSHETRA_SESSION_SECRET=<random-64-character-string>

# OPTIONAL — auto-derived if not set
# ENTRA_AUTHORITY=https://login.microsoftonline.com/<your-tenant-id>
# ENTRA_JWKS_URL=https://login.microsoftonline.com/<your-tenant-id>/discovery/v2.0/keys
# ENTRA_REDIRECT_URI=http://localhost:8000/auth/callback

# OPTIONAL — group/role mapping
# ENTRA_GROUP_TEAM_MAPPING='{}'
# ENTRA_ROLE_CLEARANCE_MAPPING='{}'
```

## D. Exact Entra Portal Settings

```
Platform:
  Web

Redirect URI:
  http://localhost:8000/auth/callback

Implicit grant and hybrid flows:
  ☑ ID tokens (used for implicit & hybrid flows)
  ☑ Access tokens (used for implicit & hybrid flows)

API permissions:
  None required.
  (Do NOT add Microsoft Graph or any other API permissions.)

Client secret:
  CREATE ONE in "Certificates & secrets" → "New client secret"
  Copy the VALUE (not the Secret ID)
  Set as ENTRA_CLIENT_SECRET environment variable

Tenant ID:
  <copy from Entra portal → Overview → Directory (tenant) ID>

Client ID:
  <copy from Entra portal → Overview → Application (client) ID>
```

## E. PKCE Implementation

**PKCE was implemented.** Reasoning:

1. **Defense-in-depth**: PKCE protects against authorization code interception, even for confidential clients
2. **OAuth 2.1 alignment**: PKCE is recommended for ALL authorization code flows in the upcoming OAuth 2.1 spec
3. **Clean implementation**: 12 lines of code, no architectural changes
4. **No breaking changes**: Existing state/nonce protection is preserved
5. **Standards-compliant**: Uses S256 challenge method per RFC 7636

The implementation:
- Generates a 128-character code_verifier (96 random bytes, base64url-encoded)
- Computes SHA256 code_challenge
- Sends code_challenge in authorization URL
- Sends code_verifier in token exchange
- Entra validates the challenge matches the verifier

## F. Test Results

### Auth Flow Tests (17/17 PASS)

| Test | What It Proves |
|------|---------------|
| Login generates auth URL | ✅ Correct Entra URL |
| Login includes state | ✅ CSRF protection |
| Login includes PKCE challenge | ✅ PKCE S256 in auth URL |
| Callback rejects invalid state | ✅ CSRF protection |
| Callback rejects missing code | ✅ Authorization code required |
| Callback rejects expired state | ✅ Time-limited states |
| PKCE generation | ✅ Verifier 43-128 chars, challenge is SHA256 |
| PKCE stored in pending state | ✅ Verifier persisted for token exchange |
| Session token creation | ✅ JWT signing |
| Expired session rejected | ✅ Token expiry |
| Client secret not in logs | ✅ Secret never exposed |
| Invalid token rejected | ✅ Malformed tokens denied |
| Missing client secret fails safely | ✅ Clear error message |
| Tampered token rejected | ✅ Modified tokens detected |
| Wrong secret rejected | ✅ Wrong signing key denied |
| Anonymous when no auth | ✅ Unauthenticated users |
| Session token auth | ✅ Valid tokens authenticate |

### Full Regression Suite

| Metric | Result |
|--------|--------|
| Total tests | 216 |
| Passed | 216 |
| Failed | 0 |
| Skipped | 1 |

## G. Remaining Manual Steps

1. **Create Entra App Registration** (if not done):
   - Name: `Kurukshetra SANJAYA`
   - Account type: Single tenant
   - Platform: Web
   - Redirect URI: `http://localhost:8000/auth/callback`

2. **Create Client Secret**:
   - Go to Entra portal → App registrations → Your app → Certificates & secrets
   - Click "New client secret"
   - Copy the **VALUE** (not the Secret ID)
   - This value expires in 12 months (configurable)

3. **Set Environment Variables**:
   ```bash
   export ENTRA_TENANT_ID=<from portal>
   export ENTRA_CLIENT_ID=<from portal>
   export ENTRA_CLIENT_SECRET=<the value you copied>
   export KURUKSHETRA_SESSION_SECRET=$(openssl rand -hex 32)
   ```

4. **Test Login Flow**:
   - Start SANJAYA server
   - Open browser to http://localhost:8000
   - Click Login
   - Authenticate with Microsoft
   - Verify redirect back to SANJAYA
   - Verify identity displayed correctly

## Status

**READY FOR ENTRA CONFIGURATION.** All code changes complete. All tests pass. Not committed — awaiting approval.
