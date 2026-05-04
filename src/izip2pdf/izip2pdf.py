"""izip2pdf: convert ZIP of images to PDF, in-memory."""

import io
import sys
import warnings
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, List, Literal, Optional, Union

import img2pdf  # type: ignore[import-untyped]
import tqdm  # type: ignore[import-untyped]
from natsort import natsorted  # type: ignore[import-untyped]
from PIL import Image, ImageFile, ImageOps  # type: ignore[import-untyped]

# Pillow safety defaults (override via convert(max_image_pixels=...))
DEFAULT_MAX_IMAGE_PIXELS = 178956970  # Pillow's default ~178MP

# JPEG dimension cap. The JPEG spec allows 65535, but 8192 is the practical
# safe limit for downstream viewers/embedders.
DEFAULT_JPEG_DIMENSION = 8192

AlphaMode = Literal["white", "black", "drop"]
ErrorMode = Literal["raise", "skip", "warn"]
ProgressMode = Union[bool, Literal["bar", "log"]]

_format_support_initialized = False
_a4_layout: Optional[Callable[..., bytes]] = None


def _ensure_format_support() -> None:
    """Lazily register HEIF and AVIF Pillow plugins.

    These have global side effects (modifying Pillow's format registry),
    so we defer registration until the first convert() call rather than
    importing them at module load time.
    """
    global _format_support_initialized
    if _format_support_initialized:
        return
    import pillow_avif  # type: ignore[import-untyped] # noqa: F401
    from pillow_heif import register_heif_opener  # type: ignore[import-untyped]
    register_heif_opener()
    _format_support_initialized = True


def _get_a4_layout() -> Callable[..., bytes]:
    """Lazily build the A4 page-layout function used by img2pdf."""
    global _a4_layout
    if _a4_layout is None:
        _a4_layout = img2pdf.get_layout_fun((img2pdf.mm_to_pt(210), None))
    return _a4_layout


@contextmanager
def configure_pillow_safety(
    max_image_pixels: Optional[int] = None,
    load_truncated_images: bool = False,
) -> Iterator[None]:
    """Temporarily configure Pillow's process-wide safety settings.

    Pillow stores these as module attributes, so this manager saves and
    restores the previous values to avoid leaking changes across calls.

    Note: not thread-safe. In multi-threaded apps, set Pillow's globals
    once at startup instead of using this manager.

    Args:
        max_image_pixels: Cap on total pixels per image to defeat
            decompression-bomb attacks.
            None  -> Pillow's safe default (~178MP)
            0     -> no cap (UNSAFE; only for trusted input)
            other -> custom cap
        load_truncated_images: Allow loading truncated/incomplete images.
            False (default) is safer.
    """
    saved_pixels = Image.MAX_IMAGE_PIXELS
    saved_truncated = ImageFile.LOAD_TRUNCATED_IMAGES

    if max_image_pixels is None:
        Image.MAX_IMAGE_PIXELS = DEFAULT_MAX_IMAGE_PIXELS
    elif max_image_pixels == 0:
        Image.MAX_IMAGE_PIXELS = None
    else:
        Image.MAX_IMAGE_PIXELS = max_image_pixels
    ImageFile.LOAD_TRUNCATED_IMAGES = load_truncated_images

    try:
        yield
    finally:
        Image.MAX_IMAGE_PIXELS = saved_pixels
        ImageFile.LOAD_TRUNCATED_IMAGES = saved_truncated


def _has_alpha(image: Image.Image) -> bool:
    """Whether the image carries an alpha channel.

    Distinguishes from CMYK (which is also 4 channels but no alpha).
    """
    if image.mode in ("RGBA", "LA", "PA", "RGBa", "La"):
        return True
    if image.mode == "CMYK":
        return False
    n = len(image.split())
    if n >= 5:
        raise ValueError(f"Unexpected number of image channels: {n}")
    return n == 4


def _alpha_mask(image: Image.Image) -> Image.Image:
    """Return the alpha channel of an image (mask for paste()).

    Handles RGBA (4 channels, alpha at index 3) and LA/PA (2 channels,
    alpha at index 1). Falls back to RGBA conversion for other modes.
    """
    if image.mode in ("RGBA", "RGBa"):
        return image.split()[3]
    if image.mode in ("LA", "La", "PA"):
        return image.split()[1]
    # Unknown alpha mode: convert to RGBA and extract from there
    return image.convert("RGBA").split()[3]


