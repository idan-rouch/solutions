import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Required vars for the project (excluding OP_PATH)
required_vars = [
    "OKTA_BASE_URL",
    "OKTA_API_TOKEN",
]

missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise EnvironmentError(
        f"Missing required environment variables: {', '.join(missing_vars)}. "
        "Please check your .env file."
    )

# Optional var warning
if not os.getenv("OP_PATH"):
    print("[WARNING] OP_PATH not set. Assuming 'op' is available in PATH.")
