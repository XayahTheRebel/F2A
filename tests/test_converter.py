from io import BytesIO
import json
from http.client import HTTPConnection
import threading
import unittest

from PIL import Image, ImageDraw

from app import Handler, ThreadingHTTPServer
from converter import ConversionError, Settings, encode_sequence, frame_durations


def png(index=0, size=(40, 32)):
    image = Image.new("RGBA", size)
    ImageDraw.Draw(image).rectangle((index * 8, 4, index * 8 + 6, 12), fill=(220, 70, 40, 128))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    image.close()
    return buffer.getvalue()


class ConverterTests(unittest.TestCase):
    def test_lossless_transparency_order_and_duration(self):
        files = [(f"frame_{i}.png", png(i)) for i in range(3)]
        data, info = encode_sequence(files, Settings(fps=24, lossless=True, loop=3))
        self.assertEqual(info, {"width": 40, "height": 32, "frames": 3, "duration": 125})
        with Image.open(BytesIO(data)) as result:
            self.assertEqual(result.n_frames, 3)
            self.assertEqual(result.info["loop"], 3)
            duration = 0
            for i, (_, original) in enumerate(files):
                result.seek(i)
                result.load()
                duration += result.info["duration"]
                with Image.open(BytesIO(original)) as source:
                    actual_pixels = result.convert("RGBA").load()
                    expected_pixels = source.load()
                    for y in range(source.height):
                        for x in range(source.width):
                            actual, expected = actual_pixels[x, y], expected_pixels[x, y]
                            self.assertEqual(actual[3], expected[3])
                            if expected[3]:
                                self.assertEqual(actual, expected)
                # Old opaque/semitransparent pixels must not leave trails.
                if i:
                    self.assertEqual(result.convert("RGBA").getpixel((1, 5))[3], 0)
            self.assertEqual(duration, 125)

    def test_no_accumulated_timing_drift(self):
        for fps in (12, 24, 30, 60):
            durations = frame_durations(240, fps)
            self.assertEqual(sum(durations), round(240_000 / fps))
            self.assertLessEqual(max(durations) - min(durations), 1)

    def test_lossy_scaled_single_image(self):
        data, info = encode_sequence([("一帧.png", png(size=(41, 33)))], Settings(scale=50))
        self.assertEqual((info["width"], info["height"]), (20, 16))
        with Image.open(BytesIO(data)) as result:
            self.assertEqual(result.format, "WEBP")
            self.assertEqual(result.size, (20, 16))
            self.assertEqual(result.convert("RGBA").getpixel((19, 15))[3], 0)

    def test_identical_frames_keep_total_duration(self):
        frames = [("a.png", png()), ("b.png", png()), ("c.png", png(1))]
        data, _ = encode_sequence(frames, Settings(fps=30, lossless=True, loop=1))
        with Image.open(BytesIO(data)) as result:
            self.assertEqual(result.info["loop"], 1)
            duration = 0
            for i in range(result.n_frames):
                result.seek(i); result.load()
                duration += result.info["duration"]
            self.assertEqual(duration, 100)

    def test_invalid_files_are_rejected(self):
        cases = [[], [("bad.png", b"not a png")], [("x.jpg", png())],
                 [("a.png", png()), ("b.png", png(size=(41, 32)))],
                 [("a.png", png())] * 501]
        for files in cases:
            with self.subTest(files=len(files)):
                with self.assertRaises(ConversionError):
                    encode_sequence(files, Settings())

    def test_apng_is_rejected(self):
        with Image.open(BytesIO(png())) as first, Image.open(BytesIO(png(1))) as second:
            buffer = BytesIO()
            first.save(buffer, format="PNG", save_all=True, append_images=[second], duration=100)
        with self.assertRaisesRegex(ConversionError, "APNG"):
            encode_sequence([("animated.png", buffer.getvalue())], Settings())

    def test_settings_validation(self):
        for options in ({"fps": 0}, {"fps": 61}, {"fps": True}, {"fps": 23.5}, {"fps": "24"},
                        {"quality": 101}, {"scale": 0}, {"loop": -1}, {"lossless": "false"}, []):
            with self.subTest(options=options), self.assertRaises(ConversionError):
                Settings.from_dict(options)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.port, timeout=10)
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        status, headers, data = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return status, headers, data

    def form(self):
        boundary = "frameflow-test-boundary"
        body = bytearray()
        options = json.dumps({"fps": 12, "lossless": True, "loop": 1}).encode()
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="settings"\r\n\r\n'.encode() + options + b"\r\n")
        for index in (2, 0, 1):
            body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="frames"; filename="{index}.png"\r\nContent-Type: image/png\r\n\r\n'.encode() + png(index) + b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())
        return bytes(body), {"Content-Type": f"multipart/form-data; boundary={boundary}", "Origin": f"http://127.0.0.1:{self.port}"}

    def test_static_and_health(self):
        status, headers, data = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Frameflow", data)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        status, _, data = self.request("GET", "/api/health")
        self.assertEqual(json.loads(data), {"ok": True, "webp": True})
        self.assertEqual(self.request("GET", "/../converter.py")[0], 404)

    def test_upload_preserves_the_selected_frame_order(self):
        body, headers = self.form()
        status, headers, data = self.request("POST", "/api/convert", body, headers)
        self.assertEqual(status, 200, data)
        self.assertEqual(headers["Content-Type"], "image/webp")
        self.assertEqual(headers["X-Duration-Ms"], "250")
        with Image.open(BytesIO(data)) as result:
            self.assertEqual(result.n_frames, 3)
            self.assertEqual(result.info["loop"], 1)
            self.assertEqual(result.convert("RGBA").getpixel((17, 5))[3], 128)

    def test_cross_origin_and_rebinding_are_rejected(self):
        body, headers = self.form()
        headers["Origin"] = "https://example.com"
        self.assertEqual(self.request("POST", "/api/convert", body, headers)[0], 403)
        self.assertEqual(self.request("GET", "/", headers={"Host": "evil.example"})[0], 403)

    def test_malformed_input_has_a_readable_error(self):
        status, _, data = self.request("POST", "/api/convert", b"oops", {
            "Content-Type": "text/plain", "Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))


if __name__ == "__main__":
    unittest.main()
