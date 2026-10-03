import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time


class FakeDecisions:
    """A local Decisions endpoint keyed by state.directory."""
    def __init__(self, table):
        self.table = table
        self.requests = []
        self.request_times = []
        self._counts = {}
        self._lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                directory = body.get("state", {}).get("directory")
                with outer._lock:
                    outer.requests.append(body)
                    outer.request_times.append(time.monotonic())
                    count = outer._counts.get(directory, 0)
                    outer._counts[directory] = count + 1
                entry = outer.table.get(directory, {})
                if "attempts" in entry:
                    choices = entry["attempts"]
                    entry = choices[count] if count < len(choices) else choices[-1]
                if entry.get("sleep"):
                    time.sleep(entry["sleep"])
                if entry.get("fail"):
                    self.send_response(500)
                    self.end_headers()
                    return
                values = entry.get("files", []) if any(key.startswith("f") for key in body["questions"]) else entry
                answers = {}
                for key in body["questions"]:
                    if key.startswith("f"):
                        index = int(key[1:])
                        probability = values[index] if index < len(values) else 0
                    else:
                        probability = entry.get(key, 0)
                    answers[key] = {"type": "noul", "noul": probability}
                raw = json.dumps({"model": "typesafe/jev-1.13", "answers": answers}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    # Timed client requests are expected to close before a slow
                    # fake response is ready.
                    pass

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.server.server_port

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
