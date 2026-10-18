"""Refresh the source cache on a schedule; never manufacture a live response."""
import os, time, traceback
from datetime import datetime, timezone
import app
import storage

INTERVAL=max(180,int(os.getenv('EDGE_REFRESH_INTERVAL_SECONDS','300')))

def main():
    while True:
        started=datetime.now(timezone.utc).isoformat()
        try:
            app.refresh_all()
            storage.set_state(app.DB_PATH,'worker_last_run',started)
            storage.set_state(app.DB_PATH,'worker_last_status','ok')
        except Exception as exc:
            storage.set_state(app.DB_PATH,'worker_last_run',started)
            storage.set_state(app.DB_PATH,'worker_last_status','error')
            storage.set_state(app.DB_PATH,'worker_last_error',f'{type(exc).__name__}: {exc}'[:1000])
            traceback.print_exc()
        time.sleep(INTERVAL)

if __name__=='__main__': main()
