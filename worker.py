"""Standalone polling worker. Run as a separate systemd service."""
import os, time, traceback
from datetime import datetime, timezone
from engine import scan_opportunities
from storage import init_db, save_opportunity, save_snapshot, set_worker_state

APP_DIR=os.path.dirname(os.path.abspath(__file__))
DB_PATH=os.environ.get("EDGE_DB_PATH",os.path.join(APP_DIR,"data","edge.db"))
INTERVAL=max(60,int(os.getenv("EDGE_SCAN_INTERVAL_SECONDS","180")))
init_db(DB_PATH)

def main():
    while True:
        started=datetime.now(timezone.utc).isoformat()
        try:
            result=scan_opportunities()
            items=result.get("items",[])
            for item in items:
                save_opportunity(DB_PATH,item)
                save_snapshot(DB_PATH,item)
            set_worker_state(DB_PATH,"last_attempt",started)
            set_worker_state(DB_PATH,"last_success",datetime.now(timezone.utc).isoformat() if result.get("data_status") in ("live_response","empty_response") else "provider_unavailable")
            set_worker_state(DB_PATH,"last_count",len(items))
            set_worker_state(DB_PATH,"last_status",result.get("data_status","unknown"))
            set_worker_state(DB_PATH,"last_error","; ".join(result.get("provider_errors",[]))[:500])
        except Exception as exc:
            set_worker_state(DB_PATH,"last_attempt",started)
            set_worker_state(DB_PATH,"last_error",str(exc)[:500])
            traceback.print_exc()
        time.sleep(INTERVAL)

if __name__=="__main__": main()
