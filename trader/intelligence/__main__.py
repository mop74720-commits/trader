"""Run the collector independently of the trading process."""
import argparse
import json
import time
from pathlib import Path

from .service import DEFAULT_CONFIG, IntelligenceHub
from .sources import timestamp


def main():
    parser=argparse.ArgumentParser(description="Public information collector; never submits trades or messages")
    parser.add_argument("--config",type=Path,default=DEFAULT_CONFIG)
    parser.add_argument("--db",type=Path,default=Path("data/intelligence.sqlite3"))
    parser.add_argument("--once",action="store_true",help="Collect sources due now, print status, and exit")
    parser.add_argument("--digest",action="store_true",help="Read a digest without network collection")
    parser.add_argument("--as-of",help="Digest cutoff ISO-8601 timestamp with timezone")
    parser.add_argument("--enable-x-api",action="store_true",help="Explicitly enable configured X requests, potentially billable")
    args=parser.parse_args()
    if args.as_of and not args.digest:
        parser.error("--as-of requires --digest")
    as_of=timestamp(args.as_of) if args.as_of else None
    if args.as_of and as_of is None:
        parser.error("Invalid --as-of timestamp")
    hub=IntelligenceHub.from_config(args.db.resolve(),args.config.resolve(),args.enable_x_api)
    try:
        if args.digest:
            print(json.dumps(hub.digest(as_of),ensure_ascii=False,indent=2))
        elif args.once:
            print(json.dumps(hub.collect_once(),ensure_ascii=False,indent=2))
        else:
            hub.start()
            print("Intelligence collector started; Ctrl+C to stop.",flush=True)
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        hub.close()


if __name__=="__main__":
    main()
