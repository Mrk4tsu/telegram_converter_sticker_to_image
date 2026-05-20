import os
import sys
import asyncio
from pathlib import Path


def check_deps():
    missing = []
    try:
        import rlottie_python
    except ImportError:
        missing.append("rlottie-python")
    try:
        from PIL import Image
    except ImportError:
        missing.append("Pillow")
    if missing:
        print("\nThieu thu vien, chay lenh sau de cai:")
        for lib in missing:
            print(f"  pip install {lib}")
        print()
        sys.exit(1)


check_deps()

from rlottie_python import LottieAnimation
from PIL import Image

RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
GRAY   = "\033[90m"
WHITE  = "\033[97m"


def clr(text, color):
    return f"{color}{text}{RESET}"

def ok(msg):    print(clr(f"  [OK] {msg}", GREEN))
def err(msg):   print(clr(f"  [!!] {msg}", RED))
def info(msg):  print(clr(f"  --> {msg}", CYAN))
def step(n, msg): print(f"\n{clr(f'[{n}]', YELLOW)} {WHITE}{msg}{RESET}")
def hr(): print(clr("  " + "-" * 50, GRAY))

def header():
    print()
    print(clr("=" * 52, CYAN))
    print(clr("  TGS -> GIF / WebP Converter  (rlottie-python)", BOLD))
    print(clr("=" * 52, CYAN))

def fmt_size(n_bytes):
    if n_bytes < 1024: return f"{n_bytes} B"
    if n_bytes < 1024**2: return f"{n_bytes/1024:.1f} KB"
    return f"{n_bytes/1024**2:.2f} MB"

def prompt(msg, default=""):
    hint = f" [{default}]" if default else ""
    val = input(f"  {msg}{hint} > ").strip()
    return val if val else default

def prompt_dir(msg):
    while True:
        raw = input(f"  {msg} > ").strip().strip('"').strip("'")
        p = Path(raw)
        if p.is_dir():
            return p
        err(f"Thu muc khong ton tai: {raw}")

def prompt_float(msg, default, lo, hi):
    while True:
        raw = prompt(msg, str(default))
        try:
            val = float(raw)
            if lo <= val <= hi:
                return val
            err(f"Nhap so tu {lo} den {hi}")
        except ValueError:
            err("Nhap so hop le")

def prompt_int(msg, default, lo, hi):
    while True:
        raw = prompt(msg, str(default))
        try:
            val = int(raw)
            if lo <= val <= hi:
                return val
            err(f"Nhap so tu {lo} den {hi}")
        except ValueError:
            err("Nhap so nguyen hop le")

def prompt_choice(msg, choices, default):
    opts = "/".join(choices)
    while True:
        raw = prompt(f"{msg} ({opts})", default).upper()
        if raw in [c.upper() for c in choices]:
            return raw
        err(f"Chon mot trong: {opts}")


def get_frames(tgs_path: Path, width: int, height: int):
    """Render TGS ra list Pillow RGBA Images."""
    anim = LottieAnimation.from_tgs(str(tgs_path))
    frame_count = anim.lottie_animation_get_totalframe()
    frames = []
    for i in range(frame_count):
        frame = anim.render_pillow_frame(i, width=width, height=height)
        frames.append(frame)
    anim.lottie_animation_destroy()
    return frames


def save_gif(frames, out_path: Path, fps: int):
    if not frames:
        raise ValueError("Khong co frames")
    duration_ms = int(1000 / fps)
    frames[0].save(
        out_path,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        loop=0,
        duration=duration_ms,
        disposal=2,
    )


def save_webp(frames, out_path: Path, fps: int, quality: int = 85):
    if not frames:
        raise ValueError("Khong co frames")
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


def convert_one(tgs_path: Path, out_path: Path, size: int, fps: int, fmt: str, quality: int = 85):
    try:
        frames = get_frames(tgs_path, size, size)
        if not frames:
            return False
        if fmt == "GIF":
            save_gif(frames, out_path, fps)
        else:
            save_webp(frames, out_path, fps, quality)
        return out_path.exists() and out_path.stat().st_size > 0
    except Exception as e:
        err(f"Loi: {e}")
        return False


def main():
    os.system("")  # bat ANSI Windows
    header()

    step(1, "Thu muc chua file .tgs:")
    input_dir = prompt_dir("Duong dan")

    tgs_files = sorted(input_dir.glob("*.tgs"))
    if not tgs_files:
        err("Khong tim thay file .tgs nao.")
        return
    ok(f"Tim thay {len(tgs_files)} file .tgs")

    step(2, "Format output:")
    fmt = prompt_choice("Chon format", ["GIF", "WEBP"], "GIF")
    ok(f"Format: {fmt}")

    step(3, "Resize theo % (100 = 512x512 goc, 50 = 256x256):")
    pct = prompt_float("% kich thuoc", 100.0, 1.0, 500.0)
    base_size = 512
    out_size = max(8, int(round(base_size * pct / 100)))
    if out_size % 2 != 0:
        out_size += 1
    ok(f"Kich thuoc output: {out_size}x{out_size} px")

    step(4, "Frame rate (FPS):")
    default_fps = 50 if fmt == "GIF" else 60
    fps = prompt_int("FPS", default_fps, 1, 120)
    ok(f"FPS: {fps}")

    quality = 85
    if fmt == "WEBP":
        step(5, "Chat luong WebP (1-100):")
        quality = prompt_int("Quality", 85, 1, 100)
        ok(f"Quality: {quality}")
    else:
        step(5, "(Bo qua quality - khong ap dung cho GIF)")

    step(6, "Thu muc output:")
    print("     [1] Tu tao thu muc con trong thu muc TGS")
    print("     [2] Nhap duong dan tuy chinh")
    ch = prompt_choice("Lua chon", ["1", "2"], "1")

    if ch == "2":
        raw = input("  Duong dan output > ").strip().strip('"').strip("'")
        output_dir = Path(raw)
    else:
        output_dir = input_dir / f"output_{fmt.lower()}_{out_size}px"

    output_dir.mkdir(parents=True, exist_ok=True)
    ok(f"Output: {output_dir}")

    hr()
    step(7, f"Bat dau convert {len(tgs_files)} file...\n")

    ext = fmt.lower()
    success, failed = 0, 0

    for i, tgs in enumerate(tgs_files, 1):
        name = tgs.stem
        out_file = output_dir / f"{name}.{ext}"

        sys.stdout.write(f"  [{i}/{len(tgs_files)}] {name}.tgs ... ")
        sys.stdout.flush()

        ok_flag = convert_one(tgs, out_file, out_size, fps, fmt, quality)

        if ok_flag:
            size_str = fmt_size(out_file.stat().st_size)
            print(clr(f"OK  ({size_str})", GREEN))
            success += 1
        else:
            print(clr("FAILED", RED))
            failed += 1

    print()
    hr()
    print(f"\n  Hoan thanh!  Thanh cong: {success}  |  That bai: {failed}")
    info(f"Output: {output_dir}")
    print()
    input("  Nhan Enter de thoat...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Da huy.")
