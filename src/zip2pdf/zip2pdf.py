#!/usr/bin/python3
# -*- coding: utf-8 -*-
import io
import os
import sys
import zipfile

import img2pdf  # type: ignore[import-untyped]

# pillow plugin
import pillow_avif  # type: ignore[import-untyped]
import tqdm  # type: ignore[import-untyped]
from natsort import natsorted
from PIL import Image, ImageFile, ImageOps
from pillow_heif import register_heif_opener  # type: ignore[import-untyped]

register_heif_opener()
ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = 10**1000
MAX_WIDTH = 8192  # limit of jpg format
MAX_HEIGHT = 8192  # limit of jpg format
layout_fun = img2pdf.get_layout_fun((img2pdf.mm_to_pt(210), None))  # A4


def need_rotate(filename):
    if os.path.splitext(filename)[1].lower() in [".psd", ".webp"]:
        return False
    return True


def rotate_image(image):
    return ImageOps.exif_transpose(image)


def is_alpha_image(image):
    length = len(image.split())
    if length >= 5:
        raise Exception
    if length == 4:
        return True
    return False


def change_alpha_to_white(image):
    image.load()  # required for png.split()
    background = Image.new("RGB", image.size, (255, 255, 255))
    background.paste(image, mask=image.split()[3])  # 3 is alpha channel
    image.close()
    return background


def calc_size(a, b, set_a):
    return set_a, int(b * set_a / a / 2) * 2


def fix_too_long_width(w, h):
    return calc_size(w, h, MAX_WIDTH)


def fix_too_long_height(w, h):
    h, w = calc_size(h, w, MAX_HEIGHT)
    return w, h


def fix_too_long_size(w, h):
    if w > MAX_WIDTH:
        w, h = fix_too_long_width(w, h)

    if h > MAX_HEIGHT:
        w, h = fix_too_long_height(w, h)

    return w, h


def resize_image(image):
    old_w, old_h = image.size
    new_w, new_h = fix_too_long_size(old_w, old_h)
    # tqdm.tqdm.write(f'resize: {(old_w, old_h)} -> {(new_w, new_h)}')
    # image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
    image = image.resize((new_w, new_h), Image.LANCZOS)
    return image


def check_zip(zip_io):
    new_io = io.BytesIO()
    with zipfile.ZipFile(zip_io) as z, zipfile.ZipFile(
        new_io, "w", compression=zipfile.ZIP_DEFLATED
    ) as new_z:
        namelist = list(natsorted(z.namelist()))
        for name in tqdm.tqdm(namelist, desc="_check_"):
            if zipfile.Path(zip_io, name).is_dir():
                continue
            try:
                binary = z.read(name)
                stream = io.BytesIO(binary)
                image = Image.open(stream)
                image.close()
                stream.close()
            except KeyboardInterrupt:
                exit()

            new_z.writestr(name, binary)
    return new_io


def get_dstbytes(name, input_image_bytes):
    content_io = io.BytesIO(input_image_bytes)
    storage_io = io.BytesIO()
    image = Image.open(content_io)

    w, h = image.size
    if (w > MAX_WIDTH) or (h > MAX_HEIGHT):
        image = resize_image(image)

    if need_rotate(name):
        image = rotate_image(image)

    if is_alpha_image(image):
        image = change_alpha_to_white(image)

    image = image.convert("RGB")
    image.save(storage_io, "jpeg", quality=85, optimize=True)

    output_image_bin = storage_io.getvalue()

    image.close()
    content_io.close()
    storage_io.close()

    return output_image_bin


def is_jpg(filepath):
    root, ext = os.path.splitext(filepath)
    if ext.lower() in [".jpg", ".jpeg"]:
        return True
    return False


def convert(zip_any, pdfpath=None, progress=True):
    if isinstance(zip_any, bytes):
        zipbytes = zip_any
    else:
        with open(zip_any, "rb") as f:
            zipbytes = f.read()

    zip_io = io.BytesIO(zipbytes)
    # new_io = check_zip(zip_io)
    # zip_io.close()
    # zip_io = new_io

    dstbytes_list = []

    with zipfile.ZipFile(zip_io) as z:
        namelist = list(natsorted(z.namelist()))

        if progress:
            namelist = tqdm.tqdm(namelist, desc="zip2pdf")

        for name in namelist:
            tqdm.tqdm.write(name)
            if zipfile.Path(zip_io, name).is_dir():
                continue

            srcbytes = z.read(name)

            # if is_jpg(name):
            #    dstbytes = srcbytes
            # else:
            dstbytes = get_dstbytes(name, srcbytes)

            dstbytes_list.append(dstbytes)

    zip_io.close()

    pdfbytes = img2pdf.convert(dstbytes_list, layout_fun=layout_fun)

    if pdfpath is not None:
        with open(pdfpath, "wb") as f:
            f.write(pdfbytes)

    return pdfbytes


def test():
    with open("input.zip", "rb") as f:
        zip_bin = f.read()

    convert("input.zip", "output1.pdf")
    convert(zip_bin, "output2.pdf")

    with open("output3.pdf", "wb") as f:
        f.write(convert("input.zip"))

    with open("output4.pdf", "wb") as f:
        f.write(convert(zip_bin))

    # testcase
    convert("input2.zip", "output5.pdf")
    convert("input3.zip", "output6.pdf")
    convert("input4.zip", "output7.pdf")
    convert("input5.zip", "output8.pdf")  # 16s
    convert("input6.zip", "output9.pdf")
    convert("input7.zip", "output10.pdf")


def main():
    for zippath in tqdm.tqdm(sys.argv[1:], desc="process"):
        tqdm.tqdm.write(zippath)
        pdfpath = os.path.splitext(zippath)[0] + ".pdf"
        if os.path.isfile(pdfpath):
            continue
        try:
            convert(zippath, pdfpath, progress=True)
        except KeyboardInterrupt:
            exit()


if __name__ == "__main__":
    main()
