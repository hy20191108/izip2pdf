#!/usr/bin/python3
# -*- coding: utf-8 -*-
import io
import sys
import warnings
import zipfile
from pathlib import Path
from typing import Callable, Literal, Optional, Union, List

import img2pdf  # type: ignore[import-untyped]
import pillow_avif  # type: ignore[import-untyped]  # noqa: F401
import tqdm  # type: ignore[import-untyped]
from natsort import natsorted  # type: ignore[import-untyped]
from PIL import Image, ImageFile, ImageOps  # type: ignore[import-untyped]
from pillow_heif import register_heif_opener  # type: ignore[import-untyped]
register_heif_opener()

# Default Pillow safety settings (can be overridden in ImageProcessor)
# Note: Setting MAX_IMAGE_PIXELS too high can lead to DoS attacks
DEFAULT_MAX_IMAGE_PIXELS = 178956970  # Pillow's default (~ 178 megapixels)
DEFAULT_LOAD_TRUNCATED_IMAGES = False  # Pillow's default

MAX_WIDTH = 8192  # limit of jpg format
MAX_HEIGHT = 8192  # limit of jpg format
layout_fun = img2pdf.get_layout_fun((img2pdf.mm_to_pt(210), None))  # A4


class ImageProcessor:
    def __init__(
        self,
        jpeg_quality: int = 85,
        max_width: int = 8192,
        max_height: int = 8192,
        rotate_exif: bool = True,
        alpha_mode: Literal["white", "black", "drop"] = "white",
        max_image_pixels: Optional[int] = None,
        load_truncated_images: bool = False,
    ):
        """Initialize ImageProcessor with safety and processing settings.

        Args:
            jpeg_quality: JPEG quality for output (0-100)
            max_width: Maximum image width in pixels
            max_height: Maximum image height in pixels
            rotate_exif: Apply EXIF rotation
            alpha_mode: How to handle transparency
            max_image_pixels: Maximum total pixels to prevent decompression bombs.
                             None = use Pillow's default (~178MP). Set to 0 to disable limit.
                             WARNING: Disabling this limit may expose you to DoS attacks.
            load_truncated_images: Allow loading truncated/incomplete images.
                                  False = reject incomplete images (safer).
                                  True = attempt to load partial data (risky).
        """
        self.jpeg_quality = jpeg_quality
        self.max_width = max_width
        self.max_height = max_height
        self.rotate_exif = rotate_exif
        self.alpha_mode = alpha_mode
        self.max_image_pixels = max_image_pixels
        self.load_truncated_images = load_truncated_images

        # Apply Pillow safety settings
        self._configure_pillow_limits()

    def _configure_pillow_limits(self) -> None:
        """Configure Pillow's safety limits for this processor instance.

        Note: These are global settings in Pillow, so they affect all Image operations.
        In multi-threaded environments, consider setting these at application startup.
        """
        # Configure pixel limit
        if self.max_image_pixels is None:
            # Use Pillow's default (safe)
            Image.MAX_IMAGE_PIXELS = DEFAULT_MAX_IMAGE_PIXELS
        elif self.max_image_pixels == 0:
            # Disable limit entirely (UNSAFE - use only for trusted input)
            Image.MAX_IMAGE_PIXELS = None
        else:
            # Use custom limit
            Image.MAX_IMAGE_PIXELS = self.max_image_pixels

        # Configure truncated image handling
        ImageFile.LOAD_TRUNCATED_IMAGES = self.load_truncated_images

    def need_rotate(self, filename: str) -> bool:
        """Check if image should be rotated based on EXIF data."""
        return Path(filename).suffix.lower() not in [".psd", ".webp"]

    @staticmethod
    def rotate_image(image: Image.Image) -> Image.Image:
        """Rotate image based on EXIF orientation data."""
        result = ImageOps.exif_transpose(image)
        return result if result is not None else image

    def is_alpha_image(self, image: Image.Image) -> bool:
        """Check if image has an alpha channel.

        Note: This distinguishes between CMYK (4 channels, no alpha)
        and RGBA/LA (4/2 channels with alpha).
        """
        # Check if the image mode explicitly includes alpha
        # Modes with alpha: RGBA, LA, PA, RGBa, La
        if image.mode in ("RGBA", "LA", "PA", "RGBa", "La"):
            return True

        # CMYK and other 4-channel modes without alpha
        if image.mode == "CMYK":
            return False

        # Fallback: check channel count, but only for unexpected modes
        length = len(image.split())
        if length >= 5:
            raise ValueError(f"Unexpected number of image channels: {length}")

        # For other modes, 4 channels likely means alpha (but CMYK handled above)
        return length == 4

    def process_alpha(self, image: Image.Image) -> Image.Image:
        """Process image with alpha channel according to alpha_mode setting."""
        if self.alpha_mode == "drop":
            # Drop alpha channel and convert directly
            return image.convert("RGB")

        image.load()  # required for png.split()
        background_color = (0, 0, 0) if self.alpha_mode == "black" else (255, 255, 255)
        background = Image.new("RGB", image.size, background_color)
        background.paste(image, mask=image.split()[3])  # 3 is alpha channel
        image.close()
        return background

    @staticmethod
    def _calc_scaled_dimension(
        original_size: int, other_size: int, target_size: int
    ) -> tuple[int, int]:
        """Calculate scaled dimensions maintaining aspect ratio.

        Args:
            original_size: The dimension being constrained (width or height)
            other_size: The other dimension
            target_size: The maximum allowed size for original_size

        Returns:
            Tuple of (target_size, scaled_other_size) with even dimensions
        """
        scaled_other = int(other_size * target_size / original_size / 2) * 2
        return target_size, scaled_other

    def fix_too_long_size(self, w: int, h: int) -> tuple[int, int]:
        """Constrain image dimensions to max_width and max_height."""
        if w > self.max_width:
            w, h = self._calc_scaled_dimension(w, h, self.max_width)
        if h > self.max_height:
            h, w = self._calc_scaled_dimension(h, w, self.max_height)
        return w, h

    def resize_image(self, image: Image.Image) -> Image.Image:
        """Resize image if it exceeds maximum dimensions."""
        old_w, old_h = image.size
        new_w, new_h = self.fix_too_long_size(old_w, old_h)
        return image.resize((new_w, new_h), Image.Resampling.LANCZOS)

    def get_dstbytes(self, name: str, input_image_bytes: bytes) -> bytes:
        """Process image bytes and convert to JPEG format for PDF embedding.

        Args:
            name: Filename (used for EXIF rotation decision)
            input_image_bytes: Raw image data

        Returns:
            JPEG-encoded image bytes
        """
        content_io = io.BytesIO(input_image_bytes)
        storage_io = io.BytesIO()
        image = None

        try:
            image = Image.open(content_io)

            w, h = image.size
            if (w > self.max_width) or (h > self.max_height):
                image = self.resize_image(image)

            if self.rotate_exif and self.need_rotate(name):
                image = self.rotate_image(image)

            if self.is_alpha_image(image):
                image = self.process_alpha(image)
            else:
                image = image.convert("RGB")

            image.save(storage_io, "jpeg", quality=self.jpeg_quality, optimize=True)
            output_image_bin = storage_io.getvalue()
            return output_image_bin

        finally:
            # Ensure all resources are closed even if an exception occurs
            if image is not None:
                image.close()
            content_io.close()
            storage_io.close()


