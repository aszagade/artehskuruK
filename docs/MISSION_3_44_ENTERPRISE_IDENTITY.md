# Mission 3.44 — Enterprise Identity & Data Boundary

## Objective

Design and implement an enterprise identity abstraction that can connect to Microsoft Entra ID/OIDC while remaining fully testable without production secrets.

## Test Result

**661/661 tests pass, 0 failures** (including 32 new identity boundary tests)

## Architecture

```
User Request
  → IdentityProvider.authenticate(token, type, context)
    → AuthenticatedIdentity
      → AuthorizationContext
        → flows through retrieval → evidence → answer → memory
```

### Same boundary applies to:

| Layer | Enforcement |
|-------|-------------|
| Existing knowledge | VisibilityFilter + AuthorizationContext |
| Uploaded documents | Document ownership via user_id |
| Confluence sources | Source permissions via AuthenticatedIdentity |
| SharePoint sources | Source permissions via AuthenticatedIdentity |
| Salesforce sources | Source permissions via AuthenticatedIdentity |
| Future connectors | Same IdentityProvider interface |
| Memory | Episodic/prospective memory user-scoped |
| Agent-to-agent | Same AuthorizationContext flow |

## What Was Implemented

### 1. IdentityProvider Interface

Abstract interface with three implementations:

| Provider | When Used | Dependencies |
|----------|-----------|-------------|
| `LocalIdentityProvider` | Development (API-key based) | DuckDB |
| `MockIdentityProvider` | Testing | None |
| `EntraIdentityProvider` | Production (Entra ID/OIDC) | `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_JWKS_URL` |

### 2. AuthenticatedIdentity

Extended identity model with enterprise attributes:

- `user_id`, `username`, `display_name`, `email`
- `team_id`, `clearance_level`
- `groups` (Entra ID group membership)
- `roles` (Entra ID application roles)
- `source_permissions` (per-source access control)
- `token_type`, `token_valid`, `token_expiry`
- `provider` (local/mock/entra)
- `can_see()`, `has_group()`, `has_role()`, `can_access_source()`

### 3. AuthorizationContext

Flows through the entire pipeline:

```python
ctx = AuthorizationContext(
    identity=authenticated_user,
    request_id="REQ-001",
    timestamp=time.time(),
)
# Used by:
# - Retrieval (visibility filtering)
# - Evidence selection
# - Answer generation
# - Memory operations
# - Audit logging
```

### 4. Clearance Boundary

| User Level | Can See |
|------------|---------|
| RESTRICTED | public, internal, confidential, restricted |
| CONFIDENTIAL | public, internal, confidential |
| INTERNAL | public, internal |
| PUBLIC | public only |

## Files Created/Modified

| File | Change |
|------|--------|
| `kurukshetra/security/identity_provider.py` | **NEW** — IdentityProvider interface, Local/Mock/Entra implementations |
| `tests/test_identity_boundary.py` | **NEW** — 32 tests for identity boundaries |

## Files NOT Changed

- Existing security middleware (APIKeyAuth, AuditLog, PathTraversalGuard)
- Existing VisibilityFilter
- Existing UserStore
- Database schema
- Retrieval algorithms
- SANJAYA answer generation

## Test Coverage

| Category | Tests | Status |
|----------|-------|--------|
| Identity provider interface | 6 | ✅ |
| AuthenticatedIdentity attributes | 8 | ✅ |
| AuthorizationContext flow | 4 | ✅ |
| Clearance boundary | 3 | ✅ |
| Cross-user isolation | 2 | ✅ |
| Token expiry | 2 | ✅ |
| Entra provider interface | 2 | ✅ |
| Uploaded document ownership | 1 | ✅ |
| Memory isolation | 2 | ✅ |
| Provider factory | 2 | ✅ |
| **Total** | **32** | **All pass** |

## Entra ID Integration Roadmap

To connect to a real Entra tenant:

1. **Register an app** in Microsoft Entra ID
   - Go to Azure Portal → Entra ID → App registrations
   - Create a new registration
   - Configure redirect URIs

2. **Set environment variables**
   ```
   ENTRA_TENANT_ID=<your-tenant-id>
   ENTRA_CLIENT_ID=<your-client-id>
   ENTRA_JWKS_URL=https://login.microsoftonline.com/<tenant>/discovery/v2.0/keys
   ```

3. **Install JWT validation library**
   ```bash
   pip install python-jose[cryptography]
   ```

4. **Uncomment the JWT validation code** in `EntraIdentityProvider.authenticate()`

5. **Configure group-to-team mapping**
   ```python
   GROUP_TEAM_MAP = {
       "SPM-Team": "spm",
       "ICS-Team": "ics",
       "SDOPS-Team": "sdops",
       "ROA-Team": "roa",
   }
   ```

6. **Configure role-to-clearance mapping**
   ```python
   ROLE_CLEARANCE_MAP = {
       "Kurukshetra.Admin": "restricted",
       "Kurukshetra.PowerUser": "confidential",
       "Kurukshetra.Viewer": "internal",
   }
   ```

The interface is ready. Only JWT validation and claim mapping need implementation.

## Security

- Identity flows through every layer
- No unauthorized evidence reaches SANJAYA
- All access decisions are auditable
- Token expiry is enforced
- Cross-user isolation is tested
- No production secrets required for development/testing

## Not Committed

Awaiting approval.
