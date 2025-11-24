"""Test edge cases and error handling."""
import io
import zipfile
import warnings

import pytest
from PIL import Image

import izip2pdf


def create_zip_with_corrupt_image():
    """Create a ZIP with a corrupt image file."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add a valid image
        img1 = Image.new('RGB', (100, 100), color='red')
        img1_bytes = io.BytesIO()
        img1.save(img1_bytes, format='PNG')
        zf.writestr('valid.png', img1_bytes.getvalue())

        # Add corrupt data pretending to be an image
        zf.writestr('corrupt.png', b'this is not a valid image')

        # Add another valid image
        img2 = Image.new('RGB', (100, 100), color='blue')
        img2_bytes = io.BytesIO()
        img2.save(img2_bytes, format='PNG')
        zf.writestr('valid2.png', img2_bytes.getvalue())

    return zip_buffer.getvalue()


def create_empty_zip():
    """Create an empty ZIP file."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED):
        pass  # Empty zip
    return zip_buffer.getvalue()


def create_zip_with_directory():
    """Create a ZIP with a directory entry."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add a directory
        zf.writestr('folder/', '')

        # Add an image inside the directory
        img = Image.new('RGB', (100, 100), color='green')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        zf.writestr('folder/image.png', img_bytes.getvalue())

    return zip_buffer.getvalue()


def test_error_handling_raise():
    """Test that raise mode actually raises exceptions."""
    zip_bytes = create_zip_with_corrupt_image()

    with pytest.raises(Exception):
        izip2pdf.convert(zip_bytes, on_error="raise")


def test_error_handling_skip():
    """Test that skip mode continues processing."""
    zip_bytes = create_zip_with_corrupt_image()
    logged_messages = []

    def custom_log(msg: str) -> None:
        logged_messages.append(msg)

    # Should not raise, should skip corrupt file
    pdf_bytes = izip2pdf.convert(
        zip_bytes,
        on_error="skip",
        log_func=custom_log
    )

    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b'%PDF')
    # Should have logged the skipped file
    assert any('SKIPPED' in msg or 'corrupt.png' in msg for msg in logged_messages)


def test_error_handling_warn():
    """Test that warn mode issues warnings."""
    zip_bytes = create_zip_with_corrupt_image()

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        pdf_bytes = izip2pdf.convert(zip_bytes, on_error="warn")

        assert len(pdf_bytes) > 0
        # Should have issued a warning
        assert len(w) > 0
        assert any('corrupt.png' in str(warning.message) for warning in w)


def test_empty_zip_with_warn():
    """Test handling of empty ZIP file with warn mode (default)."""
    zip_bytes = create_empty_zip()

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        pdf_bytes = izip2pdf.convert(zip_bytes, on_error="warn")

        # Should return empty bytes and issue a warning
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) == 0
        assert len(w) > 0
        assert any('No valid images' in str(warning.message) for warning in w)


def test_empty_zip_with_raise():
    """Test handling of empty ZIP file with raise mode."""
    zip_bytes = create_empty_zip()

    # Should raise ValueError
    with pytest.raises(ValueError, match="No valid images"):
        izip2pdf.convert(zip_bytes, on_error="raise")


def test_empty_zip_with_skip():
    """Test handling of empty ZIP file with skip mode."""
    zip_bytes = create_empty_zip()

    # Should return empty bytes without raising
    pdf_bytes = izip2pdf.convert(zip_bytes, on_error="skip")
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) == 0


def test_zip_with_directory():
    """Test that directory entries are properly skipped."""
    zip_bytes = create_zip_with_directory()

    pdf_bytes = izip2pdf.convert(zip_bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b'%PDF')


def test_large_image_resizing():
    """Test that large images are properly resized."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Create an image larger than our custom max (but not huge to avoid memory issues)
        # 2000x2000 is large enough to test resizing logic without consuming excessive memory
        large_img = Image.new('RGB', (2000, 2000), color='red')
        img_bytes = io.BytesIO()
        large_img.save(img_bytes, format='PNG')
        zf.writestr('large.png', img_bytes.getvalue())

    zip_bytes = zip_buffer.getvalue()

    # Should resize to max dimensions (1000x1000)
    pdf_bytes = izip2pdf.convert(zip_bytes, max_width=1000, max_height=1000)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b'%PDF')


def test_custom_max_dimensions_respected():
    """Test that custom max dimensions are respected."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Create an image slightly larger than custom max
        img = Image.new('RGB', (2000, 2000), color='blue')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        zf.writestr('medium.png', img_bytes.getvalue())

    zip_bytes = zip_buffer.getvalue()

    # With default max (8192), should not resize
    pdf_default = izip2pdf.convert(zip_bytes)

    # With custom smaller max (1000), should resize
    pdf_custom = izip2pdf.convert(zip_bytes, max_width=1000, max_height=1000)

    assert len(pdf_default) > 0
    assert len(pdf_custom) > 0


def test_alpha_mode_drop_no_error():
    """Test that drop mode works without errors."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Create RGBA image
        img = Image.new('RGBA', (100, 100), color=(255, 0, 0, 128))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        zf.writestr('alpha.png', img_bytes.getvalue())

    zip_bytes = zip_buffer.getvalue()

    # Should handle alpha channel drop without errors
    pdf_bytes = izip2pdf.convert(zip_bytes, alpha_mode="drop")
    assert len(pdf_bytes) > 0


def test_log_func_called_for_each_file():
    """Test that log function is called for each processed file."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for i in range(3):
            img = Image.new('RGB', (100, 100), color='red')
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            zf.writestr(f'image{i}.png', img_bytes.getvalue())

    zip_bytes = zip_buffer.getvalue()
    logged_messages = []

    def custom_log(msg: str) -> None:
        logged_messages.append(msg)

    pdf_bytes = izip2pdf.convert(zip_bytes, log_func=custom_log)

    assert len(pdf_bytes) > 0
    # Should have logged each file
    assert len(logged_messages) == 3
    assert any('image0.png' in msg for msg in logged_messages)
    assert any('image1.png' in msg for msg in logged_messages)
    assert any('image2.png' in msg for msg in logged_messages)


def test_progress_false_is_silent():
    """Test that progress=False produces no output."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        img = Image.new('RGB', (100, 100), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        zf.writestr('image.png', img_bytes.getvalue())

    zip_bytes = zip_buffer.getvalue()

    # This should complete silently
    pdf_bytes = izip2pdf.convert(zip_bytes, progress=False)
    assert len(pdf_bytes) > 0
