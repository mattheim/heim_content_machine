import time
from datetime import datetime
from content_machine import run_machine

def run_once():
    started = datetime.now()
    print(f"[{started:%Y-%m-%d %H:%M:%S}] Run starting…")
    run_machine()
    finished = datetime.now()


def run_loop(interval_seconds: int = 2 * 60 * 60) -> None:
    """Run the content machine every `interval_seconds` (default: 2 hours)."""
    print(f"Scheduler started. Interval: {interval_seconds} seconds (~2 hours)")
    try:
        while True:
            started = datetime.now()
            print(f"[{started:%Y-%m-%d %H:%M:%S}] Run starting…")
            t0 = time.perf_counter()
            try:
                run_machine()
            except Exception as exc:
                # Log and continue next cycle
                print(f"Run error: {exc}")
            t1 = time.perf_counter()
            elapsed = t1 - t0
            remaining = max(0, interval_seconds - elapsed)
            finished = datetime.now()
            print(
                f"[{finished:%Y-%m-%d %H:%M:%S}] Run finished in {elapsed:.2f}s. "
                f"Sleeping for {int(remaining)}s…"
            )
            time.sleep(remaining)
    except KeyboardInterrupt:
        print("Scheduler stopped by user.")


def main():
    #run_loop()
    run_once()


if __name__ == "__main__":
    main()