class ZipToPdfConverter:
    def __init__(
        self,
        zip_path: Union[str, bytes],
        pdf_path: Optional[str] = None,
        progress: Union[bool, Literal["bar", "log"]] = False,
        log_func: Optional[Callable[[str], None]] = None,
        jpeg_quality: int = 85,
        max_width: int = 8192,
        max_height: int = 8192,
        rotate_exif: bool = True,
        alpha_mode: Literal["white", "black", "drop"] = "white",
        on_error: Literal["raise", "skip", "warn"] = "warn",
        max_image_pixels: Optional[int] = None,
        load_truncated_images: bool = False,
    ):
        self.zip_path: Union[str, bytes] = zip_path
        self.pdf_path: Optional[str] = pdf_path
        self.progress: Union[bool, Literal["bar", "log"]] = progress
        self.log_func: Optional[Callable[[str], None]] = log_func
        self.on_error: Literal["raise", "skip", "warn"] = on_error
        self.image_processor = ImageProcessor(
            jpeg_quality=jpeg_quality,
            max_width=max_width,
            max_height=max_height,
            rotate_exif=rotate_exif,
            alpha_mode=alpha_mode,
            max_image_pixels=max_image_pixels,
            load_truncated_images=load_truncated_images,
        )

    def _log(self, message: str) -> None:
        """Log a message using the configured log function."""
        if self.log_func is not None:
            self.log_func(message)

    def _handle_error(self, error_msg: str, raise_exception: Optional[Exception] = None) -> None:
        """Handle errors based on on_error setting.

        Args:
            error_msg: Error message to log/warn
            raise_exception: Optional exception to raise in "raise" mode
        """
        if self.on_error == "raise":
            if raise_exception is not None:
                raise raise_exception
            raise RuntimeError(error_msg)
        elif self.on_error == "warn":
            warnings.warn(error_msg)
            self._log(f"WARNING: {error_msg}")
        else:  # skip
            self._log(f"SKIPPED: {error_msg}")

    def convert(self) -> bytes:
        zipbytes = self._read_zip()
        zip_io = io.BytesIO(zipbytes)
        dstbytes_list: List[bytes] = []

        with zipfile.ZipFile(zip_io) as z:
            namelist = list(natsorted(z.namelist()))

            # Determine if we should show progress bar
            show_bar = self.progress in (True, "bar", "log")
            show_log = self.progress == "log"

            if show_bar:
                namelist_iter = tqdm.tqdm(namelist, desc="izip2pdf")
            else:
                namelist_iter = namelist

            for name in namelist_iter:
                # Use ZipFile context for directory check
                if zipfile.Path(z, name).is_dir():
                    continue

                # Log file processing if enabled
                if show_log:
                    tqdm.tqdm.write(name)
                self._log(name)

                try:
                    srcbytes = z.read(name)
                    dstbytes = self.image_processor.get_dstbytes(name, srcbytes)
                    dstbytes_list.append(dstbytes)
                except Exception as e:
                    if self.on_error == "raise":
                        raise
                    error_msg = f"Error processing {name}: {e}"
                    self._handle_error(error_msg)

        zip_io.close()

        # Handle empty image list
        if not dstbytes_list:
            error_msg = "No valid images found in ZIP file"
            self._handle_error(error_msg, ValueError(error_msg))
            return b""

        pdfbytes = img2pdf.convert(dstbytes_list, layout_fun=layout_fun)

        if self.pdf_path is not None:
            with open(self.pdf_path, "wb") as f:
                f.write(pdfbytes)

        return pdfbytes

    def _read_zip(self) -> bytes:
        if isinstance(self.zip_path, bytes):
            return self.zip_path
        else:
            with open(self.zip_path, "rb") as f:
                return f.read()


