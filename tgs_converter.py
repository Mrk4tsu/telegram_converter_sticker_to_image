import os
import sys
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


def clr(text, color):   return f"{color}{text}{RESET}"
def ok(msg):            print(clr(f"  [OK] {msg}", GREEN))
def err(msg):           print(clr(f"  [!!] {msg}", RED))
def info(msg):          print(clr(f"  --> {msg}", CYAN))
def step(n, msg):       print(f"\n{clr(f'[{n}]', YELLOW)} {WHITE}{msg}{RESET}")
def hr():               print(clr("  " + "-" * 50, GRAY))

def header():
    print()
    print(clr("=" * 52, CYAN))
    print(clr("  TGS -> GIF / WebP Converter  v3", BOLD))
    print(clr("=" * 52, CYAN))

def fmt_size(n_bytes):
    if n_bytes < 1024:      return f"{n_bytes} B"
    if n_bytes < 1024**2:   return f"{n_bytes/1024:.1f} KB"
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


def get_frames(tgs_path: Path, width: int, height: int, target_fps: int):
    """
    Render TGS ra frames va tinh duration chinh xac.

    KEY FIX:
      - Lay source_fps TU FILE GOC (khong dung fps nguoi dung nhap de tinh duration).
      - target_fps chi dung de SKIP FRAME neu muon giam so frame.
      - duration_ms luon tinh dua tren so frame thuc su output.

    Vi sao file goc bi nhanh hon:
      Code cu: duration = 1000 / target_fps (vi du 20fps => 50ms/frame)
               nhung render du 60 frames => tong thoi gian = 60 * 50ms = 3000ms (sai)
      Code moi: lay source_fps = 60, duration = 1000/60 = 16ms/frame
               render du 60 frames => tong = 60 * 16ms = 1000ms (dung)
    """
    anim = LottieAnimation.from_tgs(str(tgs_path))
    total_frames = anim.lottie_animation_get_totalframe()
    source_fps   = anim.lottie_animation_get_framerate()

    if source_fps <= 0:
        source_fps = 60.0

    if target_fps <= 0 or target_fps >= source_fps:
        # Giu nguyen toan bo frame, duration theo FPS goc
        duration_ms = int(round(1000.0 / source_fps))
        frame_indices = list(range(0, total_frames))
    else:
        # Skip frame de dat target_fps
        skip = int(round(source_fps / target_fps))
        skip = max(1, skip)
        # Duration tinh theo so frame thuc su (source_fps / skip)
        actual_fps = source_fps / skip
        duration_ms = int(round(1000.0 / actual_fps))
        frame_indices = list(range(0, total_frames, skip))

    # GIF toi thieu 20ms/frame (gioi han cua dinh dang GIF)
    duration_ms = max(duration_ms, 20)

    frames = []
    for i in frame_indices:
        frame = anim.render_pillow_frame(i, width=width, height=height)
        frames.append(frame)

    anim.lottie_animation_destroy()
    return frames, duration_ms, round(source_fps)


def save_gif(frames, out_path: Path, duration_ms: int):
    if not frames:
        raise ValueError("Khong co frames")
    frames[0].save(
        out_path,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        loop=0,
        duration=duration_ms,
        disposal=2,
    )


def save_webp(frames, out_path: Path, duration_ms: int, quality: int = 85):
    if not frames:
        raise ValueError("Khong co frames")
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


def convert_one(tgs_path: Path, out_path: Path, size: int, target_fps: int, fmt: str, quality: int = 85):
    try:
        frames, duration_ms, source_fps = get_frames(tgs_path, size, size, target_fps)
        if not frames:
            return False, 0, 0
        if fmt == "GIF":
            save_gif(frames, out_path, duration_ms)
        else:
            save_webp(frames, out_path, duration_ms, quality)
        ok_flag = out_path.exists() and out_path.stat().st_size > 0
        return ok_flag, source_fps, duration_ms
    except Exception as e:
        err(f"Loi: {e}")
        return False, 0, 0


def main():
    os.system("")
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

    step(4, "Giam FPS? (0 = giu nguyen FPS goc cua tung file):")
    info("Vi du: file goc 60fps, nhap 20 => chi lay 1/3 so frame, toc do van dung")
    info("Khuyen nghi: nhap 0 de dam bao toc do chinh xac nhat")
    target_fps = prompt_int("Target FPS (0 = goc)", 0, 0, 120)
    if target_fps == 0:
        ok("Se giu nguyen FPS goc cua tung file")
    else:
        ok(f"Target FPS: {target_fps} (se skip frame neu file goc cao hon)")

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

    fps_label = f"{target_fps}fps" if target_fps > 0 else "srcfps"
    if ch == "2":
        raw = input("  Duong dan output > ").strip().strip('"').strip("'")
        output_dir = Path(raw)
    else:
        output_dir = input_dir / f"output_{fmt.lower()}_{out_size}px_{fps_label}"

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

        ok_flag, src_fps, dur_ms = convert_one(tgs, out_file, out_size, target_fps, fmt, quality)

        if ok_flag:
            size_str = fmt_size(out_file.stat().st_size)
            print(clr(f"OK  ({size_str}, src={src_fps}fps, {dur_ms}ms/frame)", GREEN))
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
