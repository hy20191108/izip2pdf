"""Basic tests that don't require external test data."""
import io
import zipfile

from PIL import Image

import izip2pdf


def create_test_zip_with_images():
    """Create a simple ZIP file with test images in memory."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Create a simple RGB image
        img1 = Image.new('RGB', (100, 100), color='red')
        img1_bytes = io.BytesIO()
        img1.save(img1_bytes, format='PNG')
        zf.writestr('image1.png', img1_bytes.getvalue())

        # Create an image with alpha channel
        img2 = Image.new('RGBA', (100, 100), color=(0, 0, 255, 128))
        img2_bytes = io.BytesIO()
        img2.save(img2_bytes, format='PNG')
        zf.writestr('image2.png', img2_bytes.getvalue())

        # Create another RGB image
        img3 = Image.new('RGB', (100, 100), color='green')
        img3_bytes = io.BytesIO()
        img3.save(img3_bytes, format='JPEG')
        zf.writestr('image3.jpg', img3_bytes.getvalue())

    return zip_buffer.getvalue()


def test_convert_basic():
    """Test basic conversion functionality."""
    zip_bytes = create_test_zip_with_images()
    pdf_bytes = izip2pdf.convert(zip_bytes)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b'%PDF')  # PDF magic number


def test_convert_with_progress_modes():
    """Test different progress modes."""
    zip_bytes = create_test_zip_with_images()

    # Silent mode (default)
    pdf1 = izip2pdf.convert(zip_bytes, progress=False)
    assert len(pdf1) > 0

    # Progress bar mode
    pdf2 = izip2pdf.convert(zip_bytes, progress="bar")
    assert len(pdf2) > 0

    # Progress with log mode
    pdf3 = izip2pdf.convert(zip_bytes, progress="log")
    assert len(pdf3) > 0


def test_convert_with_log_func():
    """Test custom log function."""
    zip_bytes = create_test_zip_with_images()
    logged_messages = []

    def custom_log(msg: str) -> None:
        logged_messages.append(msg)

    pdf_bytes = izip2pdf.convert(zip_bytes, log_func=custom_log)

    assert len(pdf_bytes) > 0
    assert len(logged_messages) > 0
    # Should have logged file names
    assert any('image' in msg for msg in logged_messages)


def test_convert_with_quality_settings():
    """Test different JPEG quality settings."""
    zip_bytes = create_test_zip_with_images()

    # Low quality
    pdf_low = izip2pdf.convert(zip_bytes, jpeg_quality=50)

    # High quality
    pdf_high = izip2pdf.convert(zip_bytes, jpeg_quality=95)

    assert len(pdf_low) > 0
    assert len(pdf_high) > 0
    # Higher quality typically results in larger files
    # (not always guaranteed with small test images, so we just check both work)


def test_convert_with_max_dimensions():
    """Test custom max width/height."""
    zip_bytes = create_test_zip_with_images()

    pdf_bytes = izip2pdf.convert(
        zip_bytes,
        max_width=4096,
        max_height=4096
    )

    assert len(pdf_bytes) > 0


def test_convert_with_rotate_exif():
    """Test EXIF rotation control."""
    zip_bytes = create_test_zip_with_images()

    # With rotation
    pdf_with = izip2pdf.convert(zip_bytes, rotate_exif=True)

    # Without rotation
    pdf_without = izip2pdf.convert(zip_bytes, rotate_exif=False)

    assert len(pdf_with) > 0
    assert len(pdf_without) > 0


def test_convert_with_alpha_modes():
    """Test different alpha channel handling modes."""
    zip_bytes = create_test_zip_with_images()

    # White background (default)
    pdf_white = izip2pdf.convert(zip_bytes, alpha_mode="white")

    # Black background
    pdf_black = izip2pdf.convert(zip_bytes, alpha_mode="black")

    # Drop alpha
    pdf_drop = izip2pdf.convert(zip_bytes, alpha_mode="drop")

    assert len(pdf_white) > 0
    assert len(pdf_black) > 0
    assert len(pdf_drop) > 0


def test_convert_with_error_handling():
    """Test different error handling modes."""
    zip_bytes = create_test_zip_with_images()

    # Warn mode (default)
    pdf_warn = izip2pdf.convert(zip_bytes, on_error="warn")
    assert len(pdf_warn) > 0

    # Skip mode
    pdf_skip = izip2pdf.convert(zip_bytes, on_error="skip")
    assert len(pdf_skip) > 0

    # Raise mode
    pdf_raise = izip2pdf.convert(zip_bytes, on_error="raise")
    assert len(pdf_raise) > 0


def test_convert_with_output_path(tmp_path):
    """Test writing to output file."""
    zip_bytes = create_test_zip_with_images()
    output_path = tmp_path / "test_output.pdf"

    pdf_bytes = izip2pdf.convert(zip_bytes, str(output_path))

    # Should return bytes
    assert len(pdf_bytes) > 0

    # Should also write to file
    assert output_path.exists()
    assert output_path.stat().st_size > 0

    # File contents should match returned bytes
    with open(output_path, 'rb') as f:
        file_contents = f.read()
    assert file_contents == pdf_bytes


def test_convert_combined_parameters():
    """Test using multiple parameters together."""
    zip_bytes = create_test_zip_with_images()
    logged_messages = []

    def custom_log(msg: str) -> None:
        logged_messages.append(msg)

    pdf_bytes = izip2pdf.convert(
        zip_bytes,
        progress=False,
        log_func=custom_log,
        jpeg_quality=90,
        max_width=2048,
        max_height=2048,
        rotate_exif=True,
        alpha_mode="white",
        on_error="warn",
    )

    assert len(pdf_bytes) > 0
    assert len(logged_messages) > 0
