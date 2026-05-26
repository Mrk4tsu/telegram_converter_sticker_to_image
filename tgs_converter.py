"""
TGS + WebM Sticker Converter v6
================================
Ho tro:
  - .tgs  (Telegram Animated Sticker) -> GIF / WebP
  - .webm (Telegram Video Sticker)    -> GIF / WebP

Fix v6:
  - WebM VP9 alpha: buoc giai ma bang libvpx-vp9 (software decoder)
    moi giu duoc alpha stream an cua VP9 Profile 0 alpha_mode=1
  - Timing chinh xac: lay PTS tung frame bang ffprobe,
    tinh duration moi frame tu PTS gap thay vi dung fps uniform
    -> khong bi drop/duplicate frame, animation khong bi giat
  - GIF: xu ly alpha dung (disposal=2, transparency=0)
  - WebP: duration la list per-frame thay vi mot gia tri chung

Yeu cau:
  pip install rlottie-python pillow

Build thanh exe:
  1. Dat ffmpeg.exe + ffprobe.exe cung thu muc voi script nay
  2. pyinstaller --onefile --console ^
       --add-binary "ffmpeg.exe;." ^
       --add-binary "ffprobe.exe;." ^
       tgs_converter.py
"""

import os
import sys
import json
import subprocess
import shutil
from pathlib import Path


# ── Tim ffmpeg / ffprobe ──────────────────────────────────────────────────────
def _find_tool(name: str) -> str | None:
    exe = name + (".exe" if sys.platform == "win32" else "")
    candidates = []
    candidates.append(Path(sys.executable).parent / exe)
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys._MEIPASS) / exe)
    else:
        candidates.append(Path(__file__).parent / exe)
    for p in candidates:
        if p.exists():
            return str(p)
    return shutil.which(name)


FFMPEG  = _find_tool("ffmpeg")
FFPROBE = _find_tool("ffprobe")
HAS_FFMPEG  = FFMPEG  is not None
HAS_FFPROBE = FFPROBE is not None


# ── Check pip deps ────────────────────────────────────────────────────────────
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
        print("\nThieu thu vien Python:")
        for lib in missing:
            print(f"  pip install {lib}")
        sys.exit(1)


check_deps()

from rlottie_python import LottieAnimation
from PIL import Image

# ── Colors ────────────────────────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
CYAN    = "\033[96m"
GREEN   = "\033[92m"
RED     = "\033[91m"
YELLOW  = "\033[93m"
GRAY    = "\033[90m"
WHITE   = "\033[97m"
MAGENTA = "\033[95m"

def clr(text, color): return f"{color}{text}{RESET}"
def ok(msg):          print(clr(f"  [OK] {msg}", GREEN))
def err(msg):         print(clr(f"  [!!] {msg}", RED))
def info(msg):        print(clr(f"  --> {msg}", CYAN))
def warn(msg):        print(clr(f"  [!]  {msg}", YELLOW))
def step(n, msg):     print(f"\n{clr(f'[{n}]', YELLOW)} {WHITE}{msg}{RESET}")
def hr():             print(clr("  " + "-" * 54, GRAY))

def header():
    print()
    print(clr("=" * 56, CYAN))
    print(clr("  TGS + WebM Sticker Converter  v6", BOLD))
    print(clr("  .tgs -> GIF/WebP  |  .webm -> GIF/WebP", GRAY))
    print(clr("=" * 56, CYAN))

def fmt_size(n):
    if n < 1024:      return f"{n} B"
    if n < 1024**2:   return f"{n/1024:.1f} KB"
    return f"{n/1024**2:.2f} MB"

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
        except ValueError:
            pass
        err(f"Nhap so tu {lo} den {hi}")

def prompt_int(msg, default, lo, hi):
    while True:
        raw = prompt(msg, str(default))
        try:
            val = int(raw)
            if lo <= val <= hi:
                return val
        except ValueError:
            pass
        err(f"Nhap so nguyen tu {lo} den {hi}")

def prompt_choice(msg, choices, default):
    opts = "/".join(choices)
    while True:
        raw = prompt(f"{msg} ({opts})", default).upper()
        if raw in [c.upper() for c in choices]:
            return raw
        err(f"Chon mot trong: {opts}")


# ════════════════════════════════════════════════════════════════════════════
#  WEBM UTILITIES
# ════════════════════════════════════════════════════════════════════════════

