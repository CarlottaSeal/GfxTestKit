"""
screenshot_test.py - Screenshot regression testing via PSNR/SSIM.

Modeled after The-Forge's TestScreenshots():
  - Reference-image-driven traversal (ensures no missing screenshots slip through)
  - PSNR as primary metric with configurable threshold (default 70 dB)
  - Pixel-count safety valve (<16 differing pixels = forced pass)
  - Diff image saved for visual inspection
  - scikit-image imported lazily (avoid import overhead when test is disabled)

Usage:
  Requires the target application to capture screenshots into a known directory.
  Reference images must be pre-captured and stored in the baseline directory.
"""

import time
from pathlib import Path

from core import RET_SUCCESS, RET_WARNING, RET_CRITICAL
from core.config import ProjectConfig
from core.runner import launch
from core.report import TestResult


# Lazy-loaded to avoid dependency when screenshot test is disabled
_skimage_loaded = False
_compare_psnr = None
_compare_ssim = None


def _ensure_skimage():
    """Lazy import scikit-image (same pattern as The-Forge TestScreenshots line 189)."""
    global _skimage_loaded, _compare_psnr, _compare_ssim
    if _skimage_loaded:
        return True
    try:
        from skimage.metrics import peak_signal_noise_ratio, structural_similarity
        from skimage import io as skimage_io  # noqa: F401 - ensure it's available
        _compare_psnr = peak_signal_noise_ratio
        _compare_ssim = structural_similarity
        _skimage_loaded = True
        return True
    except ImportError:
        print("  [Screenshot] ERROR: scikit-image not installed (pip install scikit-image)")
        return False


def _compare_images(output_path: Path, reference_path: Path, psnr_threshold: float) -> dict:
    """
    Compare two images and return comparison metrics.

    Returns dict with: psnr, ssim, diff_pixels, passed, reason
    """
    from skimage import io as skimage_io
    import numpy as np

    img_out = skimage_io.imread(str(output_path))
    img_ref = skimage_io.imread(str(reference_path))

    # Handle size mismatch
    if img_out.shape != img_ref.shape:
        return {
            "psnr": 0.0, "ssim": 0.0, "diff_pixels": -1,
            "passed": False, "reason": f"Size mismatch: {img_out.shape} vs {img_ref.shape}",
        }

    # PSNR
    psnr = float(_compare_psnr(img_ref, img_out))

    # SSIM (multichannel for RGB)
    channel_axis = 2 if len(img_ref.shape) == 3 else None
    ssim = float(_compare_ssim(img_ref, img_out, channel_axis=channel_axis))

    # Count differing pixels (The-Forge's <16 pixel safety valve)
    diff = np.abs(img_out.astype(float) - img_ref.astype(float))
    if len(diff.shape) == 3:
        diff_mask = np.any(diff > 1.0, axis=2)  # any channel differs by >1
    else:
        diff_mask = diff > 1.0
    diff_pixels = int(np.sum(diff_mask))

    # Two-gate pass logic (The-Forge TestScreenshots lines 313-319):
    # Gate 1: PSNR >= threshold -> PASS
    # Gate 2: diff_pixels < 16 -> forced PASS (floating point jitter)
    if psnr >= psnr_threshold:
        passed = True
        reason = f"PSNR {psnr:.1f} >= {psnr_threshold}"
    elif diff_pixels < 16:
        passed = True
        reason = f"PSNR {psnr:.1f} < {psnr_threshold}, but only {diff_pixels} diff pixels (< 16, forced pass)"
    else:
        passed = False
        reason = f"PSNR {psnr:.1f} < {psnr_threshold}, {diff_pixels} diff pixels"

    # Save diff image for inspection
    diff_path = output_path.parent / f"{output_path.stem}_diff{output_path.suffix}"
    try:
        from skimage import exposure
        if len(diff.shape) == 3:
            diff_gray = np.mean(diff, axis=2)
        else:
            diff_gray = diff
        diff_vis = exposure.rescale_intensity(diff_gray, out_range=(0, 255)).astype(np.uint8)
        skimage_io.imsave(str(diff_path), diff_vis)
    except Exception:
        pass  # non-critical

    return {
        "psnr": round(psnr, 2),
        "ssim": round(ssim, 4),
        "diff_pixels": diff_pixels,
        "passed": passed,
        "reason": reason,
    }


