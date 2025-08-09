#!/usr/bin/python3
# -*- coding: utf-8 -*-
import io
import sys
import zipfile
from pathlib import Path
from typing import Optional, Union, List

import img2pdf  # type: ignore[import-untyped]
import pillow_avif  # type: ignore[import-untyped]  # noqa: F401
import tqdm  # type: ignore[import-untyped]
from natsort import natsorted  # type: ignore[import-untyped]
from PIL import Image, ImageFile, ImageOps  # type: ignore[import-untyped]
from pillow_heif import register_heif_opener  # type: ignore[import-untyped]
register_heif_opener()
ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = 10**1000
MAX_WIDTH = 8192  # limit of jpg format
MAX_HEIGHT = 8192  # limit of jpg format
layout_fun = img2pdf.get_layout_fun((img2pdf.mm_to_pt(210), None))  # A4


class ImageProcessor:
    @staticmethod
    def need_rotate(filename):
        return Path(filename).suffix.lower() not in [".psd", ".webp"]

    @staticmethod
    def rotate_image(image):
        return ImageOps.exif_transpose(image)

    @staticmethod
    def is_alpha_image(image):
        length = len(image.split())
        if length >= 5:
            raise Exception
        return length == 4

    @staticmethod
    def change_alpha_to_white(image):
        image.load()  # required for png.split()
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[3])  # 3 is alpha channel
        image.close()
        return background

    @staticmethod
    def calc_size(a, b, set_a):
        return set_a, int(b * set_a / a / 2) * 2

    @staticmethod
    def fix_too_long_width(w, h):
        return ImageProcessor.calc_size(w, h, MAX_WIDTH)

    @staticmethod
    def fix_too_long_height(w, h):
        h, w = ImageProcessor.calc_size(h, w, MAX_HEIGHT)
        return w, h

    @staticmethod
    def fix_too_long_size(w, h):
        if w > MAX_WIDTH:
            w, h = ImageProcessor.fix_too_long_width(w, h)
        if h > MAX_HEIGHT:
            w, h = ImageProcessor.fix_too_long_height(w, h)
        return w, h

    @staticmethod
    def resize_image(image):
        old_w, old_h = image.size
        new_w, new_h = ImageProcessor.fix_too_long_size(old_w, old_h)
        image = image.resize((new_w, new_h), Image.LANCZOS)
        return image

    @staticmethod
    def get_dstbytes(name, input_image_bytes):
        content_io = io.BytesIO(input_image_bytes)
        storage_io = io.BytesIO()
        image = Image.open(content_io)

        w, h = image.size
        if (w > MAX_WIDTH) or (h > MAX_HEIGHT):
            image = ImageProcessor.resize_image(image)

        if ImageProcessor.need_rotate(name):
            image = ImageProcessor.rotate_image(image)

        if ImageProcessor.is_alpha_image(image):
            image = ImageProcessor.change_alpha_to_white(image)

        image = image.convert("RGB")
        image.save(storage_io, "jpeg", quality=85, optimize=True)

        output_image_bin = storage_io.getvalue()

        image.close()
        content_io.close()
        storage_io.close()

        return output_image_bin


class ZipToPdfConverter:
    def __init__(self, zip_path: Union[str, bytes], pdf_path: Optional[str] = None, progress: bool = True):
        self.zip_path: Union[str, bytes] = zip_path
        self.pdf_path: Optional[str] = pdf_path
        self.progress: bool = progress

    def convert(self) -> bytes:
        zipbytes = self._read_zip()
        zip_io = io.BytesIO(zipbytes)
        dstbytes_list: List[bytes] = []

        with zipfile.ZipFile(zip_io) as z:
            namelist = list(natsorted(z.namelist()))

            if self.progress:
                namelist = tqdm.tqdm(namelist, desc="izip2pdf")

            for name in namelist:
                tqdm.tqdm.write(name)
                # Use ZipFile context for directory check
                if zipfile.Path(z, name).is_dir():
                    continue

                srcbytes = z.read(name)
                dstbytes = ImageProcessor.get_dstbytes(name, srcbytes)
                dstbytes_list.append(dstbytes)

        zip_io.close()
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


def convert(zip_input: Union[str, bytes], output_pdf_path: Optional[str] = None, progress: bool = False) -> bytes:
    """Convert a ZIP (file path or bytes) containing images into a PDF.

    When output_pdf_path is provided, the PDF is written to that path and
    the PDF bytes are also returned.
    """
    converter = ZipToPdfConverter(zip_input, output_pdf_path, progress=progress)
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
