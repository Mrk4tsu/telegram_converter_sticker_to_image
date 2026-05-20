import os
import sys
import asyncio
from pathlib import Path

def check_deps():
    missing = []
    try:
        import pyrlottie
    except ImportError:
        missing.append("pyrlottie")
    try:
        from PIL import Image
    except ImportError:
        missing.append("Pillow")

    if missing:
        print("\n❌  Thiếu thư viện:")
        for lib in missing:
            print(f"     pip install {lib}")
        print()
        sys.exit(1)

check_deps()

from pyrlottie import (
    LottieFile,
    FileMap,
    convSingleLottie,
    convMultLottie,
)
from PIL import Image
import asyncio


# ─── Màu ANSI console ────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
GRAY   = "\033[90m"
WHITE  = "\033[97m"

def clr(text, color): return f"{color}{text}{RESET}"
def ok(msg):    print(clr(f"  ✓ {msg}", GREEN))
def err(msg):   print(clr(f"  ✗ {msg}", RED))
def info(msg):  print(clr(f"  → {msg}", CYAN))
def step(n, msg): print(f"\n{clr(f'[{n}]', YELLOW)} {WHITE}{msg}{RESET}")
def hr(): print(clr("  " + "─" * 50, GRAY))


def header():
    print()
    print(clr("╔══════════════════════════════════════════════════╗", CYAN))
    print(clr("║", CYAN) + clr("  TGS → GIF / WebP Converter  (pyrlottie)  ", BOLD) + clr("  ║", CYAN))
    print(clr("╚══════════════════════════════════════════════════╝", CYAN))


def fmt_size(n_bytes: int) -> str:
    if n_bytes < 1024: return f"{n_bytes} B"
    if n_bytes < 1024**2: return f"{n_bytes/1024:.1f} KB"
    return f"{n_bytes/1024**2:.2f} MB"


def prompt(msg: str, default: str = "") -> str:
    """Nhập có default, Enter = dùng default."""
    hint = f" [{default}]" if default else ""
    val = input(clr(f"  {msg}{hint} > ", WHITE)).strip()
    return val if val else default


def prompt_dir(msg: str) -> Path:
    """Nhập đường dẫn thư mục hợp lệ."""
    while True:
        raw = input(clr(f"  {msg} > ", WHITE)).strip().strip('"').strip("'")
        p = Path(raw)
        if p.is_dir():
            return p
        err(f"Thư mục không tồn tại: {raw}")


def prompt_float(msg: str, default: float, lo: float, hi: float) -> float:
    while True:
        raw = prompt(msg, str(default))
        try:
            val = float(raw)
            if lo <= val <= hi:
                return val
            err(f"Vui lòng nhập số từ {lo} đến {hi}")
        except ValueError:
            err("Nhập số hợp lệ")


def prompt_int(msg: str, default: int, lo: int, hi: int) -> int:
    while True:
        raw = prompt(msg, str(default))
        try:
            val = int(raw)
            if lo <= val <= hi:
                return val
            err(f"Vui lòng nhập số từ {lo} đến {hi}")
        except ValueError:
            err("Nhập số nguyên hợp lệ")


def prompt_choice(msg: str, choices: list[str], default: str) -> str:
    opts = "/".join(choices)
    while True:
        raw = prompt(f"{msg} ({opts})", default).upper()
        if raw in [c.upper() for c in choices]:
            return raw
        err(f"Chọn một trong: {opts}")


def resize_frames(frames: list, size: tuple[int, int]) -> list:
    """Resize list PIL Image frames về size (w, h)."""
    resized = []
    for frame in frames:
        resized.append(frame.resize(size, Image.LANCZOS))
    return resized


def save_gif(frames: list, out_path: Path, fps: int):
    if not frames:
        raise ValueError("Không có frames để lưu")

    duration_ms = int(1000 / fps)

    # GIF cần chuyển sang palette mode
    gif_frames = []
    for frame in frames:
        # Giữ transparency
        if frame.mode == "RGBA":
            gif_frame = frame.convert("RGBA")
        else:
            gif_frame = frame.convert("RGBA")
        gif_frames.append(gif_frame)

    gif_frames[0].save(
        out_path,
        format="GIF",
        save_all=True,
        append_images=gif_frames[1:],
        loop=0,
        duration=duration_ms,
        disposal=2,
    )


def save_webp(frames: list, out_path: Path, fps: int, quality: int = 85):
    if not frames:
        raise ValueError("Không có frames để lưu")

    duration_ms = int(1000 / fps)

    frames[0].save(
        out_path,
        format="WEBP",
        save_all=True,
        append_images=frames[1:],
        loop=0,
        duration=duration_ms,
        quality=quality,
        method=4,
    )