def run(cfg: ProjectConfig, update_baseline: bool = False) -> TestResult:
    """
    Execute the screenshot regression test.

    1. Launch app with screenshot args (app captures screenshots to output dir)
    2. Compare each reference image against the output
    3. Report per-image PSNR and overall pass/fail
    """
    start = time.time()
    output_dir = Path(cfg.screenshot_output_dir)
    reference_dir = Path(cfg.screenshot_reference_dir)
    threshold = cfg.screenshot_psnr_threshold

    # Launch application to capture screenshots
    if cfg.screenshot_args:
        run_result = launch(
            exe_path=Path(cfg.exe_path),
            args=cfg.screenshot_args,
            working_dir=Path(cfg.working_dir) if cfg.working_dir else None,
            timeout=cfg.timeout,
            env=cfg.env_vars or None,
        )
        if run_result.crashed:
            return TestResult(
                name="screenshot", status="FAIL", return_code=RET_CRITICAL,
                message=f"App crashed during screenshot capture: {run_result.crash_reason}",
                duration_seconds=time.time() - start,
            )

    # Update baseline: copy outputs to reference dir
    if update_baseline:
        if not output_dir.exists():
            return TestResult(
                name="screenshot", status="FAIL", return_code=RET_CRITICAL,
                message=f"Output dir not found: {output_dir}",
                duration_seconds=time.time() - start,
            )
        import shutil
        reference_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for img in output_dir.glob("*.png"):
            shutil.copy2(img, reference_dir / img.name)
            count += 1
        return TestResult(
            name="screenshot", status="PASS",
            message=f"Baseline updated: {count} images copied to {reference_dir}",
            duration_seconds=time.time() - start,
        )

    # Lazy load scikit-image
    if not _ensure_skimage():
        return TestResult(
            name="screenshot", status="SKIP", return_code=RET_WARNING,
            message="scikit-image not available",
            duration_seconds=time.time() - start,
        )

    # Reference-driven traversal (The-Forge pattern: iterate references, not outputs)
    if not reference_dir.exists():
        return TestResult(
            name="screenshot", status="SKIP", return_code=RET_WARNING,
            message=f"No reference dir: {reference_dir}",
            duration_seconds=time.time() - start,
        )

    references = sorted(reference_dir.glob("*.png"))
    if not references:
        return TestResult(
            name="screenshot", status="SKIP", return_code=RET_WARNING,
            message="No reference images found",
            duration_seconds=time.time() - start,
        )

    ret_code = RET_SUCCESS
    details = {}
    failures = []

    for ref_img in references:
        out_img = output_dir / ref_img.name

        if not out_img.exists():
            details[ref_img.name] = {"passed": False, "reason": "OUTPUT MISSING"}
            ret_code = max(ret_code, RET_CRITICAL)
            failures.append(f"{ref_img.name}: missing")
            print(f"  [Screenshot] {ref_img.name}: MISSING")
            continue

        comp = _compare_images(out_img, ref_img, threshold)
        details[ref_img.name] = comp
        status_str = "PASS" if comp["passed"] else "FAIL"
        print(f"  [Screenshot] {ref_img.name}: PSNR={comp['psnr']:.1f} SSIM={comp['ssim']:.3f} "
              f"diff={comp['diff_pixels']}px [{status_str}]")

        if not comp["passed"]:
            ret_code = max(ret_code, RET_WARNING)
            failures.append(f"{ref_img.name}: {comp['reason']}")

    # Check for outputs without references (new screenshots not in baseline)
    if output_dir.exists():
        for out_img in sorted(output_dir.glob("*.png")):
            if "_diff" in out_img.stem:
                continue
            if not (reference_dir / out_img.name).exists():
                print(f"  [Screenshot] {out_img.name}: NEW (no reference)")

    if ret_code == RET_SUCCESS:
        msg = f"All {len(references)} screenshots match"
        status = "PASS"
    else:
        msg = f"{len(failures)}/{len(references)} failed: {failures[0]}"
        status = "WARNING" if ret_code <= RET_WARNING else "FAIL"

    return TestResult(
        name="screenshot", status=status, return_code=ret_code,
        message=msg, details=details, duration_seconds=time.time() - start,
    )
