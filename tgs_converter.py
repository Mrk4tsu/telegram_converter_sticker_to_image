import os
import sys
import subprocess
import shutil
from pathlib import Path


# ── Check deps ───────────────────────────────────────────────────────────────
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

    # ffmpeg optional - chi can cho WebM
    has_ffmpeg = shutil.which("ffmpeg") is not None
    return has_ffmpeg


check_deps_result = check_deps()
HAS_FFMPEG = check_deps_result

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
MAGENTA = "\033[95m"


def clr(text, color):   return f"{color}{text}{RESET}"
def ok(msg):            print(clr(f"  [OK] {msg}", GREEN))
def err(msg):           print(clr(f"  [!!] {msg}", RED))
def info(msg):          print(clr(f"  --> {msg}", CYAN))
def warn(msg):          print(clr(f"  [!] {msg}", YELLOW))
def step(n, msg):       print(f"\n{clr(f'[{n}]', YELLOW)} {WHITE}{msg}{RESET}")
def hr():               print(clr("  " + "-" * 54, GRAY))

def header():
    print()
    print(clr("=" * 56, CYAN))
    print(clr("  TGS + WebM Sticker Converter  v4", BOLD))
    print(clr("  .tgs -> GIF/WebP  |  .webm -> GIF/WebP/WebM", GRAY))
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


# ── Lay thong tin WebM bang ffprobe ──────────────────────────────────────────
def probe_webm(path: Path):
    """Tra ve (width, height, fps) cua file webm."""
    try:
        import json
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", str(path)],
            capture_output=True, text=True
        )
        data = json.loads(result.stdout)
        s = data["streams"][0]
        w = s["width"]
        h = s["height"]
        fps_raw = s.get("r_frame_rate", "30/1")
        num, den = fps_raw.split("/")
        fps = round(int(num) / int(den), 2)
        has_alpha = s.get("tags", {}).get("alpha_mode", "0") == "1"
        return w, h, fps, has_alpha
    except Exception:
        return 512, 512, 30.0, False


# ── Convert WebM bang ffmpeg ──────────────────────────────────────────────────
def convert_webm_to_gif(src: Path, dst: Path, size: int):
    """
    WebM (VP9 + alpha) -> GIF
    Dung palette de giam artifact mau.
    Alpha -> nen trang (GIF khong ho tro alpha that su).
    """
    # Buoc 1: tao palette
    palette = dst.with_suffix(".palette.png")
    cmd_palette = [
        "ffmpeg", "-y", "-i", str(src),
        "-vf", f"scale={size}:{size}:flags=lanczos,palettegen=reserve_transparent=1",
        str(palette)
    ]
    r1 = subprocess.run(cmd_palette, capture_output=True)
    if r1.returncode != 0:
        return False

    # Buoc 2: render GIF dung palette
    cmd_gif = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-i", str(palette),
        "-lavfi", f"scale={size}:{size}:flags=lanczos [x]; [x][1:v] paletteuse=alpha_threshold=128",
        str(dst)
    ]
    r2 = subprocess.run(cmd_gif, capture_output=True)
    palette.unlink(missing_ok=True)
    return r2.returncode == 0 and dst.exists() and dst.stat().st_size > 0


def convert_webm_to_webp(src: Path, dst: Path, size: int, quality: int = 85):
    """
    WebM (VP9 + alpha) -> Animated WebP
    Giu alpha channel.
    """
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-vf", f"scale={size}:{size}:flags=lanczos",
        "-vcodec", "libwebp",
        "-lossless", "0",
        "-quality", str(quality),
        "-loop", "0",
        "-preset", "default",
        "-an",
        str(dst)
    ]
    r = subprocess.run(cmd, capture_output=True)
    return r.returncode == 0 and dst.exists() and dst.stat().st_size > 0


