import os
import sys
import subprocess
import shutil
from pathlib import Path


# ── Tim ffmpeg: uu tien cung thu muc exe, sau do PATH ────────────────────────
def find_ffmpeg() -> str | None:
    """
    Thu tu tim ffmpeg:
      1. Cung thu muc voi file .exe (khi build PyInstaller --onefile)
      2. Cung thu muc voi script .py (khi chay truc tiep)
      3. PATH he thong
    """
    # Khi PyInstaller --onefile chay, file duoc giai nen vao thu muc tam _MEIPASS
    # nhung ban than exe nam o sys.executable
    candidates = []

    # Thu muc cua exe / script
    exe_dir = Path(sys.executable).parent
    candidates.append(exe_dir / "ffmpeg.exe")
    candidates.append(exe_dir / "ffmpeg")

    # Thu muc cua script (khi chay truc tiep bang python)
    if getattr(sys, "frozen", False):
        # Dang chay tu PyInstaller bundle
        bundle_dir = Path(sys._MEIPASS)
        candidates.append(bundle_dir / "ffmpeg.exe")
        candidates.append(bundle_dir / "ffmpeg")
    else:
        # Dang chay truc tiep
        script_dir = Path(__file__).parent
        candidates.append(script_dir / "ffmpeg.exe")
        candidates.append(script_dir / "ffmpeg")

    for p in candidates:
        if p.exists():
            return str(p)

    # Cuoi cung: tim trong PATH he thong
    return shutil.which("ffmpeg")


def find_ffprobe() -> str | None:
    """Tim ffprobe tuong tu ffmpeg."""
    candidates = []

    exe_dir = Path(sys.executable).parent
    candidates.append(exe_dir / "ffprobe.exe")
    candidates.append(exe_dir / "ffprobe")

    if getattr(sys, "frozen", False):
        bundle_dir = Path(sys._MEIPASS)
        candidates.append(bundle_dir / "ffprobe.exe")
        candidates.append(bundle_dir / "ffprobe")
    else:
        script_dir = Path(__file__).parent
        candidates.append(script_dir / "ffprobe.exe")
        candidates.append(script_dir / "ffprobe")

    for p in candidates:
        if p.exists():
            return str(p)

    return shutil.which("ffprobe")


# ── Check deps ────────────────────────────────────────────────────────────────
def check_deps():
    missing_pip = []
    try:
        import rlottie_python
    except ImportError:
        missing_pip.append("rlottie-python")
    try:
        from PIL import Image
    except ImportError:
        missing_pip.append("Pillow")

    if missing_pip:
        print("\nThieu thu vien Python:")
        for lib in missing_pip:
            print(f"  pip install {lib}")
        print()
        sys.exit(1)


check_deps()

from rlottie_python import LottieAnimation
from PIL import Image

# Tim ffmpeg sau khi check deps
FFMPEG  = find_ffmpeg()
FFPROBE = find_ffprobe()
HAS_FFMPEG = FFMPEG is not None

RESET   = "\033[0m"
BOLD    = "\033[1m"
CYAN    = "\033[96m"
GREEN   = "\033[92m"
RED     = "\033[91m"
YELLOW  = "\033[93m"
GRAY    = "\033[90m"
WHITE   = "\033[97m"
MAGENTA = "\033[95m"


def clr(text, color):   return f"{color}{text}{RESET}"
def ok(msg):            print(clr(f"  [OK] {msg}", GREEN))
def err(msg):           print(clr(f"  [!!] {msg}", RED))
def info(msg):          print(clr(f"  --> {msg}", CYAN))
def warn(msg):          print(clr(f"  [!]  {msg}", YELLOW))
def step(n, msg):       print(f"\n{clr(f'[{n}]', YELLOW)} {WHITE}{msg}{RESET}")
def hr():               print(clr("  " + "-" * 54, GRAY))

def header():
    print()
    print(clr("=" * 56, CYAN))
    print(clr("  TGS + WebM Sticker Converter  v5", BOLD))
    print(clr("  .tgs -> GIF/WebP  |  .webm -> GIF/WebP", GRAY))
    print(clr("=" * 56, CYAN))

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


