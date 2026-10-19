"""PNG sequence conversion, independent of the local web interface."""

from dataclasses import dataclass
from io import BytesIO
import warnings

from PIL import Image, ImageCms, UnidentifiedImageError

MAX_FRAMES = 500
MAX_INPUT_BYTES = 128 * 1024 * 1024
MAX_DECODED_BYTES = 256 * 1024 * 1024
MAX_FRAME_PIXELS = 16_000_000


class ConversionError(ValueError):
    """A validation error that can be shown directly to the user."""


@dataclass(frozen=True)
class Settings:
    fps: int = 24
    quality: int = 85
    lossless: bool = False
    scale: int = 100
    loop: int = 0

    @classmethod
    def from_dict(cls, values):
        if not isinstance(values, dict):
            raise ConversionError("转换设置格式不正确。")
        limits = {"fps": (1, 60), "quality": (1, 100), "scale": (1, 100), "loop": (0, 65535)}
        parsed = {}
        defaults = cls()
        for key, (low, high) in limits.items():
            value = values.get(key, getattr(defaults, key))
            if type(value) is not int or not low <= value <= high:
                raise ConversionError(f"{key} 必须是 {low}–{high} 之间的整数。")
            parsed[key] = value
        lossless = values.get("lossless", False)
        if type(lossless) is not bool:
            raise ConversionError("无损压缩设置必须为布尔值。")
        return cls(**parsed, lossless=lossless)


def frame_durations(count: int, fps: int) -> list[int]:
    """Distribute rounding errors so 24/30/60 FPS does not accumulate drift."""
    return [round((i + 1) * 1000 / fps) - round(i * 1000 / fps) for i in range(count)]


def encode_sequence(files: list[tuple[str, bytes]], settings: Settings) -> tuple[bytes, dict]:
    if not files:
        raise ConversionError("请先导入 PNG 序列帧。")
    if len(files) > MAX_FRAMES:
        raise ConversionError(f"一次最多转换 {MAX_FRAMES} 帧。")
    if sum(len(data) for _, data in files) > MAX_INPUT_BYTES:
        raise ConversionError("PNG 文件总大小不能超过 128 MiB，请分批处理或缩小原图。")

    frames = []
    original_size = None
    decoded_bytes = 0
    try:
        for name, data in files:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(BytesIO(data)) as source:
                        if source.format != "PNG" or not name.lower().endswith(".png"):
                            raise ConversionError(f"「{name}」不是 PNG 图片。")
                        if getattr(source, "n_frames", 1) != 1:
                            raise ConversionError(f"「{name}」是 APNG，请使用单张 PNG 序列帧。")
                        width, height = source.size
                        if width * height > MAX_FRAME_PIXELS:
                            raise ConversionError(f"「{name}」超过 1600 万像素，请先缩小图片。")
                        if original_size is None:
                            original_size = source.size
                        elif source.size != original_size:
                            raise ConversionError(
                                f"「{name}」的尺寸为 {width} × {height}，"
                                f"请将所有帧统一为 {original_size[0]} × {original_size[1]}。"
                            )
                        target = tuple(max(1, round(n * settings.scale / 100)) for n in source.size)
                        if max(target) > 16383:
                            raise ConversionError("WebP 单边最大为 16383 像素，请降低输出比例。")
                        decoded_bytes += target[0] * target[1] * 4
                        if decoded_bytes + width * height * 4 > MAX_DECODED_BYTES:
                            raise ConversionError("序列帧解码后超过 256 MiB，请降低输出比例或减少帧数。")
                        frame = source.convert("RGBA")
                        try:
                            if profile := source.info.get("icc_profile"):
                                frame_with_profile = ImageCms.profileToProfile(
                                    frame, ImageCms.ImageCmsProfile(BytesIO(profile)),
                                    ImageCms.createProfile("sRGB"), outputMode="RGBA"
                                )
                                frame.close()
                                frame = frame_with_profile
                            if target != source.size:
                                resized = frame.resize(target, Image.Resampling.LANCZOS)
                                frame.close()
                                frame = resized
                            frames.append(frame)
                        except Exception:
                            frame.close()
                            raise
            except ConversionError:
                raise
            except (UnidentifiedImageError, OSError, SyntaxError, ValueError,
                    Image.DecompressionBombError, Image.DecompressionBombWarning, ImageCms.PyCMSError) as error:
                raise ConversionError(f"无法读取「{name}」，图片可能损坏或色彩配置无效。") from error

        durations = frame_durations(len(frames), settings.fps)
        output = BytesIO()
        frames[0].save(
            output, format="WEBP", save_all=True, append_images=frames[1:],
            duration=durations, loop=settings.loop, lossless=settings.lossless,
            quality=settings.quality if not settings.lossless else 80,
            method=4, background=(0, 0, 0, 0),
        )
        return output.getvalue(), {
            "width": frames[0].width, "height": frames[0].height,
            "frames": len(frames), "duration": sum(durations),
        }
    finally:
        for frame in frames:
            frame.close()
