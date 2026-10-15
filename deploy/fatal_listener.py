#!/usr/bin/env python3
"""supervisord event listener: on PROCESS_STATE_FATAL, terminate supervisord (and so the container)."""
import os
import signal
import sys


def write(line: str) -> None:
    sys.stdout.write(line)
    sys.stdout.flush()


def main() -> None:
    while True:
        write("READY\n")
        header = sys.stdin.readline()
        if not header:
            return
        fields = dict(token.split(":", 1) for token in header.split())
        payload = sys.stdin.read(int(fields["len"]))
        process = dict(token.split(":", 1) for token in payload.split() if ":" in token).get("processname", "?")
        sys.stderr.write(f"[supervisor] service '{process}' failed repeatedly (FATAL); stopping container.\n")
        sys.stderr.flush()
        write("RESULT 2\nOK")
        os.kill(os.getppid(), signal.SIGTERM)  # parent of an event listener is supervisord


if __name__ == "__main__":
    main()