def convert(
    zip_input: Union[str, bytes],
    output_pdf_path: Optional[str] = None,
    progress: Union[bool, Literal["bar", "log"]] = False,
    *,
    log_func: Optional[Callable[[str], None]] = None,
    jpeg_quality: int = 85,
    max_width: int = 8192,
    max_height: int = 8192,
    rotate_exif: bool = True,
    alpha_mode: Literal["white", "black", "drop"] = "white",
    on_error: Literal["raise", "skip", "warn"] = "warn",
    max_image_pixels: Optional[int] = None,
    load_truncated_images: bool = False,
) -> bytes:
    """Convert a ZIP (file path or bytes) containing images into a PDF.

    When output_pdf_path is provided, the PDF is written to that path and
    the PDF bytes are also returned.

    Args:
        zip_input: Path to ZIP file or ZIP file as bytes
        output_pdf_path: Optional path to write the output PDF
        progress: Control progress display. False (default) = silent, True/"bar" = show bar only,
                  "log" = show bar + file names
        log_func: Optional callable to receive log messages (file names, warnings)
        jpeg_quality: JPEG quality for image conversion (default: 85)
        max_width: Maximum image width in pixels (default: 8192)
        max_height: Maximum image height in pixels (default: 8192)
        rotate_exif: Whether to rotate images based on EXIF data (default: True)
        alpha_mode: How to handle transparency: "white" (default), "black", or "drop"
        on_error: Error handling: "warn" (default), "skip", or "raise"
        max_image_pixels: Maximum total pixels to prevent decompression bombs.
                         None (default) = use Pillow's default (~178MP). Set to 0 to disable.
                         WARNING: Disabling may expose you to DoS attacks.
        load_truncated_images: Allow loading truncated/incomplete images (default: False, safer)

    Returns:
        PDF file as bytes
    """
    converter = ZipToPdfConverter(
        zip_input,
        output_pdf_path,
        progress=progress,
        log_func=log_func,
        jpeg_quality=jpeg_quality,
        max_width=max_width,
        max_height=max_height,
        rotate_exif=rotate_exif,
        alpha_mode=alpha_mode,
        on_error=on_error,
        max_image_pixels=max_image_pixels,
        load_truncated_images=load_truncated_images,
    )
    return converter.convert()


def main() -> None:
    for zippath in tqdm.tqdm(sys.argv[1:], desc="process"):
        tqdm.tqdm.write(zippath)
        pdfpath = Path(zippath).with_suffix(".pdf")
        if pdfpath.is_file():
            continue
        try:
            converter = ZipToPdfConverter(zippath, str(pdfpath), progress=True)
            converter.convert()
        except KeyboardInterrupt:
            exit()


if __name__ == "__main__":
    main()
