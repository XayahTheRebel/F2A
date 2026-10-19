"""Real browser checks. Run against app.py on port 8766; outputs stay ignored."""
from io import BytesIO
import os
import re
from pathlib import Path
import sys

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
OUTPUT = Path(__file__).resolve().parents[1] / "test-results"
OUTPUT.mkdir(exist_ok=True)


def fixture(name, index, size=(96, 80)):
    image = Image.new("RGBA", size)
    ImageDraw.Draw(image).rectangle((index * 15, 10, index * 15 + 10, 35), fill=(230, 90, 60, 255))
    data = BytesIO(); image.save(data, format="PNG"); image.close()
    return {"name": name, "mimeType": "image/png", "buffer": data.getvalue()}


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(os.environ.get("FRAMEFLOW_TEST_URL", "http://127.0.0.1:8766"))
    page.wait_for_load_state("networkidle")
    expect(page.locator("#export")).to_be_disabled()
    page.screenshot(path=str(OUTPUT / "desktop-empty.png"), full_page=True)

    page.locator("#demo-button").click()
    expect(page.locator("#frame-count")).to_have_text("24")
    expect(page.locator("#export")).to_be_enabled()
    page.get_by_role("button", name="暂停动画", exact=True).click()
    expect(page.locator("#output-duration")).to_have_text("24 帧 / 1.00 s")
    page.locator("#lossless").click()
    expect(page.locator("#quality")).to_be_disabled()
    page.locator('[data-fps="12"]').click()
    page.locator("#scale").select_option("50")
    page.locator("#loop").select_option("1")
    page.locator("#filename").fill("跳舞示例.webp")
    expect(page.locator("#output-dimensions")).to_have_text("128 × 128")
    page.locator("#export").click()
    expect(page.locator("#result-card")).to_be_visible(timeout=30000)
    expect(page.locator("#result-tab")).to_have_attribute("aria-pressed", "true")
    with page.expect_download() as download_info:
        page.locator("#download").click()
    download = download_info.value
    assert download.suggested_filename == "跳舞示例.webp"
    destination = OUTPUT / "demo.webp"
    download.save_as(str(destination))
    with Image.open(destination) as result:
        assert result.size == (128, 128)
        assert result.n_frames == 24
        assert result.info["loop"] == 1
        durations = []
        for i in range(result.n_frames):
            result.seek(i); result.load(); durations.append(result.info["duration"])
        assert sum(durations) == 2000
        assert result.convert("RGBA").getpixel((0, 0))[3] == 0
    page.screenshot(path=str(OUTPUT / "desktop-result.png"), full_page=True)
    page.locator("#fps").fill("30")
    expect(page.locator("#result-card")).to_be_hidden()
    expect(page.locator("#result-tab")).to_be_disabled()
    page.locator("#clear").click()
    expect(page.locator("#export")).to_be_disabled()

    page.locator("#file-input").set_input_files([
        fixture("frame_10.png", 2), fixture("frame_2.png", 1), fixture("frame_1.png", 0)])
    expect(page.locator("#frame-count")).to_have_text("3")
    items = page.locator(".frame-item")
    assert [items.nth(i).get_attribute("title") for i in range(3)] == ["frame_1.png", "frame_2.png", "frame_10.png"]
    page.locator("#reverse").click()
    expect(items.nth(0)).to_have_attribute("title", "frame_10.png")
    page.locator("#move-right").click()
    expect(items.nth(1)).to_have_attribute("title", "frame_10.png")
    page.locator("#sort").click()
    expect(items.nth(0)).to_have_attribute("title", "frame_1.png")
    items.nth(0).drag_to(items.nth(2))
    expect(items.nth(2)).to_have_attribute("title", "frame_1.png")
    page.locator("#remove").click()
    expect(page.locator("#frame-count")).to_have_text("2")
    page.locator("#file-input").set_input_files(fixture("wrong_size.png", 0, (80, 80)))
    expect(page.locator("#message")).to_contain_text("统一")
    expect(page.locator("#frame-count")).to_have_text("2")
    page.locator("#file-input").set_input_files({"name": "broken.png", "mimeType": "image/png", "buffer": b"not a png"})
    expect(page.locator("#message")).to_contain_text("不是有效")
    expect(page.locator("#frame-count")).to_have_text("2")
    page.locator("#fps").fill("0")
    expect(page.locator("#export")).to_be_disabled()
    page.locator("#fps").fill("60")
    expect(page.locator("#export")).to_be_enabled()
    page.locator("#lossy").click()
    expect(page.locator("#quality")).to_be_enabled()
    page.locator("#export").click()
    expect(page.locator("#result-card")).to_be_visible(timeout=30000)

    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(OUTPUT / "mobile-result.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile horizontal overflow"
    page.locator("#source-tab").click()
    page.locator("#clear").click()
    page.locator("#file-input").set_input_files(fixture("single.png", 0))
    expect(page.locator("#frame-count")).to_have_text("1")
    page.locator("#export").click()
    expect(page.locator("#result-card")).to_be_visible(timeout=30000)
    expect(page.locator("#message")).to_contain_text("静态")
    page.locator("#quit").click()
    expect(page.locator(".local-badge")).to_have_text("应用已退出")
    expect(page.locator("#export")).to_be_disabled()
    expect(page.locator("#download")).to_have_attribute("href", re.compile(r"blob:.+"))
    assert not errors, errors
    browser.close()
    print("Browser checks passed: demo, exports, alpha, durations, natural sort, reorder, validation, mobile, single frame.")
