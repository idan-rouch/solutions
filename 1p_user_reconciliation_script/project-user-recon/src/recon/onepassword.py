import json
import subprocess

def normalize_user(user):
    """
    Normalize a single user record into a consistent dictionary.
    Input can be from mock data or real op CLI output.
    """
    return {
        "email": user.get("email"),
        "status": user.get("state").upper() if user.get("state") else None,
        "id": user.get("id")
    }

def list_1password_users(mock=False):
    """
    Return a list of users in a normalized format:
    [
        {"email": "alice@example.com", "status": "ACTIVE", "id": "USR-1"},
        ...
    ]
    """
    if mock:
        mock_users = [
            {"email": "idan.rouch+oktatest@agilebits.com", "state": "ACTIVE", "id": "USR-999"},
            {"email": "bob@example.com", "state": "SUSPENDED", "id": "USR-2"},
            {"email": "eva@example.com", "state": "DELETED", "id": "USR-3"},
        ]
        return [normalize_user(u) for u in mock_users]

    # Run the real 1Password CLI command
    cmd = ["op", "user", "list", "--format", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    users_raw = json.loads(result.stdout)

    # Normalize the real data
    return [normalize_user(u) for u in users_raw]
