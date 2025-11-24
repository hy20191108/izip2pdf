"""Integration tests that require actual test data files.

These tests are skipped if the input directory doesn't exist.
For unit tests that don't require external files, see test_basic.py.
"""
import io
import zipfile
from pathlib import Path

import pytest
from PIL import Image

import izip2pdf


def create_test_zip_with_images():
    """Create a test ZIP file with various image types."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # RGB image
        img1 = Image.new('RGB', (200, 200), color='red')
        img1_bytes = io.BytesIO()
        img1.save(img1_bytes, format='PNG')
        zf.writestr('image1.png', img1_bytes.getvalue())

        # RGBA image
        img2 = Image.new('RGBA', (200, 200), color=(0, 0, 255, 128))
        img2_bytes = io.BytesIO()
        img2.save(img2_bytes, format='PNG')
        zf.writestr('image2.png', img2_bytes.getvalue())

        # JPEG image
        img3 = Image.new('RGB', (200, 200), color='green')
        img3_bytes = io.BytesIO()
        img3.save(img3_bytes, format='JPEG')
        zf.writestr('image3.jpg', img3_bytes.getvalue())

    return zip_buffer.getvalue()


def test_izip2pdf_with_generated_data(tmp_path):
    """Test basic conversion with generated test data."""
    zip_bin = create_test_zip_with_images()

    # Test with bytes input and file output
    output1 = tmp_path / "output1.pdf"
    pdf_bytes1 = izip2pdf.convert(zip_bin, str(output1))
    assert len(pdf_bytes1) > 0
    assert pdf_bytes1.startswith(b'%PDF')
    assert output1.exists()
    assert output1.stat().st_size > 0

    # Test with bytes input only
    pdf_bytes2 = izip2pdf.convert(zip_bin)
    assert len(pdf_bytes2) > 0
    assert pdf_bytes2.startswith(b'%PDF')

    # Test with file input
    zip_file = tmp_path / "input.zip"
    zip_file.write_bytes(zip_bin)
    output2 = tmp_path / "output2.pdf"
    pdf_bytes3 = izip2pdf.convert(str(zip_file), str(output2))
    assert len(pdf_bytes3) > 0
    assert output2.exists()


def test_new_parameters_with_assertions(tmp_path):
    """Test new parameters with meaningful assertions."""
    zip_bin = create_test_zip_with_images()

    # Test with progress=False (silent mode)
    pdf_silent = izip2pdf.convert(zip_bin, progress=False)
    assert len(pdf_silent) > 0
    assert pdf_silent.startswith(b'%PDF')

    # Test with custom log function
    logged_messages = []

    def custom_log(msg: str) -> None:
        logged_messages.append(msg)

    pdf_with_log = izip2pdf.convert(zip_bin, log_func=custom_log)
    assert len(pdf_with_log) > 0
    assert len(logged_messages) >= 3  # Should log each of 3 images
    assert any('image1.png' in msg for msg in logged_messages)
    assert any('image2.png' in msg for msg in logged_messages)
    assert any('image3.jpg' in msg for msg in logged_messages)

    # Test with different JPEG quality
    pdf_low = izip2pdf.convert(zip_bin, jpeg_quality=50)
    pdf_high = izip2pdf.convert(zip_bin, jpeg_quality=95)
    assert len(pdf_low) > 0
    assert len(pdf_high) > 0
    # Lower quality typically produces smaller files, but not guaranteed with small test images
    # So we just verify both work

    # Test with custom max dimensions
    pdf_small_max = izip2pdf.convert(zip_bin, max_width=100, max_height=100)
    assert len(pdf_small_max) > 0

    # Test with EXIF rotation disabled
    pdf_no_rotate = izip2pdf.convert(zip_bin, rotate_exif=False)
    assert len(pdf_no_rotate) > 0

    # Test with different alpha modes
    pdf_alpha_white = izip2pdf.convert(zip_bin, alpha_mode="white")
    pdf_alpha_black = izip2pdf.convert(zip_bin, alpha_mode="black")
    pdf_alpha_drop = izip2pdf.convert(zip_bin, alpha_mode="drop")
    assert len(pdf_alpha_white) > 0
    assert len(pdf_alpha_black) > 0
    assert len(pdf_alpha_drop) > 0
    # Different alpha modes should produce different results
    assert pdf_alpha_white != pdf_alpha_black

    # Test with output file
    output_path = tmp_path / "test_output.pdf"
    pdf_with_file = izip2pdf.convert(zip_bin, str(output_path))
    assert len(pdf_with_file) > 0
    assert output_path.exists()
    # Verify file content matches returned bytes
    with open(output_path, 'rb') as f:
        assert f.read() == pdf_with_file


@pytest.mark.skipif(
    not Path("input/input1.zip").exists(),
    reason="Test data not available (input/input1.zip not found)"
)
def test_izip2pdf_with_real_data(tmp_path):
    """Test with real data files if available.

    This test is skipped if the input directory doesn't exist.
    Expects test files named input1.zip through input7.zip in the input/ directory.
    """
    # Test all input files that exist (input1.zip through input7.zip)
    for i in range(1, 8):
        input_file = f"input/input{i}.zip"
        if not Path(input_file).exists():
            continue

        # Test with file path
        output = tmp_path / f"output{i}.pdf"
        pdf_bytes = izip2pdf.convert(input_file, str(output))
        assert output.exists()
        assert output.stat().st_size > 0
        assert len(pdf_bytes) > 0
        assert pdf_bytes.startswith(b'%PDF')

        # Test with bytes input
        with open(input_file, "rb") as f:
            zip_bin = f.read()
        pdf_bytes_from_bytes = izip2pdf.convert(zip_bin)
        assert len(pdf_bytes_from_bytes) > 0
        assert pdf_bytes_from_bytes.startswith(b'%PDF')