def _flatten_alpha(image: Image.Image, mode: AlphaMode) -> Image.Image:
    """Composite an alpha image onto a solid background, or drop alpha."""
    if mode == "drop":
        return image.convert("RGB")

    image.load()  # required before split() on PNGs
    bg_color = (0, 0, 0) if mode == "black" else (255, 255, 255)
    background = Image.new("RGB", image.size, bg_color)
    background.paste(image, mask=_alpha_mask(image))
    return background


def _scaled_dimensions(
    width: int, height: int, max_width: int, max_height: int
) -> tuple[int, int]:
    """Return (w, h) constrained to (max_width, max_height), aspect-preserved.

    Output dimensions are rounded down to even numbers for codec friendliness.
    """
    if width > max_width:
        height = int(height * max_width / width / 2) * 2
        width = max_width
    if height > max_height:
        width = int(width * max_height / height / 2) * 2
        height = max_height
    return width, height


def _should_apply_exif_rotation(filename: str) -> bool:
    """PSD/WebP carry orientation differently or not at all; skip them."""
    return Path(filename).suffix.lower() not in (".psd", ".webp")


def to_jpeg_bytes(
    name: str,
    image_bytes: bytes,
    *,
    quality: int = 85,
    max_width: int = DEFAULT_JPEG_DIMENSION,
    max_height: int = DEFAULT_JPEG_DIMENSION,
    rotate_exif: bool = True,
    alpha_mode: AlphaMode = "white",
) -> bytes:
    """Convert one image's bytes into JPEG bytes ready for PDF embedding.

    Calls `_ensure_format_support()` to register HEIF/AVIF Pillow plugins on
    first invocation (idempotent). Wrap the call in `configure_pillow_safety(...)`
    when stricter Pillow safety limits are required.
    """
    _ensure_format_support()
    output = io.BytesIO()
    with Image.open(io.BytesIO(image_bytes)) as image:
        w, h = image.size
        new_size = _scaled_dimensions(w, h, max_width, max_height)
        if new_size != image.size:
            image = image.resize(new_size, Image.Resampling.LANCZOS)

        if rotate_exif and _should_apply_exif_rotation(name):
            rotated = ImageOps.exif_transpose(image)
            if rotated is not None:
                image = rotated

        if _has_alpha(image):
            image = _flatten_alpha(image, alpha_mode)
        else:
            image = image.convert("RGB")

        image.save(output, "jpeg", quality=quality, optimize=True)
    return output.getvalue()


def _read_zip_input(zip_input: Union[str, bytes]) -> bytes:
    if isinstance(zip_input, bytes):
        return zip_input
    with open(zip_input, "rb") as f:
        return f.read()


def _emit(
    message: str,
    on_error: ErrorMode,
    log_func: Optional[Callable[[str], None]],
) -> None:
    """Emit a per-file error message according to on_error policy."""
    if on_error == "warn":
        warnings.warn(message)
        if log_func is not None:
            log_func(f"WARNING: {message}")
    else:  # "skip"
        if log_func is not None:
            log_func(f"SKIPPED: {message}")


def convert(
    zip_input: Union[str, bytes],
    output_pdf_path: Optional[str] = None,
    progress: ProgressMode = False,
    *,
    log_func: Optional[Callable[[str], None]] = None,
    jpeg_quality: int = 85,
    max_width: int = DEFAULT_JPEG_DIMENSION,
    max_height: int = DEFAULT_JPEG_DIMENSION,
    rotate_exif: bool = True,
    alpha_mode: AlphaMode = "white",
    on_error: ErrorMode = "warn",
    max_image_pixels: Optional[int] = None,
    load_truncated_images: bool = False,
) -> bytes:
    """Convert a ZIP of images into a PDF, entirely in memory.

    Args:
        zip_input: Path to a ZIP file, or its bytes.
        output_pdf_path: If given, write the PDF there as well as returning it.
        progress: False/True/"bar"/"log" for tqdm display modes.
        log_func: Receives every filename and warning text.
        jpeg_quality: JPEG quality 0-100.
        max_width, max_height: Cap on each dimension after resize.
        rotate_exif: Apply EXIF orientation correction.
        alpha_mode: "white"/"black"/"drop" for transparent images.
        on_error: "raise"/"skip"/"warn" for per-image failures.
        max_image_pixels: Decompression-bomb guard (None=Pillow default,
                          0=disabled).
        load_truncated_images: Allow truncated images.

    Returns:
        PDF as bytes. b"" if no images converted and on_error != "raise".
    """
    _ensure_format_support()

    show_bar = progress in (True, "bar", "log")
    show_log = progress == "log"

    pages: List[bytes] = []

    with configure_pillow_safety(max_image_pixels, load_truncated_images), \
         zipfile.ZipFile(io.BytesIO(_read_zip_input(zip_input))) as src:
        names = list(natsorted(src.namelist()))
        names_iter = tqdm.tqdm(names, desc="izip2pdf") if show_bar else names

        for name in names_iter:
            if zipfile.Path(src, name).is_dir():
                continue
            if show_log:
                tqdm.tqdm.write(name)
            if log_func is not None:
                log_func(name)

            try:
                pages.append(to_jpeg_bytes(
                    name, src.read(name),
                    quality=jpeg_quality,
                    max_width=max_width,
                    max_height=max_height,
                    rotate_exif=rotate_exif,
                    alpha_mode=alpha_mode,
                ))
            except Exception as e:
                if on_error == "raise":
                    raise
                _emit(f"Error processing {name}: {e}", on_error, log_func)

    if not pages:
        msg = "No valid images found in ZIP file"
        if on_error == "raise":
            raise ValueError(msg)
        _emit(msg, on_error, log_func)
        return b""

    pdf_bytes: bytes = img2pdf.convert(pages, layout_fun=_get_a4_layout())

    if output_pdf_path is not None:
        with open(output_pdf_path, "wb") as f:
            f.write(pdf_bytes)

    return pdf_bytes


