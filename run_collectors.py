"""Run every phase 1-2 collector. Each one is independent: a failure is logged, not fatal."""
import importlib
import sys
import traceback

COLLECTORS = ["repo_rate", "rainfall", "gold", "trends", "app_reviews", "review_dataset"]

if __name__ == "__main__":
    wanted = sys.argv[1:] or COLLECTORS
    failed = []
    for name in wanted:
        print(f"\n=== {name} ===")
        try:
            importlib.import_module(f"src.collectors.{name}").main()
        except Exception:
            traceback.print_exc()
            failed.append(name)
    print(f"\nDone. Failed: {failed or 'none'}")
