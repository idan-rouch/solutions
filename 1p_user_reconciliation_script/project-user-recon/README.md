# 1Password ↔ Okta Reconciliation Tool

A Python-based reconciliation and remediation tool for Okta and the 1Password SCIM Bridge. It detects mismatches, exports CSVs for auditing, and automates fixes like reprovisioning, deprovisioning, and SCIM onboarding.

## Features
- Fetch users from both Okta and 1Password (via SCIM).
- Reconcile and categorize users into distinct buckets:
  - to_provision: Users who are `ACTIVE` in Okta but missing from 1Password.
  - to_deprovision: Users inactive in the IdP but still active in 1Password.
  - to_scim_onboard: Users active in 1Password but not managed by SCIM.
  - in_1p_not_in_idp: Users active in 1Password but not found in Okta at all.
- Reprovision: Automatically remove and re-add a user to the Okta SCIM group to trigger a provisioning push.
- Deprovision: Use a SCIM `PATCH` request to set `active=false` in 1Password, with an optional fallback to the `op` CLI.
- CSV Export: Generate CSV reports for auditing and manual review.

## Prerequisites
- Python 3.10+ (tested up to 3.13).
- An Okta application configured for SCIM, with a group assigned to the 1Password app.
- An Okta API token.
- Your 1Password SCIM Bridge base URL and bearer token (this is the connector host, not the web UI).
- Optional: 1Password `op` CLI installed, requiring Owner or Admin rights for fallback operations.

## Installation

git clone <repo-url>
cd project-user-recon
python3 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env

## Environment Setup
Copy the `.env.example` file to `.env` and populate it with your specific credentials. Ensure you use the SCIM Bridge base URL, which is the host that returns an HTTP 200 status at the `/ServiceProviderConfig` endpoint. Remember to keep your `.env` file out of version control (.gitignore).

Required variables:
- OKTA_BASE_URL: Your Okta organization URL (e.g., `https://mycompany.okta.com`).
- OKTA_API_TOKEN: An Okta API token with the necessary permissions.
- OKTA_SCIM_GROUP_ID: The ID of the Okta group assigned to the 1Password SCIM application.
- OP_SCIM_BASE_URL: The base URL for your SCIM Bridge.
- OP_SCIM_BEARER_TOKEN: The bearer token for your SCIM Bridge.
- OP_ACCOUNT: Your 1Password account domain for CLI fallback (e.g., `yourcompany.1password.com`).

Optional variables:
- OP_PATH: The path to the `op` CLI executable if it's not in your system's `PATH`.
- OP_MOCK: Set to `true` to mock `op` CLI calls for testing.
- OP_ADMIN_BASE_URL: The 1Password Admin API base URL (if extending beyond SCIM).
- OP_SERVICE_ACCOUNT_TOKEN: A 1Password Service Account token (if extending beyond SCIM).

Load env:
```
export $(grep -v '^#' .env | xargs)
```

Sign into 1Password and validate login:
```bash
op signin [-f] # Or "eval $(op signin)"
op whoami
```

You can run these quick health/sanity checks to verify your credentials:
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $OP_SCIM_BEARER_TOKEN" "$OP_SCIM_BASE_URL/ServiceProviderConfig"
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: SSWS $OKTA_API_TOKEN" "$OKTA_BASE_URL/api/v1/users?limit=1"
python -c 'import sys, click; print("python:", sys.executable); import importlib.metadata as m; print("click:", m.version("click"))'
python -m src.recon.cli --help

Example `.env` file:
OP_PATH=
OP_MOCK=false
OKTA_BASE_URL=https://your-okta-domain.okta.com
OKTA_API_TOKEN=your-okta-api-token
OKTA_SCIM_GROUP_ID=your-okta-scim-group-id
OP_SCIM_BASE_URL=https://your-scim-bridge.example.com
OP_SCIM_BEARER_TOKEN=your-scim-bearer-token
OP_ACCOUNT=your-1password-account-domain
OP_ADMIN_BASE_URL=https://api.your-region.1password.com
OP_SERVICE_ACCOUNT_TOKEN=your-op-service-account-token

