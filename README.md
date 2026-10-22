# User Access Management Portal

Single sign-on and central role management for the company's systems.

- **One account per person.** Users sign in once at the portal and are then signed in to every system they have access to.
- **Roles and permissions per system.** Each registered system has its own roles (e.g. HR: `employee`, `manager`, `hr-admin`) and permissions (e.g. `leave.approve`). Admins decide which permissions each role grants and which roles each user holds, all in the portal.
- **Standard protocol.** The portal is an **OpenID Connect provider** (OAuth 2.0 authorization code flow + PKCE, RS256-signed JWTs). Any OIDC client library can integrate: Python, .NET, Java/Spring, Node, PHP and others.
- **Audit log** of sign-ins, SSO grants, denials and every admin change.

```
┌──────────────┐  1. redirect to /oauth/authorize   ┌──────────────────────────┐
│  HR system   │ ─────────────────────────────────► │   Access Portal          │
│  CRM system  │                                    │   React UI  +  FastAPI   │
│  ...         │ ◄───────────────────────────────── │   (OIDC provider)        │
└──────────────┘  2. back with code → exchange for  └──────────────────────────┘
                     ID/access token with "roles"
```

## Project layout

| Path | What |
|---|---|
| `backend/` | FastAPI: portal API, OIDC endpoints, SQLAlchemy models |
| `frontend/` | React + TypeScript (Vite): login, "My apps" launchpad, admin screens |
| `examples/demo_client/` | A sample "Demo HR" system showing how a system integrates |

## Running locally

Requires Python 3.11+ and Node 18+.

