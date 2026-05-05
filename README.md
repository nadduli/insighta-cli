# Insighta Labs+ — CLI

Globally-installable command-line client for Insighta Labs+. Authenticates
via GitHub PKCE, stores credentials at `~/.insighta/credentials.json`, and
speaks to the same backend as the web portal.

```bash
insighta login
insighta profiles search "young males from nigeria"
insighta profiles export --format csv --gender male --country NG
```

---

## Installation

The CLI is a Python package built with [`uv`](https://docs.astral.sh/uv/).
Install it globally with `uv tool`:

```bash
git clone <cli-repo-url>
cd insighta-cli
uv tool install .
```

That puts an `insighta` script on your `PATH` so it works from any directory.
To upgrade later: `uv tool install --reinstall .`. To uninstall:
`uv tool uninstall insighta-cli`.

> Alternative: `pipx install .` from inside the repo. Either tool is fine.

### Configuration

The CLI reads three environment variables. Copy `.env.example` to `.env` and
load it (e.g. `source .env`), or export them in your shell rc:

| Variable                     | Default                  | Notes                                  |
|------------------------------|--------------------------|----------------------------------------|
| `INSIGHTA_BACKEND_URL`       | `http://localhost:8000`  | Where the backend is reachable         |
| `INSIGHTA_GITHUB_CLIENT_ID`  | (required for `login`)   | Client ID of the **CLI** GitHub OAuth app |
| `INSIGHTA_CALLBACK_PORT`     | `51420`                  | Loopback port for the OAuth redirect   |

The redirect URI registered on the GitHub OAuth app must be
`http://127.0.0.1:<INSIGHTA_CALLBACK_PORT>/callback` and must match the
backend's `GITHUB_CLI_CALLBACK_PORT`.

---

## Commands

```
insighta login                  # PKCE OAuth flow → ~/.insighta/credentials.json
insighta logout                 # revoke session + clear local credentials
insighta whoami                 # show the authenticated user (calls /auth/me)

insighta profiles list                                            # paginated, defaults
insighta profiles list --gender male --country NG --age-group adult
insighta profiles list --min-age 25 --max-age 40
insighta profiles list --sort-by age --order desc --page 2 --limit 20

insighta profiles get <id>                                        # single profile
insighta profiles search "young males from nigeria"               # NL query
insighta profiles create --name "Harriet Tubman"                  # admin only

insighta profiles upload ./profiles.csv                           # admin only — bulk import
                                                                  # streams the file, skips bad rows,
                                                                  # prints a per-reason summary

insighta profiles export --format csv                             # → ./profiles_<timestamp>.csv
insighta profiles export --format csv --gender male --country NG
insighta profiles export --format csv -o /tmp/profiles.csv        # custom path
```

Run `insighta --help` or `insighta profiles --help` for the full reference.

---

## Authentication Flow (PKCE)

The CLI never sees the GitHub client secret — that lives only on the
backend. Instead it uses Proof Key for Code Exchange:

```
1. CLI generates:
     - state          (random, validates the redirect)
     - code_verifier  (random, kept secret in memory)
     - code_challenge = base64url(SHA-256(code_verifier))

2. CLI starts a temporary HTTP server on 127.0.0.1:<port>.

3. CLI opens the user's browser to:
     https://github.com/login/oauth/authorize?
       client_id=<CLI app>
       &redirect_uri=http://127.0.0.1:<port>/callback
       &scope=read:user user:email
       &state=<state>
       &code_challenge=<challenge>
       &code_challenge_method=S256

4. User authorizes on github.com.
   GitHub redirects to http://127.0.0.1:<port>/callback?code=...&state=...

5. CLI verifies the returned `state` matches what it generated
   (anything else → abort).

6. CLI POSTs the code AND the original verifier to:
     POST <backend>/auth/cli/exchange
     { "code": "...", "code_verifier": "..." }

7. Backend exchanges with GitHub (using the secret) AND forwards the
   verifier so GitHub can re-derive and check the challenge.
   Backend returns:
     { access_token, refresh_token, user }

8. CLI persists the tokens to ~/.insighta/credentials.json (mode 0600).
```

The CLI is treated as a public client; the secret is held only by the
backend, and the PKCE pair binds the authorization request to the
eventual exchange.

---

## Token Handling

### Where tokens live

`~/.insighta/credentials.json`, written with mode **0600** (user
read/write only). The directory itself is `0700`.

```json
{
  "backend_url": "https://...",
  "access_token": "...",
  "refresh_token": "...",
  "user_id": "...",
  "username": "...",
  "role": "analyst",
  "saved_at": "2026-04-30T08:00:00+00:00"
}
```

The file is written via temp-file + atomic-rename so a crash mid-write
never leaves a half-baked credentials file.

### Auto-refresh

Every API request goes through one wrapper (`APIClient.request`) that:

1. Sends `Authorization: Bearer <access_token>` and `X-API-Version: 1`.
2. On a `401`, calls `POST /auth/refresh` with the stored refresh token.
3. If the refresh succeeds, persists the new pair and **retries the
   original request once**.
4. If the refresh fails, deletes the local credentials and raises
   `NotAuthenticated`, surfaced as
   `Session expired. Run insighta login again.`

The refresh endpoint always returns a brand-new pair. The previous refresh
token is invalidated server-side immediately, so a stolen token fails on
first use. (See the backend README for family-wide reuse detection.)

### Logout

`insighta logout` calls `POST /auth/logout` with the refresh token (best
effort — even if the network is down it still wipes the local credentials).

---

## Output

- Every network call shows a Rich spinner while it runs.
- `profiles list` / `profiles search` render results as a table with a
  pagination footer (`Page 1/203 — 2026 matching profiles.`).
- `profiles get` renders a vertical key/value detail.
- `profiles export` streams CSV to disk and prints the destination path.
- All errors print to stderr as `Error: <message>`, preserving the
  backend's message text.

---

## Project Layout

```
src/insighta_cli/
├── cli.py             # top-level Typer app + main() entrypoint
├── config.py          # env-driven configuration
├── credentials.py     # ~/.insighta/credentials.json store
├── auth.py            # PKCE flow + loopback callback server
├── client.py          # APIClient with auto-refresh on 401
├── output.py          # Rich tables, spinner, error formatter
└── commands/
    ├── auth.py        # login, logout, whoami
    └── profiles.py    # list, get, search, create, export
```

---

## Development

```bash
uv sync --all-extras                    # install runtime + dev deps
uv run pytest -q                        # run the test suite
uv run ruff check .                     # lint

# run the CLI without a global install
uv run insighta --help
```

CI (`.github/workflows/ci.yml`) runs lint + tests + a build on every PR
and push to `main`.

---

## Author

**Nadduli Daniel** — naddulidaniel94@gmail.com
[GitHub](https://github.com/naddulidaniel) · [LinkedIn](https://linkedin.com/in/nadduli-daniel)
