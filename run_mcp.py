import sys
import os

# Must be set BEFORE any src imports
PROJECT_ROOT = r"C:\Users\user\Desktop\rbi project\regulatory-autopilot"
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

# Hardcode only non-secret paths
os.environ["DB_PATH"] = r"C:\Users\user\Desktop\rbi project\regulatory-autopilot\data\circulars\circulars.db"
os.environ["QDRANT_PATH"] = r"C:\Users\user\Desktop\rbi project\regulatory-autopilot\data\vectors"
os.environ["PDF_DIR"] = r"C:\Users\user\Desktop\rbi project\regulatory-autopilot\data\circulars\pdfs\auto"

# Load secrets (GROQ_API_KEY etc.) from .env — never hardcode them
from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=False)

# Run the MCP server
from src.mcp_servers.watcher_server import main
import asyncio
asyncio.run(main())