# ── Probe WebM ────────────────────────────────────────────────────────────────
def probe_webm(path: Path):
    if not FFPROBE:
        return 512, 512, 30.0, False
    try:
        import json
        result = subprocess.run(
            [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_streams", str(path)],
            capture_output=True, text=True
        )
        data = json.loads(result.stdout)
        s = data["streams"][0]
        w = s["width"]
        h = s["height"]
        fps_raw = s.get("r_frame_rate", "30/1")
        num, den = fps_raw.split("/")
        fps = round(int(num) / max(int(den), 1), 2)
        has_alpha = s.get("tags", {}).get("alpha_mode", "0") == "1"
        return w, h, fps, has_alpha
    except Exception:
        return 512, 512, 30.0, False


# ── Convert WebM -> GIF ───────────────────────────────────────────────────────
def convert_webm_to_gif(src: Path, dst: Path, size: int) -> bool:
    palette = dst.with_suffix(".palette.png")
    try:
        r1 = subprocess.run([
            FFMPEG, "-y", "-i", str(src),
            "-vf", f"scale={size}:{size}:flags=lanczos,palettegen=reserve_transparent=1",
            str(palette)
        ], capture_output=True)
        if r1.returncode != 0:
            return False

        r2 = subprocess.run([
            FFMPEG, "-y",
            "-i", str(src),
            "-i", str(palette),
            "-lavfi", f"scale={size}:{size}:flags=lanczos [x]; [x][1:v] paletteuse=alpha_threshold=128",
            str(dst)
        ], capture_output=True)
        return r2.returncode == 0 and dst.exists() and dst.stat().st_size > 0
    finally:
        palette.unlink(missing_ok=True)


# ── Convert WebM -> WebP animated ────────────────────────────────────────────
def convert_webm_to_webp(src: Path, dst: Path, size: int, quality: int = 85) -> bool:
    r = subprocess.run([
        FFMPEG, "-y", "-i", str(src),
        "-vf", f"scale={size}:{size}:flags=lanczos",
        "-vcodec", "libwebp",
        "-lossless", "0",
        "-quality", str(quality),
        "-loop", "0",
        "-preset", "default",
        "-an",
        str(dst)
    ], capture_output=True)
    return r.returncode == 0 and dst.exists() and dst.stat().st_size > 0


# ── Convert TGS ──────────────────────────────────────────────────────────────
def get_tgs_frames(tgs_path: Path, width: int, height: int, target_fps: int):
    anim = LottieAnimation.from_tgs(str(tgs_path))
    total_frames = anim.lottie_animation_get_totalframe()
    source_fps   = anim.lottie_animation_get_framerate()
    if source_fps <= 0:
        source_fps = 60.0

    if target_fps <= 0 or target_fps >= source_fps:
        duration_ms = int(round(1000.0 / source_fps))
        indices = list(range(0, total_frames))
    else:
        skip = max(1, int(round(source_fps / target_fps)))
        actual_fps = source_fps / skip
        duration_ms = int(round(1000.0 / actual_fps))
        indices = list(range(0, total_frames, skip))

    duration_ms = max(duration_ms, 20)
    frames = [anim.render_pillow_frame(i, width=width, height=height) for i in indices]
    anim.lottie_animation_destroy()
    return frames, duration_ms, round(source_fps)


def save_gif(frames, out_path: Path, duration_ms: int):
    frames[0].save(
        out_path, format="GIF", save_all=True,
        append_images=frames[1:], loop=0,
        duration=duration_ms, disposal=2,
    )


def save_webp_frames(frames, out_path: Path, duration_ms: int, quality: int = 85):
    frames[0].save(
        out_path, format="WEBP", save_all=True,
        append_images=frames[1:], loop=0,
        duration=duration_ms, quality=quality, method=4,
    )


def convert_tgs(tgs_path: Path, out_path: Path, size: int, target_fps: int, fmt: str, quality: int = 85):
    frames, duration_ms, src_fps = get_tgs_frames(tgs_path, size, size, target_fps)
    if not frames:
        return False, 0, 0
    if fmt == "GIF":
        save_gif(frames, out_path, duration_ms)
    else:
        save_webp_frames(frames, out_path, duration_ms, quality)
    return out_path.exists() and out_path.stat().st_size > 0, src_fps, duration_ms


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    os.system("")
    header()

    # Hien thi trang thai ffmpeg
    print()
    if HAS_FFMPEG:
        ok(f"ffmpeg: {FFMPEG}")
    else:
        warn("ffmpeg khong tim thay!")
        warn("Dat ffmpeg.exe cung thu muc voi file exe nay.")
        warn("Download: https://github.com/BtbN/FFmpeg-Builds/releases")
        warn("File .webm se bi bo qua.")

    # [1] Thu muc input
    step(1, "Thu muc chua file sticker:")
    input_dir = prompt_dir("Duong dan")

    tgs_files  = sorted(input_dir.glob("*.tgs"))
    webm_files = sorted(input_dir.glob("*.webm"))
    all_files  = tgs_files + webm_files

    if not all_files:
        err("Khong tim thay file .tgs hoac .webm nao.")
        input("\n  Nhan Enter de thoat...")
        return

    print()
    if tgs_files:  ok(f"TGS : {len(tgs_files)} file")
    if webm_files: ok(f"WebM: {len(webm_files)} file")

    # [2] Format output
    step(2, "Format output:")
    print("     [1] GIF  - pho bien, khong alpha")
    print("     [2] WebP - giu alpha, chat luong tot (khuyen nghi)")
    fmt_choice = prompt_choice("Chon", ["1", "2"], "2")
    fmt = "GIF" if fmt_choice == "1" else "WEBP"
    ok(f"Format: {fmt}")

    # [3] % resize
    step(3, "Resize theo % (100 = 512x512 goc, 50 = 256x256):")
    pct = prompt_float("% kich thuoc", 100.0, 1.0, 500.0)
    base_size = 512
    out_size = max(8, int(round(base_size * pct / 100)))
    if out_size % 2 != 0:
        out_size += 1
    ok(f"Kich thuoc output: {out_size}x{out_size} px")

    # [4] FPS (chi cho TGS)
    target_fps = 0
    if tgs_files:
        step(4, "FPS cho TGS (0 = giu nguyen FPS goc):")
        target_fps = prompt_int("Target FPS", 0, 0, 120)
        ok("Giu FPS goc" if target_fps == 0 else f"Target FPS: {target_fps}")
    else:
        step(4, "(Bo qua - khong co file TGS)")

    # [5] Quality (WebP)
    quality = 85
    if fmt == "WEBP":
        step(5, "Chat luong WebP (1-100):")
        quality = prompt_int("Quality", 85, 1, 100)
        ok(f"Quality: {quality}")
    else:
        step(5, "(Bo qua quality - khong ap dung cho GIF)")

    # [6] Output dir
    step(6, "Thu muc output:")
    print("     [1] Tu tao thu muc con trong thu muc input")
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

    # [7] Convert
    hr()
    step(7, f"Bat dau convert {len(all_files)} file...\n")

    success, failed, skipped = 0, 0, 0
    total = len(all_files)

    for i, src in enumerate(all_files, 1):
        is_tgs  = src.suffix.lower() == ".tgs"
        name    = src.stem
        tag     = clr("[TGS] ", CYAN) if is_tgs else clr("[WebM]", MAGENTA)
        ext     = fmt.lower()
        out_file = output_dir / f"{name}.{ext}"

        sys.stdout.write(f"  [{i}/{total}] {tag} {name} ... ")
        sys.stdout.flush()

        ok_flag = False
        detail  = ""

        try:
            if is_tgs:
                ok_flag, src_fps, dur_ms = convert_tgs(
                    src, out_file, out_size, target_fps, fmt, quality
                )
                detail = f"src={src_fps}fps {dur_ms}ms/frame"
            else:
                # WebM
                if not HAS_FFMPEG:
                    print(clr("SKIP (khong co ffmpeg)", YELLOW))
                    skipped += 1
                    continue

                if fmt == "GIF":
                    ok_flag = convert_webm_to_gif(src, out_file, out_size)
                else:
                    ok_flag = convert_webm_to_webp(src, out_file, out_size, quality)

                if ok_flag:
                    w, h, fps, alpha = probe_webm(src)
                    detail = f"src={w}x{h} {fps}fps alpha={'yes' if alpha else 'no'}"

        except Exception as e:
            err(f"Loi: {e}")
            ok_flag = False

        if ok_flag:
            size_str = fmt_size(out_file.stat().st_size)
            extra = f", {detail}" if detail else ""
            print(clr(f"OK  ({size_str}{extra})", GREEN))
            success += 1
        else:
            print(clr("FAILED", RED))
            failed += 1

    # Ket qua
    print()
    hr()
    parts = [f"Thanh cong: {clr(str(success), GREEN)}"]
    if failed:   parts.append(f"That bai: {clr(str(failed), RED)}")
    if skipped:  parts.append(f"Bo qua: {clr(str(skipped), YELLOW)}")
    print(f"\n  Hoan thanh!  " + "  |  ".join(parts))
    info(f"Output: {output_dir}")
    print()
    input("  Nhan Enter de thoat...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Da huy.")