def convert_webm_to_webm(src: Path, dst: Path, size: int, quality: int = 85):
    """
    WebM -> WebM (resize, giu VP9 + alpha)
    quality: 0=tot nhat, 63=te nhat (ffmpeg crf scale)
    crf = map quality(1-100) -> crf(63-0)
    """
    crf = int(63 - (quality / 100.0 * 63))
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-vf", f"scale={size}:{size}:flags=lanczos",
        "-c:v", "libvpx-vp9",
        "-crf", str(crf),
        "-b:v", "0",
        "-auto-alt-ref", "0",  # bat buoc khi co alpha
        "-an",
        str(dst)
    ]
    r = subprocess.run(cmd, capture_output=True)
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

    frames = []
    for i in indices:
        frames.append(anim.render_pillow_frame(i, width=width, height=height))
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
    ok_flag = out_path.exists() and out_path.stat().st_size > 0
    return ok_flag, src_fps, duration_ms


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    os.system("")
    header()

    if not HAS_FFMPEG:
        warn("ffmpeg khong tim thay trong PATH.")
        warn("Convert file .webm se khong hoat dong.")
        warn("Download: https://ffmpeg.org/download.html")
    else:
        ok("ffmpeg da san sang")

    # [1] Thu muc input
    step(1, "Thu muc chua file sticker:")
    input_dir = prompt_dir("Duong dan")

    tgs_files  = sorted(input_dir.glob("*.tgs"))
    webm_files = sorted(input_dir.glob("*.webm"))
    all_files  = tgs_files + webm_files

    if not all_files:
        err("Khong tim thay file .tgs hoac .webm nao.")
        return

    print()
    if tgs_files:
        ok(f"TGS : {len(tgs_files)} file")
    if webm_files:
        ok(f"WebM: {len(webm_files)} file")

    # [2] Format output
    step(2, "Format output:")
    print("     [1] GIF  - ho tro rong, khong co alpha that su")
    print("     [2] WebP - chat luong tot, giu alpha")
    if webm_files and HAS_FFMPEG:
        print("     [3] WebM - chi cho file .webm, giu alpha + chat luong cao nhat")
    fmt_choice = prompt_choice("Chon", ["1", "2", "3"] if (webm_files and HAS_FFMPEG) else ["1", "2"], "2")
    fmt_map = {"1": "GIF", "2": "WEBP", "3": "WEBM"}
    fmt = fmt_map[fmt_choice]
    ok(f"Format: {fmt}")

    if fmt == "WEBM" and tgs_files:
        warn(f"Format WebM chi ap dung cho .webm, {len(tgs_files)} file .tgs se duoc convert sang WebP thay.")

    # [3] % resize
    step(3, "Resize theo % (100 = giu nguyen 512x512, 50 = 256x256):")
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
        step(4, "(Bo qua FPS - khong co file TGS)")

    # [5] Quality
    quality = 85
    if fmt != "GIF":
        step(5, f"Chat luong {fmt} (1-100):")
        quality = prompt_int("Quality", 85, 1, 100)
        ok(f"Quality: {quality}")
    else:
        step(5, "(Bo qua quality - GIF khong co tuy chon nay)")

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

    success, failed = 0, 0
    total = len(all_files)

    for i, src in enumerate(all_files, 1):
        is_tgs  = src.suffix.lower() == ".tgs"
        is_webm = src.suffix.lower() == ".webm"
        name = src.stem
        tag  = clr("[TGS] ", CYAN) if is_tgs else clr("[WebM]", MAGENTA)

        # Tentukan ext output
        if is_webm and fmt == "WEBM":
            out_ext = "webm"
        elif fmt == "GIF":
            out_ext = "gif"
        elif fmt == "WEBP":
            out_ext = "webp"
        else:
            out_ext = "webp"  # TGS fallback dari WEBM

        out_file = output_dir / f"{name}.{out_ext}"
        sys.stdout.write(f"  [{i}/{total}] {tag} {name} ... ")
        sys.stdout.flush()

        ok_flag = False
        detail  = ""

        try:
            if is_tgs:
                # TGS -> GIF hoac WebP
                actual_fmt = fmt if fmt != "WEBM" else "WEBP"
                ok_flag, src_fps, dur_ms = convert_tgs(
                    src, out_file, out_size, target_fps, actual_fmt, quality
                )
                detail = f"src={src_fps}fps {dur_ms}ms/frame"

            elif is_webm:
                if not HAS_FFMPEG:
                    err("ffmpeg khong co, bo qua")
                    failed += 1
                    continue

                if fmt == "GIF":
                    ok_flag = convert_webm_to_gif(src, out_file, out_size)
                elif fmt == "WEBM":
                    ok_flag = convert_webm_to_webm(src, out_file, out_size, quality)
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
            print(clr(f"OK  ({size_str}" + (f", {detail}" if detail else "") + ")", GREEN))
            success += 1
        else:
            print(clr("FAILED", RED))
            failed += 1

    print()
    hr()
    print(f"\n  Hoan thanh!  Thanh cong: {clr(str(success), GREEN)}  |  That bai: {clr(str(failed), RED)}")
    info(f"Output: {output_dir}")
    print()
    input("  Nhan Enter de thoat...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Da huy.")