**1. Backend** (port 8110, the same as on the server; 8000 is used by the Logistics Price Calculator's API)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # set ADMIN_PASSWORD, or read the generated one from the log
uvicorn app.main:app --reload --port 8110
```

The first start creates the database, an RSA signing key in `backend/keys/`, and the initial admin account.

**2. Frontend** (port 5173). Open http://localhost:5173.

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server forwards `/api`, `/oauth` and `/.well-known` to the backend, so the portal and its OIDC issuer share one origin: `http://localhost:5173`.

**3. Optional: demo systems.** Demo HR runs on port 9000, Demo CRM on port 9001.

```bash
cd backend
python -m app.seed_demo          # registers Demo HR + Demo CRM with their roles, writes their env files
python -m app.seed_users         # sample users with different roles in each system (backend must be running)
cd ../examples/demo_client
pip install -r requirements.txt
uvicorn app:app --port 9000 --env-file .env
uvicorn app:app --port 9001 --env-file crm.env     # in a second terminal
```

Sign in at http://localhost:9000, then open http://localhost:9001: the CRM signs you in automatically, without a click or a password. Every page in the demo systems requires sign-in, so when a system has no session for the user it **redirects straight to the portal** (no "Sign in" button): users already signed in there are back instantly, others see the portal's sign-in page, and either way they land on the page they asked for. This is the right pattern for internal systems. A system that also has public pages can instead check silently with `prompt=none`, which the portal supports: it returns a code if the user is already signed in, or `login_required` / `access_denied` without showing any page. Each demo system has a **Behind the scenes** page (`/behind-the-scenes`) that records every step of the sign-in as it happens: the redirects, the code, the server-to-server token exchange, the signature checks, permission checks and token refreshes. The two systems run the same example code, configured by their env files.

| Sample user | Demo HR | Demo CRM |
|---|---|---|
| alice.tan | employee | sales-rep |
| bob.lim | employee, manager | sales-manager |
| chloe.ng | hr-admin | no access |
| david.wong | employee | support-agent |
| emma.lee | no access | sales-rep, support-agent |
| frank.ho | employee | sales-rep (account disabled) |

**Tests**

```bash
cd backend
pytest
```

## Admin workflow

1. **Systems → Register system.** Enter a name, client ID, launch URL and redirect URI(s). For server-side apps, copy the client secret shown once. Untick "client secret" for browser-only SPAs or mobile apps; those use PKCE.
2. **Roles tab:** add the system's roles (e.g. `viewer`, `editor`, `admin`).
3. **Permissions tab:** add the permissions the system's code checks (e.g. `invoices.view`, `invoices.approve`), then tick which roles grant each one in the role × permission grid.
4. **Users → user → System access.** Tick the roles the user should have in each system. The page previews the permissions the user will end up with before you save.

When an admin creates a user, the portal emails them their username, email, temporary password, and the sign-in address (with the mail server set below; otherwise the admin page says to tell them yourself). They must choose their own password at the first sign-in.

A user can sign in to a system only if they hold **at least one** of its roles. Otherwise the portal shows "Access denied" and no token is issued.

### Access requests

People without access click **Request access** under the sign-in form, enter their company email and choose a system (pre-selected when a system sent them to sign in, or when only one is offered). Only systems with **Allow access requests** switched on (system → Settings; off by default) are offered. Admins see the requests under **Access requests** (the menu shows how many are open):

- **Approve:** with no account for that email yet, enter a username (suggested from the email) and a temporary password, and choose a role: the account is created and gets the role, and must change its password at first sign-in. With an existing account, just choose the role to add. The person is emailed: a new account gets its username, **temporary password**, and where to sign in (the system's launch URL); an existing one gets the system and its username.
- **Decline:** closes the request, with an optional reason. The person is emailed that it was declined, with the reason if there is one.

The public page answers the same whether or not an account exists, ignores a repeat of an open request or a request for access the person already has, and accepts at most 5 requests an hour from one address. Requests, approvals and declines are in the audit log.

**Email (optional):** set the mail server in `backend/.env`: every active admin is emailed about each new request, and the requester about the decision. Without `SMTP_HOST`, nothing is sent, and the admin page says so after each decision (then tell the person yourself).

```
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USER=mailbox@pahtama.com
SMTP_PASSWORD=...
SMTP_FROM=Access Portal <mailbox@pahtama.com>   # optional; defaults to "Access Portal <SMTP_USER>"
SMTP_USE_TLS=true
```

## Integrating a system

Systems use a standard OpenID Connect library; no portal-specific code is needed. Each system's
**Integration** tab in the portal shows a Quick start with its values filled in:

- **React app:** `oidc-client-ts` + `react-oidc-context` (sign-in, tokens, refresh, sign-out).
- **Python API:** PyJWT verifies each request's access token with the portal's public key
  (download it from `/oauth/public-key.pem`), then checks roles or permissions.
- **Server-side web apps:** the framework's own OIDC library (.NET, Spring, Authlib, openid-client…).

The Promotion Approval Form (`C:\projects\PromotionApprovalForm`) is a working example of the React + Python
setup. The older starter kits in `kits/` still work but are no longer the recommended path. The rest
of this section describes the underlying protocol.

Configure the system as an OIDC client:

| Setting | Value |
|---|---|
| Discovery URL | `https://<portal>/.well-known/openid-configuration` |
| Client ID / secret | from the system's page in the portal |
| Scopes | `openid profile email` |
| Response type | `code` (with PKCE `S256`) |
| Permissions | `permissions` claim in the ID token, access token and userinfo (array of strings). **Check these in code.** |
| Roles | `roles` claim (array of strings), for systems that only need roles |

Example ID token payload:

```json
{
  "iss": "https://portal.company.com", "sub": "42", "aud": "hr",
  "preferred_username": "alice", "name": "Alice A", "email": "alice@company.com",
  "roles": ["manager"], "permissions": ["leave.approve", "records.view_own"],
  "nonce": "...", "exp": 1790000000
}
```

The system must verify the token's signature with the JWKS (`/oauth/jwks`), and check `iss`, `aud` (its own client ID), `exp` and `nonce`. It then checks the `permissions` claim before each protected action:

```python
if "invoices.approve" not in user["permissions"]:
    raise HTTPException(403)
```

Permission names are a contract: the names in the portal must match the names the code checks. Rules that depend on the data itself ("only your own invoices") stay in the system's code. See [examples/demo_client/app.py](examples/demo_client/app.py) for a full, short implementation.

Endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /oauth/authorize` | start sign-in (reuses the SSO session if the user is already signed in) |
| `POST /oauth/token` | `authorization_code` and `refresh_token` grants (refresh tokens rotate) |
| `GET /oauth/userinfo` | current profile, roles and permissions for a Bearer access token |
| `GET /oauth/jwks` | public signing keys |
| `POST /oauth/revoke` | revoke a refresh token |
| `GET /oauth/logout?client_id=…&post_logout_redirect_uri=…` | single sign-out |

**How changes propagate**

- **Role and permission changes** apply at the user's next sign-in or token refresh. Access tokens last 15 minutes by default.
- **Disabling a user** ends their portal session and revokes all refresh tokens, so they lose access to every system within one access-token lifetime.
- **Sign-out** from any system (via `/oauth/logout`) or from the portal ends the SSO session everywhere. Each system should also clear its own local session, as the demo does.

## Production checklist

- Serve the portal over **HTTPS** on one domain, and set `ISSUER`, `FRONTEND_URL` to that URL and `COOKIE_SECURE=true`.
- Build the UI (`npm run build`). FastAPI serves `frontend/dist` automatically when it exists, or you can serve it from your reverse proxy.
- Use **SQL Server** (see *Moving to SQL Server* below) and add Alembic migrations before the schema changes. Today tables are created with `create_all`.
- Keep `backend/keys/private.pem` secret and back it up. If it is lost, all systems' issued tokens become invalid.
- Run uvicorn with `--proxy-headers` behind a proxy so audit IPs are correct.
- Add login rate limiting / lockout, and consider MFA, or federating to Azure AD / Google Workspace if the company already uses one.

## Importing the Logistics Price Calculator's users

`python -m app.import_lpc` (dry run) / `--apply` copies LPC's roles, permissions and users from its own
database (`LogCalculatorTest`, using `DWBI_USER` / `DWBI_PASSWORD` from LPC's `backend/.env`) into the portal's
*Logistics Price Calculator* system. Users keep their current LPC passwords (bcrypt hashes are copied), get
`<username>@pahtama.com`, and LPC's `admin` becomes `lpc.admin`. Safe to re-run; see the script's docstring.

## Moving to SQL Server

Target: `phm\reportingsvr`, database `AccessManagement`, Windows authentication. Needs the
*ODBC Driver 18 for SQL Server* and `pyodbc` (in `requirements.txt`). Run from `backend/`, on the company
network (or VPN), as a Windows account that may create tables in `AccessManagement`:

1. **Stop the portal** so nothing changes during the copy.
2. **Copy the data** (creates the tables; refuses if they already contain data; the SQLite file is not changed):
   ```powershell
   .\.venv\Scripts\python -m app.migrate_db --to "mssql+pyodbc://@phm\reportingsvr/AccessManagement?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
   ```
3. **Point the portal at it:** set the same URL as `DATABASE_URL` in `backend/.env`.
4. **Start the portal** and sign in. Keep `uam.db` as a backup until you're happy.

Notes:
- **Authentication:** set `DATABASE_USER` and `DATABASE_PASSWORD` in `backend/.env` to use a SQL Server login
  (the password needs no URL-encoding there). Leave both empty for **Windows authentication** as the account
  running the portal; when it runs as a service, that service account then needs access to `AccessManagement`.
  The login needs read/write on the portal's tables (e.g. `db_datareader` + `db_datawriter`), plus permission to
  create tables the first time.
- `TrustServerCertificate=yes` accepts the server's certificate without checking it (common for internal servers
  with self-signed certificates). Remove it once the server has a trusted certificate.
- Text columns are `NVARCHAR`, so names in any script (e.g. Myanmar) are stored correctly.
