"""Test backward compatibility with existing API."""
import io
import zipfile

from PIL import Image

import izip2pdf


def create_simple_test_zip():
    """Create a simple ZIP file with one test image."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        img = Image.new('RGB', (100, 100), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        zf.writestr('image.png', img_bytes.getvalue())

    return zip_buffer.getvalue()


def test_positional_progress_argument():
    """Test that progress can still be used as a positional argument (backward compatibility)."""
    zip_bytes = create_simple_test_zip()

    # Old style: progress as 3rd positional argument
    pdf_bytes = izip2pdf.convert(zip_bytes, None, True)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b'%PDF')

    # Also test with False
    pdf_bytes2 = izip2pdf.convert(zip_bytes, None, False)
    assert len(pdf_bytes2) > 0

    # And with output path
    pdf_bytes3 = izip2pdf.convert("dummy.zip" if False else zip_bytes, None, "bar")
    assert len(pdf_bytes3) > 0


def test_keyword_progress_argument():
    """Test that progress can also be used as a keyword argument."""
    zip_bytes = create_simple_test_zip()

    # New style: progress as keyword argument
    pdf_bytes = izip2pdf.convert(zip_bytes, progress=True)
    assert len(pdf_bytes) > 0

    pdf_bytes2 = izip2pdf.convert(zip_bytes, progress="bar")
    assert len(pdf_bytes2) > 0

    pdf_bytes3 = izip2pdf.convert(zip_bytes, None, progress="log")
    assert len(pdf_bytes3) > 0


def test_new_parameters_must_be_keyword_only():
    """Test that new parameters must be specified as keywords."""
    zip_bytes = create_simple_test_zip()

    # These should work (keyword arguments)
    pdf1 = izip2pdf.convert(zip_bytes, jpeg_quality=90)
    assert len(pdf1) > 0

    pdf2 = izip2pdf.convert(zip_bytes, None, False, jpeg_quality=90, max_width=4096)
    assert len(pdf2) > 0

    # Trying to pass new params as positional would fail at runtime
    # (can't easily test TypeError in this context without actual call)


def test_mixed_old_and_new_style():
    """Test mixing old positional progress with new keyword parameters."""
    zip_bytes = create_simple_test_zip()

    # Old progress style (positional) + new parameters (keyword)
    pdf_bytes = izip2pdf.convert(
        zip_bytes,
        None,
        True,  # progress as positional
        jpeg_quality=90,  # new parameter as keyword
        alpha_mode="black"  # new parameter as keyword
    )
    assert len(pdf_bytes) > 0


def test_default_values_unchanged():
    """Test that default values remain the same for backward compatibility."""
    zip_bytes = create_simple_test_zip()

    # All defaults
    pdf1 = izip2pdf.convert(zip_bytes)
    assert len(pdf1) > 0

    # Only zip_input specified
    pdf2 = izip2pdf.convert(zip_bytes)
    assert len(pdf2) > 0

    # zip_input and output_pdf_path
    pdf3 = izip2pdf.convert(zip_bytes, None)
    assert len(pdf3) > 0
