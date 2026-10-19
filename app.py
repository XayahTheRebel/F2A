"""Run Frameflow locally: python app.py. No files are saved or sent online."""

import argparse
from email import policy
from email.parser import BytesParser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import webbrowser

from PIL import features

from converter import ConversionError, MAX_FRAMES, MAX_INPUT_BYTES, Settings, encode_sequence

ROOT = Path(__file__).resolve().parent
STATIC = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
          "/style.css": ("style.css", "text/css"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}
# libwebp may use significant memory; only one conversion runs at a time.
ENCODER_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "Frameflow/1.0"

    def respond(self, status, body, content_type="application/json", extra_headers=None):
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, str(value))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def valid_host(self):
        # Reject DNS rebinding and requests from other web pages on the LAN.
        return self.headers.get("Host", "") == f"127.0.0.1:{self.server.server_port}"

    def do_GET(self):
        if not self.valid_host():
            self.respond(403, {"error": "请通过应用启动时显示的本机地址访问。"})
            return
        route = self.path.split("?", 1)[0]
        if route == "/api/health":
            self.respond(200, {"ok": True, "webp": features.check("webp")})
        elif route in STATIC:
            filename, mime = STATIC[route]
            self.respond(200, (ROOT / "static" / filename).read_bytes(), mime + "; charset=utf-8")
        else:
            self.respond(404, {"error": "没有找到这个页面。"})

    def do_POST(self):
        if not self.valid_host():
            self.respond(403, {"error": "不允许访问。"})
            return
        origin = self.headers.get("Origin")
        if origin != f"http://127.0.0.1:{self.server.server_port}":
            self.respond(403, {"error": "请在应用页面中发起转换。"})
            return
        if self.path == "/api/shutdown":
            if ENCODER_LOCK.locked():
                self.respond(409, {"error": "正在转换，请完成后再退出。"})
                return
            self.respond(200, {"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if self.path != "/api/convert":
            self.respond(404, {"error": "没有找到这个接口。"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.respond(400, {"error": "请求大小无效。"})
            return
        if not 0 < length <= MAX_INPUT_BYTES + 1024 * 1024:
            self.close_connection = True
            self.respond(413, {"error": "PNG 文件总大小不能超过 128 MiB。"})
            return
        if not ENCODER_LOCK.acquire(blocking=False):
            self.close_connection = True
            self.respond(409, {"error": "已有任务正在转换，请稍后重试。"})
            return
        try:
            content_type = self.headers.get("Content-Type", "")
            if not content_type.startswith("multipart/form-data;") or "\r" in content_type or "\n" in content_type:
                raise ConversionError("请使用文件表单上传 PNG 序列。")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ConversionError("图片数据没有传输完整，请重新转换。")
            message = BytesParser(policy=policy.default).parsebytes(
                f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + raw
            )
            del raw
            if not message.is_multipart() or message.defects:
                raise ConversionError("文件表单格式无效，请重新导入。")
            files, values = [], {}
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                if name == "frames":
                    files.append((part.get_filename() or "frame.png", part.get_payload(decode=True)))
                    if len(files) > MAX_FRAMES:
                        raise ConversionError(f"一次最多转换 {MAX_FRAMES} 帧。")
                elif name == "settings":
                    try:
                        values = json.loads(part.get_payload(decode=True))
                    except (json.JSONDecodeError, UnicodeDecodeError) as error:
                        raise ConversionError("转换设置格式不正确。") from error
            del message
            result, info = encode_sequence(files, Settings.from_dict(values))
            self.respond(200, result, "image/webp", {
                "X-Frame-Count": info["frames"], "X-Duration-Ms": info["duration"],
                "X-Image-Width": info["width"], "X-Image-Height": info["height"],
                "Content-Disposition": 'attachment; filename="animation.webp"',
            })
        except ConversionError as error:
            self.respond(400, {"error": str(error)})
        except MemoryError:
            self.respond(400, {"error": "可用内存不足，请减少帧数或降低输出比例。"})
        except Exception as error:
            print(f"Conversion failed: {type(error).__name__}: {error}")
            self.respond(500, {"error": "编码没有完成，请减少帧数后重试。"})
        finally:
            ENCODER_LOCK.release()


def main():
    parser = argparse.ArgumentParser(description="Frameflow · PNG 序列帧转动态 WebP")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not features.check("webp"):
        raise SystemExit("当前 Pillow 不支持 WebP，请执行 python -m pip install --upgrade Pillow。")
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError:
        # Double-clicking the launcher twice should still open a usable app.
        if args.port != 8765:
            raise
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    print(f"\n  Frameflow · PNG → WebP\n  http://127.0.0.1:{server.server_port}\n  Close this window or press Ctrl+C to exit.\n", flush=True)
    if not args.no_browser:
        threading.Timer(0.5, partial(webbrowser.open, f"http://127.0.0.1:{server.server_port}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