# --- Backwards-compatible classes (deprecated since v0.2.0) ---
# Kept so that existing code importing ImageProcessor / ZipToPdfConverter
# continues to work. New code should call convert() directly.

class ImageProcessor:
    """Deprecated since v0.2.0; call izip2pdf.to_jpeg_bytes() instead."""

    def __init__(
        self,
        jpeg_quality: int = 85,
        max_width: int = DEFAULT_JPEG_DIMENSION,
        max_height: int = DEFAULT_JPEG_DIMENSION,
        rotate_exif: bool = True,
        alpha_mode: AlphaMode = "white",
        max_image_pixels: Optional[int] = None,
        load_truncated_images: bool = False,
    ):
        self.jpeg_quality = jpeg_quality
        self.max_width = max_width
        self.max_height = max_height
        self.rotate_exif = rotate_exif
        self.alpha_mode = alpha_mode
        self.max_image_pixels = max_image_pixels
        self.load_truncated_images = load_truncated_images

    def get_dstbytes(self, name: str, input_image_bytes: bytes) -> bytes:
        with configure_pillow_safety(
            self.max_image_pixels, self.load_truncated_images
        ):
            return to_jpeg_bytes(
                name, input_image_bytes,
                quality=self.jpeg_quality,
                max_width=self.max_width,
                max_height=self.max_height,
                rotate_exif=self.rotate_exif,
                alpha_mode=self.alpha_mode,
            )


class ZipToPdfConverter:
    """Deprecated since v0.2.0; call izip2pdf.convert() instead."""

    def __init__(
        self,
        zip_path: Union[str, bytes],
        pdf_path: Optional[str] = None,
        progress: ProgressMode = False,
        log_func: Optional[Callable[[str], None]] = None,
        jpeg_quality: int = 85,
        max_width: int = DEFAULT_JPEG_DIMENSION,
        max_height: int = DEFAULT_JPEG_DIMENSION,
        rotate_exif: bool = True,
        alpha_mode: AlphaMode = "white",
        on_error: ErrorMode = "warn",
        max_image_pixels: Optional[int] = None,
        load_truncated_images: bool = False,
    ):
        self.zip_path = zip_path
        self.pdf_path = pdf_path
        self.progress = progress
        self.log_func = log_func
        self.jpeg_quality = jpeg_quality
        self.max_width = max_width
        self.max_height = max_height
        self.rotate_exif = rotate_exif
        self.alpha_mode = alpha_mode
        self.on_error = on_error
        self.max_image_pixels = max_image_pixels
        self.load_truncated_images = load_truncated_images

    def convert(self) -> bytes:
        return convert(
            self.zip_path,
            self.pdf_path,
            self.progress,
            log_func=self.log_func,
            jpeg_quality=self.jpeg_quality,
            max_width=self.max_width,
            max_height=self.max_height,
            rotate_exif=self.rotate_exif,
            alpha_mode=self.alpha_mode,
            on_error=self.on_error,
            max_image_pixels=self.max_image_pixels,
            load_truncated_images=self.load_truncated_images,
        )


def main() -> None:
    """CLI: izip2pdf <zip>... — convert each ZIP to <name>.pdf."""
    for zippath in tqdm.tqdm(sys.argv[1:], desc="process"):
        tqdm.tqdm.write(zippath)
        pdfpath = Path(zippath).with_suffix(".pdf")
        if pdfpath.is_file():
            continue
        convert(zippath, str(pdfpath), progress=True)


if __name__ == "__main__":
    main()
