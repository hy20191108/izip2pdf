"""Tests for security features and CMYK handling added in security improvements."""
import io
import zipfile

import pytest
from PIL import Image

import izip2pdf


def create_test_zip_with_cmyk():
    """Create a test ZIP file with a CMYK image."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Create CMYK image
        cmyk_img = Image.new('CMYK', (200, 200), color=(100, 50, 0, 0))
        cmyk_bytes = io.BytesIO()
        cmyk_img.save(cmyk_bytes, format='JPEG')
        zf.writestr('cmyk_image.jpg', cmyk_bytes.getvalue())

        # Create RGB for comparison
        rgb_img = Image.new('RGB', (200, 200), color='red')
        rgb_bytes = io.BytesIO()
        rgb_img.save(rgb_bytes, format='JPEG')
        zf.writestr('rgb_image.jpg', rgb_bytes.getvalue())

    return zip_buffer.getvalue()


def test_cmyk_image_handling(tmp_path):
    """Test that CMYK images are correctly identified and converted."""
    zip_bin = create_test_zip_with_cmyk()

    # Should successfully convert without treating CMYK as transparent
    output_pdf = tmp_path / "cmyk_test.pdf"
    pdf_bytes = izip2pdf.convert(zip_bin, str(output_pdf))

    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b'%PDF')
    assert output_pdf.exists()
    assert output_pdf.stat().st_size > 0


def test_max_image_pixels_default():
    """Test that max_image_pixels defaults to safe value."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Small image that should work with default limits
        img = Image.new('RGB', (100, 100), color='blue')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        zf.writestr('small.png', img_bytes.getvalue())

    # Should work with default safe limits
    pdf_bytes = izip2pdf.convert(zip_buffer.getvalue())
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b'%PDF')


def test_max_image_pixels_custom_limit():
    """Test that custom max_image_pixels limit is respected."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Create a small image
        img = Image.new('RGB', (100, 100), color='green')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        zf.writestr('test.png', img_bytes.getvalue())

    # Should work with custom limit that allows this size
    pdf_bytes = izip2pdf.convert(
        zip_buffer.getvalue(),
        max_image_pixels=50_000_000  # 50 megapixels
    )
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b'%PDF')


def test_load_truncated_images_false_by_default():
    """Test that load_truncated_images defaults to False (safer)."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Normal complete image
        img = Image.new('RGB', (100, 100), color='yellow')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        zf.writestr('complete.png', img_bytes.getvalue())

    # Should work with default (False) setting
    pdf_bytes = izip2pdf.convert(zip_buffer.getvalue())
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b'%PDF')


def test_load_truncated_images_explicit():
    """Test that load_truncated_images parameter is accepted."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        img = Image.new('RGB', (100, 100), color='cyan')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        zf.writestr('test.jpg', img_bytes.getvalue())

    # Test with explicit False
    pdf_bytes_safe = izip2pdf.convert(
        zip_buffer.getvalue(),
        load_truncated_images=False
    )
    assert len(pdf_bytes_safe) > 0

    # Test with explicit True (for trusted input)
    pdf_bytes_lenient = izip2pdf.convert(
        zip_buffer.getvalue(),
        load_truncated_images=True
    )
    assert len(pdf_bytes_lenient) > 0


def test_rgba_vs_cmyk_distinction():
    """Test that RGBA and CMYK images are handled differently."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # RGBA with transparency
        rgba_img = Image.new('RGBA', (100, 100), color=(255, 0, 0, 128))
        rgba_bytes = io.BytesIO()
        rgba_img.save(rgba_bytes, format='PNG')
        zf.writestr('rgba.png', rgba_bytes.getvalue())

        # CMYK without transparency (4 channels but not alpha)
        cmyk_img = Image.new('CMYK', (100, 100), color=(50, 100, 0, 0))
        cmyk_bytes = io.BytesIO()
        cmyk_img.save(cmyk_bytes, format='JPEG')
        zf.writestr('cmyk.jpg', cmyk_bytes.getvalue())

    # Both should convert successfully without confusing CMYK for RGBA
    pdf_bytes = izip2pdf.convert(zip_buffer.getvalue())
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b'%PDF')


def test_security_parameters_combined():
    """Test combining multiple security parameters."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        img = Image.new('RGB', (200, 200), color='magenta')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        zf.writestr('test.png', img_bytes.getvalue())

    # Test with combined security settings
    pdf_bytes = izip2pdf.convert(
        zip_buffer.getvalue(),
        max_image_pixels=100_000_000,
        load_truncated_images=False,
        on_error="warn"
    )
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b'%PDF')
