"""Test LA-mode (grayscale + alpha) image handling.

Pre-v0.2.0 this raised IndexError because process_alpha used
image.split()[3] which is RGBA-specific.
"""
import io
import zipfile

from PIL import Image

import izip2pdf


def _zip_with_la_image() -> bytes:
    buf = io.BytesIO()
    img = Image.new("LA", (50, 50), color=(128, 200))
    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("la_image.png", img_buf.getvalue())
    return buf.getvalue()


def test_la_mode_white_background() -> None:
    pdf = izip2pdf.convert(_zip_with_la_image(), alpha_mode="white")
    assert pdf.startswith(b"%PDF")


def test_la_mode_black_background() -> None:
    pdf = izip2pdf.convert(_zip_with_la_image(), alpha_mode="black")
    assert pdf.startswith(b"%PDF")


def test_la_mode_drop_alpha() -> None:
    pdf = izip2pdf.convert(_zip_with_la_image(), alpha_mode="drop")
    assert pdf.startswith(b"%PDF")