def probe_webm(path: Path) -> dict:
    """
    Tra ve dict:
      width, height, fps (float), has_alpha (bool),
      n_frames (int), durations_ms (list[int])

    Cach tinh duration:
      - Lay danh sach PTS tung packet bang ffprobe
      - duration[i] = pts[i+1] - pts[i]
      - duration cuoi = total_duration - pts[-1]
    """
    result = {"width": 512, "height": 512, "fps": 30.0,
              "has_alpha": False, "n_frames": 0, "durations_ms": []}

    if not HAS_FFPROBE:
        return result

    try:
        # Stream info
        r = subprocess.run([
            FFPROBE, "-v", "quiet",
            "-select_streams", "v:0",
            "-show_streams",
            "-of", "json",
            str(path)
        ], capture_output=True, text=True)
        data = json.loads(r.stdout)
        s = data["streams"][0]

        result["width"]  = s.get("width",  512)
        result["height"] = s.get("height", 512)

        fps_raw = s.get("r_frame_rate", "30/1")
        num, den = fps_raw.split("/")
        result["fps"] = round(int(num) / max(int(den), 1), 3)

        # alpha_mode="1" trong Metadata tag -> co alpha stream VP9
        result["has_alpha"] = s.get("tags", {}).get("alpha_mode", "0") == "1"

        # Total duration tu format (chinh xac hon stream)
        r2 = subprocess.run([
            FFPROBE, "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "json",
            str(path)
        ], capture_output=True, text=True)
        total_dur = float(json.loads(r2.stdout)["format"]["duration"])

        # PTS tung frame
        r3 = subprocess.run([
            FFPROBE, "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "packet=pts_time",
            "-of", "json",
            str(path)
        ], capture_output=True, text=True)
        packets = json.loads(r3.stdout).get("packets", [])
        pts_list = [float(p["pts_time"]) for p in packets]

        if not pts_list:
            return result

        n = len(pts_list)
        result["n_frames"] = n

        # Duration moi frame tinh tu PTS gap
        durations = []
        for i in range(n):
            nxt = pts_list[i + 1] if i + 1 < n else total_dur
            ms = max(10, int(round((nxt - pts_list[i]) * 1000)))
            durations.append(ms)
        result["durations_ms"] = durations

    except Exception as e:
        pass  # tra ve gia tri mac dinh

    return result


def _extract_frames_webm(src: Path, n_frames: int, size: int, tmp_dir: Path) -> list[Image.Image]:
    """
    Extract chinh xac n_frames bang cach chon frame theo index.
    Dung libvpx-vp9 decoder de giai ma alpha stream VP9.
    Tra ve list[Image.RGBA].
    """
    tmp_dir.mkdir(parents=True, exist_ok=True)
    frames = []

    for i in range(n_frames):
        out = tmp_dir / f"f{i:04d}.png"
        r = subprocess.run([
            FFMPEG, "-y",
            "-vcodec", "libvpx-vp9",      # software decoder -> giu alpha
            "-i", str(src),
            "-vf", (
                f"select=eq(n\\,{i}),"     # lay dung frame thu i
                f"scale={size}:{size}:flags=lanczos"
            ),
            "-vframes", "1",
            "-update", "1",               # ghi 1 file thay vi sequence
            str(out)
        ], capture_output=True)

        if r.returncode != 0 or not out.exists() or out.stat().st_size == 0:
            # Frame loi: dung frame truoc do (hoac frame trang)
            if frames:
                frames.append(frames[-1].copy())
            else:
                frames.append(Image.new("RGBA", (size, size), (0, 0, 0, 0)))
            continue

        img = Image.open(out).convert("RGBA")
        frames.append(img)

    return frames


def convert_webm_to_webp(src: Path, dst: Path, size: int, quality: int = 85) -> tuple[bool, dict]:
    """
    Convert WebM -> animated WebP voi alpha chinh xac va timing dung.
    Tra ve (success: bool, info: dict)
    """
    probe = probe_webm(src)
    if probe["n_frames"] == 0:
        return False, probe

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        frames = _extract_frames_webm(src, probe["n_frames"], size, tmp_dir)

    if not frames:
        return False, probe

    try:
        frames[0].save(
            dst,
            format="WEBP",
            save_all=True,
            append_images=frames[1:],
            loop=0,
            duration=probe["durations_ms"],  # list per-frame duration
            quality=quality,
            method=6,
        )
        ok_flag = dst.exists() and dst.stat().st_size > 0
    except Exception as e:
        ok_flag = False

    return ok_flag, probe


