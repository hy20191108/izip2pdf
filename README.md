izip2pdf (image zip to pdf)
=======
This library convert zip file containing image file to pdf file.
- fast convert
- pdf page width is same
- This library convert on memory, not use tmp folder.

Support image format in zip
- jpeg, jpeg2000, png,  webp, avif, heif, psd, tiff, etc.

Usage
-----

	$ izip2pdf sample1.zip
    $ izip2pdf sample2.zip sample3.zip


As result, this library make sample1.pdf sample2.pdf sample3.pdf

In the case of Linux environment, you can use

	$ izip2pdf sample*.zip

Installation
------------

If you want to install, you can run:

	$ pip install izip2pdf

Library
-------

The package can also be used as a library:

### Basic Usage

```python
import izip2pdf

# usecase 1: file path to file path
izip2pdf.convert("input.zip", "output.pdf")

# usecase 2: bytes to file
with open("input.zip", "rb") as f:
    zip_bin = f.read()
izip2pdf.convert(zip_bin, "output/output2.pdf")

# usecase 3: file to bytes
pdf_bin = izip2pdf.convert("input.zip")
with open("output.pdf", "wb") as f:
    f.write(pdf_bin)

# usecase 4: bytes to bytes
with open("input.zip", "rb") as f:
    zip_bin = f.read()
pdf_bin = izip2pdf.convert(zip_bin)
with open("output.pdf", "wb") as f:
    f.write(pdf_bin)
```

### Advanced Options

```python
import izip2pdf

# With progress bar
izip2pdf.convert("input.zip", "output.pdf", progress=True)

# Custom JPEG quality and dimensions
izip2pdf.convert(
    "input.zip",
    "output.pdf",
    jpeg_quality=95,
    max_width=4096,
    max_height=4096
)

# Handle transparency with different background colors
izip2pdf.convert("input.zip", "output.pdf", alpha_mode="white")  # white background
izip2pdf.convert("input.zip", "output.pdf", alpha_mode="black")  # black background
izip2pdf.convert("input.zip", "output.pdf", alpha_mode="drop")   # drop alpha channel

# Error handling options
izip2pdf.convert("input.zip", "output.pdf", on_error="warn")   # warn and continue (default)
izip2pdf.convert("input.zip", "output.pdf", on_error="skip")   # silently skip errors
izip2pdf.convert("input.zip", "output.pdf", on_error="raise")  # raise exception on error
```

### Security Options

For processing untrusted ZIP files, you can configure safety limits:

```python
import izip2pdf

# Default: safe limits (recommended for untrusted input)
izip2pdf.convert("untrusted.zip", "output.pdf")  # Uses ~178MP pixel limit

# Custom pixel limit to prevent decompression bombs
izip2pdf.convert(
    "untrusted.zip",
    "output.pdf",
    max_image_pixels=100_000_000  # 100 megapixels max
)

# For trusted input only: disable limits (use with caution!)
izip2pdf.convert(
    "trusted.zip",
    "output.pdf",
    max_image_pixels=0,              # Disable pixel limit (WARNING: DoS risk!)
    load_truncated_images=True       # Allow incomplete images (WARNING: risky!)
)
```

**Security Notes:**
- By default, `izip2pdf` uses Pillow's safe limits (~178 megapixels) to protect against decompression bomb attacks
- Setting `max_image_pixels=0` disables this protection and may expose you to DoS attacks from malicious ZIP files
- Only disable safety limits when processing ZIP files from trusted sources


# Reference
- [img2pdf](https://github.com/myollie/img2pdf)