import zip2pdf


def test_zip2pdf():
    with open("input/input.zip", "rb") as f:
        zip_bin = f.read()

    zip2pdf.convert("input/input.zip", "output/output1.pdf")
    zip2pdf.convert(zip_bin, "output/output2.pdf")

    with open("output/output3.pdf", "wb") as f:
        f.write(zip2pdf.convert("input.zip"))

    with open("output/output4.pdf", "wb") as f:
        f.write(zip2pdf.convert(zip_bin))

    # testcase
    zip2pdf.convert("input/input2.zip", "output/output5.pdf")
    zip2pdf.convert("input/input3.zip", "output/output6.pdf")
    zip2pdf.convert("input/input4.zip", "output/output7.pdf")
    zip2pdf.convert("input/input5.zip", "output/output8.pdf")  # 16s
    zip2pdf.convert("input/input6.zip", "output/utput9.pdf")
    zip2pdf.convert("input/input7.zip", "output/output10.pdf")
