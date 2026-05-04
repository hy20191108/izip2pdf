"""Test that to_jpeg_bytes() also triggers HEIF/AVIF plugin registration.

Regression test for: codex P2 review on PR #2 — to_jpeg_bytes() bypassed
_ensure_format_support() before v0.2.1, breaking HEIF/AVIF compat for
direct callers (e.g. ImageProcessor replacement code).
"""
import io

from PIL import Image

import izip2pdf


def test_to_jpeg_bytes_triggers_format_support() -> None:
    """Calling to_jpeg_bytes() must ensure HEIF/AVIF plugins are registered."""
    # Reset the module-level guard so we observe the registration.
    izip2pdf.izip2pdf._format_support_initialized = False  # type: ignore[attr-defined]

    img_buf = io.BytesIO()
    Image.new("RGB", (50, 50), "red").save(img_buf, format="PNG")

    izip2pdf.to_jpeg_bytes("img.png", img_buf.getvalue())

    assert izip2pdf.izip2pdf._format_support_initialized is True  # type: ignore[attr-defined]
