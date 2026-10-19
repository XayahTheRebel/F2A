"""Launch an isolated source/packaged server and clean up its process tree."""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, help="Test a packaged executable instead of source")
    args = parser.parse_args()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    command = [str(args.exe.resolve())] if args.exe else [sys.executable, str(ROOT / "app.py")]
    command += ["--port", str(port), "--no-browser"]
    output = ROOT / "test-results"
    output.mkdir(exist_ok=True)
    log_path = output / ("exe-server.log" if args.exe else "source-server.log")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with log_path.open("w", encoding="utf-8") as log:
        server = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=log, creationflags=flags)
        try:
            url = f"http://127.0.0.1:{port}"
            for _ in range(200):
                if server.poll() is not None:
                    raise RuntimeError(f"Server exited: {log_path.read_text(encoding='utf-8')}")
                try:
                    with urlopen(url + "/api/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except (URLError, TimeoutError, ConnectionError):
                    time.sleep(0.1)
            else:
                raise RuntimeError("Server did not become ready")
            # Verify the executable bundles the exact files that were reviewed.
            for route in ("index.html", "app.js", "style.css", "favicon.svg"):
                with urlopen(url + ("/" if route == "index.html" else "/" + route), timeout=5) as response:
                    assert response.read() == (ROOT / "static" / route).read_bytes(), f"Outdated asset: {route}"
            environment = dict(os.environ, FRAMEFLOW_TEST_URL=url)
            result = subprocess.run([sys.executable, str(ROOT / "tests" / "browser_check.py")], cwd=ROOT, env=environment)
            if result.returncode:
                raise RuntimeError(f"Browser check failed. Server log: {log_path.read_text(encoding='utf-8')}")
        finally:
            try:
                request = Request(url + "/api/shutdown", data=b"", headers={"Origin": url}, method="POST")
                with urlopen(request, timeout=2):
                    pass
            except (URLError, TimeoutError, ConnectionError):
                pass
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.terminate()
                server.wait(timeout=5)
    print("Packaged application verified." if args.exe else "Source application verified.")


if __name__ == "__main__":
    main()
