"""Does key derivation actually free the main thread on this build?

Unlock derives in a worker so the login window keeps painting. Whether
that delivers anything is not up to our code: it depends on whether
`cryptography` releases the GIL during PBKDF2, which is not part of its
contract and has changed between versions.

Two sessions of this project measured it and disagreed -- 2 main-thread
iterations on one machine, 337,295 on another -- and neither could settle
it, because each had one environment. So it is measured on every CI run
and printed with the versions it belongs to.

This reports; it does not fail. A build that stops because a library
changed its threading behaviour would be reporting the wrong thing: the
number is a property of the environment, and the point is to have it
written down next to the environment it came from.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time

# The app writes to APPDATA on import; a check has no business touching
# whatever the real one holds.
os.environ.setdefault("APPDATA", tempfile.mkdtemp(prefix="gil-check-"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Below this, the main thread was starved: a derivation takes hundreds of
# milliseconds, and a loop doing nothing should manage orders of
# magnitude more than a handful of turns in that time.
RESPONSIVE_ITERATIONS = 1000


def main() -> int:
    import cryptography

    from password_vault.crypto import derive_key

    salt = os.urandom(32)
    password = "MeasurementOnly123!"

    started = time.perf_counter()
    derive_key(password, salt)
    alone = (time.perf_counter() - started) * 1000

    spins = 0
    finished = threading.Event()

    def work():
        derive_key(password, salt)
        finished.set()

    started = time.perf_counter()
    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    after_start = (time.perf_counter() - started) * 1000
    while not finished.is_set():
        spins += 1
        time.sleep(0)
    worker.join()

    freed = spins >= RESPONSIVE_ITERATIONS
    print(f"python                : {sys.version.split()[0]}")
    print(f"cryptography          : {cryptography.__version__}")
    print(f"one derivation        : {alone:.0f} ms")
    print(f"Thread.start() took   : {after_start:.1f} ms")
    print(f"main-thread iterations: {spins:,}")
    print()
    print("the GIL is released during PBKDF2 — unlocking really does "
          "free the window" if freed else
          "the GIL is HELD during PBKDF2 — the worker does not free the "
          "window on this build, and unlock will feel frozen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