async def convert_one(
    tgs_path: Path,
    out_path: Path,
    size: int,
    fps: int,
    fmt: str,          # "GIF" hoặc "WEBP"
    quality: int = 85,
) -> bool:
    try:
        lottie_file = LottieFile(str(tgs_path))

        # pyrlottie render ra frames (PIL Images) với kích thước gốc
        # convSingleLottieFrames trả về LottieFrames có .frames
        from pyrlottie import convSingleLottieFrames
        result = await convSingleLottieFrames(lottie_file)

        frames: list = result.frames  # list[PIL.Image.Image]

        if not frames:
            return False

        # Resize
        target = (size, size)
        if frames[0].size != target:
            frames = resize_frames(frames, target)

        # Save
        if fmt == "GIF":
            save_gif(frames, out_path, fps)
        else:
            save_webp(frames, out_path, fps, quality)

        return out_path.exists() and out_path.stat().st_size > 0

    except Exception as e:
        err(f"  Lỗi nội bộ: {e}")
        return False


# ─── Main ────────────────────────────────────────────────────────────────────
async def main():
    os.system("")  # Bật ANSI trên Windows
    header()

    step(1, "Thư mục chứa file .tgs:")
    input_dir = prompt_dir("Đường dẫn")

    tgs_files = sorted(input_dir.glob("*.tgs"))
    if not tgs_files:
        err("Không tìm thấy file .tgs nào trong thư mục này.")
        return
    ok(f"Tìm thấy {len(tgs_files)} file .tgs")

    step(2, "Format output:")
    fmt = prompt_choice("Chọn format", ["GIF", "WEBP"], "GIF")
    ok(f"Format: {fmt}")

    step(3, "Resize theo % (100 = 512x512 gốc, 50 = 256x256):")
    pct = prompt_float("% kích thước", 100.0, 1.0, 500.0)
    base_size = 512
    out_size = max(8, int(round(base_size * pct / 100)))
    if out_size % 2 != 0:
        out_size += 1  # Làm chẵn cho codec
    ok(f"Kích thước output: {out_size}x{out_size} px ({pct}% của {base_size}x{base_size})")

    step(4, "Frame rate (FPS):")
    default_fps = 50 if fmt == "GIF" else 60
    fps = prompt_int("FPS", default_fps, 1, 120)
    ok(f"FPS: {fps}")

    quality = 85
    if fmt == "WEBP":
        step(5, "Chất lượng WebP (1–100):")
        quality = prompt_int("Quality", 85, 1, 100)
        ok(f"Quality: {quality}")
    else:
        step(5, "(Bỏ qua quality — không áp dụng cho GIF)")

    step(6, "Thư mục output:")
    print(f"     {clr('[1]', YELLOW)} Tự tạo thư mục con trong thư mục TGS")
    print(f"     {clr('[2]', YELLOW)} Nhập đường dẫn tùy chỉnh")
    ch = prompt_choice("Lựa chọn", ["1", "2"], "1")

    if ch == "2":
        raw = input(clr("  Đường dẫn output > ", WHITE)).strip().strip('"').strip("'")
        output_dir = Path(raw)
    else:
        output_dir = input_dir / f"output_{fmt.lower()}_{out_size}px"

    output_dir.mkdir(parents=True, exist_ok=True)
    ok(f"Output: {output_dir}")

    hr()
    step(7, f"Bắt đầu convert {len(tgs_files)} file...\n")

    ext = fmt.lower()
    success, failed = 0, 0

    for i, tgs in enumerate(tgs_files, 1):
        name = tgs.stem
        out_file = output_dir / f"{name}.{ext}"

        # Progress indicator
        sys.stdout.write(f"  [{i}/{len(tgs_files)}] {clr(name, WHITE)}.tgs ... ")
        sys.stdout.flush()

        ok_flag = await convert_one(tgs, out_file, out_size, fps, fmt, quality)

        if ok_flag:
            size_str = fmt_size(out_file.stat().st_size)
            print(clr(f"OK  ({size_str})", GREEN))
            success += 1
        else:
            print(clr("FAILED", RED))
            failed += 1

    print()
    hr()
    print(f"\n  {clr('Hoàn thành!', CYAN)}  "
          f"Thành công: {clr(str(success), GREEN)}  |  "
          f"Thất bại: {clr(str(failed), RED)}")
    info(f"Output: {output_dir}")
    print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(clr("\n\n  Đã hủy.", GRAY))
