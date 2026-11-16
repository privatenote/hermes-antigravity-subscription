"""Real pipes must respect deadlines and preserve the next worker turn."""
import io
import json
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

from process import TurnStdoutReader
from stream import AntigravityStream


def test_turn_reader_never_prefetches_the_next_turn():
    result = json.dumps({"event": "result", "result": {"status": "SUCCESS"}}) + "\n"
    proc = SimpleNamespace(stdout=io.StringIO(result + "NEXT_TURN\n" + result))
    first = TurnStdoutReader(proc)
    try:
        assert first.readline(1) == result
        first._thread.join(1)
        assert not first._thread.is_alive()
        second = TurnStdoutReader(proc)
        try:
            assert second.readline(1) == "NEXT_TURN\n"
            assert second.readline(1) == result
        finally:
            second.close()
    finally:
        first.close()


def test_silent_live_process_cannot_block_stream_past_its_deadline():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    client = SimpleNamespace(_worker_proc=proc, _isolated_gemini_dir=None)

    def terminate():
        proc.kill()
        proc.wait(timeout=2)
        client._worker_proc = None

    client._terminate_worker = terminate
    stream = AntigravityStream(proc=proc, client=client, model="test", timeout=0.15, is_worker=True)
    errors = []

    def consume():
        try:
            list(stream)
        except Exception as exc:
            errors.append(exc)

    consumer = threading.Thread(target=consume, daemon=True)
    start = time.monotonic()
    consumer.start()
    try:
        consumer.join(1.5)
        assert not consumer.is_alive(), "Blocking pipe read ignored the deadline"
        assert time.monotonic() - start < 1.5
        assert len(errors) == 1 and "stream deadline" in str(errors[0])
        assert proc.poll() is not None
    finally:
        if proc.poll() is None:
            terminate()
        consumer.join(2)
        proc.stdout.close()
