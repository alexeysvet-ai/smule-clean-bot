import asyncio
from datetime import datetime, timezone

download_semaphore = asyncio.Semaphore(1)

user_requests = {}
last_update_ts = None
process_start_ts = datetime.now(timezone.utc).timestamp()