def convert_webm_to_gif(src: Path, dst: Path, size: int) -> tuple[bool, dict]:
    """
    Convert WebM -> animated GIF voi alpha va timing dung.
    GIF chi ho tro 1-bit transparency -> dung disposal=2 + transparency=0.
    """
    probe = probe_webm(src)
    if probe["n_frames"] == 0:
        return False, probe

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        frames = _extract_frames_webm(src, probe["n_frames"], size, tmp_dir)

    if not frames:
        return False, probe

    try:
        frames[0].save(
            dst,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            loop=0,
            duration=probe["durations_ms"],
            disposal=2,      # xoa ve nen truoc khi ve frame tiep theo
            transparency=0,  # palette index 0 = trong suot
            optimize=False,
        )
        ok_flag = dst.exists() and dst.stat().st_size > 0
    except Exception as e:
        ok_flag = False

    return ok_flag, probe


# ════════════════════════════════════════════════════════════════════════════
#  TGS UTILITIES  (giu nguyen tu v5)
# ════════════════════════════════════════════════════════════════════════════

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


# ════════════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════════════

def main():
    os.system("")
    header()

    print()
    if HAS_FFMPEG:
        ok(f"ffmpeg : {FFMPEG}")
    else:
        warn("ffmpeg khong tim thay!")
        warn("Dat ffmpeg.exe cung thu muc voi file exe nay.")
        warn("Download: https://github.com/BtbN/FFmpeg-Builds/releases")
        warn("File .webm se bi bo qua.")

    if HAS_FFPROBE:
        ok(f"ffprobe: {FFPROBE}")
    else:
        warn("ffprobe khong tim thay! Timing co the khong chinh xac.")

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
    print("     [1] GIF  - pho bien, ho tro 1-bit alpha")
    print("     [2] WebP - giu alpha day du, chat luong tot (khuyen nghi)")
    fmt_choice = prompt_choice("Chon", ["1", "2"], "2")
    fmt = "GIF" if fmt_choice == "1" else "WEBP"
    ok(f"Format: {fmt}")

    # [3] % resize
    step(3, "Resize theo % (100 = 512x512 goc, 50 = 256x256):")
    pct = prompt_float("% kich thuoc", 100.0, 1.0, 500.0)
    out_size = max(8, int(round(512 * pct / 100)))
    if out_size % 2 != 0:
        out_size += 1
    ok(f"Kich thuoc output: {out_size}x{out_size} px")

    # [4] FPS (chi TGS)
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
        step(5, "(Bo qua quality - GIF khong ap dung)")

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
        is_tgs = src.suffix.lower() == ".tgs"
        name   = src.stem
        tag    = clr("[TGS] ", CYAN) if is_tgs else clr("[WebM]", MAGENTA)
        ext    = fmt.lower()
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
                detail = f"src={src_fps}fps  frame={dur_ms}ms"

            else:
                if not HAS_FFMPEG:
                    print(clr("SKIP (khong co ffmpeg)", YELLOW))
                    skipped += 1
                    continue

                if fmt == "GIF":
                    ok_flag, probe = convert_webm_to_gif(src, out_file, out_size)
                else:
                    ok_flag, probe = convert_webm_to_webp(src, out_file, out_size, quality)

                if ok_flag and probe["n_frames"] > 0:
                    dur_list = probe["durations_ms"]
                    alpha_str = "alpha=yes" if probe["has_alpha"] else "alpha=no"
                    detail = (
                        f"src={probe['width']}x{probe['height']} "
                        f"{probe['fps']}fps  "
                        f"frames={probe['n_frames']}  "
                        f"{alpha_str}  "
                        f"timing={dur_list}"
                    )

        except Exception as e:
            detail = str(e)
            ok_flag = False

        if ok_flag:
            size_str = fmt_size(out_file.stat().st_size)
            extra = f"  ({detail})" if detail else ""
            print(clr(f"OK  [{size_str}]{extra}", GREEN))
            success += 1
        else:
            reason = f"  ({detail})" if detail else ""
            print(clr(f"FAILED{reason}", RED))
            failed += 1

    # Ket qua
    print()
    hr()
    parts = [f"Thanh cong: {clr(str(success), GREEN)}"]
    if failed:  parts.append(f"That bai: {clr(str(failed), RED)}")
    if skipped: parts.append(f"Bo qua: {clr(str(skipped), YELLOW)}")
    print(f"\n  Hoan thanh!  " + "  |  ".join(parts))
    info(f"Output: {output_dir}")
    print()
    input("  Nhan Enter de thoat...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Da huy.")