## Project Structure
.
├── 0
├── docs
│   └── USER_GUIDE.md
├── env.example
├── Makefile
├── out
│   ├── in_1p_not_in_idp.csv
│   ├── to_deprovision.csv
│   ├── to_provision.csv
│   └── to_scim_onboard.csv
├── README.md
├── requirements.txt
├── run_recon.py
├── src
│   ├── __init__.py
│   ├── __pycache__
│   │   └── __init__.cpython-313.pyc
│   └── recon
│       ├── __init__.py
│       ├── __pycache__
│       │   ├── __init__.cpython-313.pyc
│       │   ├── cli.cpython-313.pyc
│       │   ├── engine.cpython-313.pyc
│       │   ├── okta.cpython-313.pyc
│       │   ├── onepassword.cpython-313.pyc
│       │   ├── op_cli.cpython-313.pyc
│       │   ├── scim.cpython-313.pyc
│       │   └── util.cpython-313.pyc
│       ├── cli.py
│       ├── engine.py
│       ├── okta.py
│       ├── onepassword.py
│       ├── op_cli.py
│       ├── scim.py
│       └── util.py
└── tests
    ├── fixtures
    │   └── op_user_list.json
    └── test_onepassword.py

## Usage
Always activate your virtual environment before running the tool:
source .venv/bin/activate

Show the CLI help menu for a list of all commands and options:
python -m src.recon.cli --help

List users from each service (useful for smoke tests):
python -m src.recon.cli list-okta
python -m src.recon.cli list-1p

Run a dry-run reconciliation to see what actions would be taken. This is a read-only operation and will not make any changes. It will write CSVs to the specified directory.
python -m src.recon.cli recon-dryrun --csv-dir out

Reprovision a single user by re-adding them to the Okta SCIM group:
python -m src.recon.cli reprovision --email "user@example.com" --okta-group-id "$OKTA_SCIM_GROUP_ID" --wait-seconds 45 --interval 5

Batch reprovision multiple users from a CSV file:
python -m src.recon.cli reprovision-batch --csv users.csv --okta-group-id "$OKTA_SCIM_GROUP_ID"

Apply deprovisioning. This will first attempt to use SCIM. Use `--no-cli` to prevent it from falling back to the `op` CLI.
python -m src.recon.cli apply-deprovision --execute --csv-dir out --no-cli

Apply SCIM onboarding to existing 1Password users:
python -m src.recon.cli apply-scim-onboard --execute --okta-group-id "$OKTA_SCIM_GROUP_ID" --csv-dir out

## Testing with curl
Remember to URL-encode the `+` symbol in email addresses as `%2B`.

Check if the SCIM service is reachable:
curl -s -H "Authorization: Bearer $OP_SCIM_BEARER_TOKEN" "$OP_SCIM_BASE_URL/ServiceProviderConfig" | jq

Look up a user in Okta by their login/email:
ENC="user%2Btag@example.com"
curl -s -H "Authorization: SSWS $OKTA_API_TOKEN" "$OKTA_BASE_URL/api/v1/users?search=profile.login%20eq%20%22$ENC%22" | jq

Look up a user in 1Password via SCIM:
ENC="user%2Btag@example.com"
curl -s -H "Authorization: Bearer $OP_SCIM_BEARER_TOKEN" "$OP_SCIM_BASE_URL/Users?filter=userName%20eq%20%22$ENC%22" | jq -r '.Resources | length, (.[0]? | .id // empty), (.[0]? | .userName // empty)'

Check SCIM presence:
```bash
ENC_EMAIL="user%40domain.com"
curl -s -H "Authorization: Bearer $OP_SCIM_BEARER_TOKEN"   "$OP_SCIM_BASE_URL/Users?filter=userName%20eq%20%22$ENC_EMAIL%22" | jq
```

Deactivate a user via SCIM PATCH request:
USER_ID="SCIM_ID"
curl -s -X PATCH \
-H "Authorization: Bearer $OP_SCIM_BEARER_TOKEN" \
-H "Content-Type: application/scim+json" \
"$OP_SCIM_BASE_URL/Users/$USER_ID" \
--data '{"schemas":["urn:ietf:params:scim:api:messages:2.0:PatchOp"],"Operations":[{"op":"replace","value":{"active":false}}]}'

## Common Issues
- SCIM returns HTML/404: You are likely using the 1Password web UI host. Use the SCIM connector host URL instead.
- Okta search misses emails with `+`: The `+` character must be URL-encoded as `%2B` in API requests.
- SCIM PATCH 400 Bad Request: Ensure your `Content-Type` header is `application/scim+json` and the data payload is correctly formatted.
- `op` CLI returns 403 Forbidden: The identity used to run the command lacks sufficient privileges. Use an Owner or Admin account, or skip the CLI fallback with `--no-cli`.
- Zsh quirks: Avoid using comments with a `)` on the same line, and always quote your shell variables to prevent unexpected expansion.

## Safety Notes
- `recon-dryrun` is a read-only command and completely safe to run.
- `reprovision` is idempotent. Running it multiple times will not cause issues.
- `apply-deprovision` makes state changes in 1Password. It's recommended to use `--no-cli` unless you specifically intend to use the CLI fallback.

```
