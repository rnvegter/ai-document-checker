import io
import struct
import sys
import unittest
import zlib
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from traces import scrub_text, strip_image_metadata  # noqa: E402

XMP = b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><Iptc4xmpExt:DigitalSourceType>trainedAlgorithmicMedia</Iptc4xmpExt:DigitalSourceType></x:xmpmeta>'


def tag_encode(text):
    """Hide ASCII text as invisible Unicode tag characters."""
    return "".join(chr(0xE0000 + ord(c)) for c in text)


class TextTests(unittest.TestCase):
    def test_removes_hidden_characters(self):
        text = "Hello​ wor‍ld⁦!" + tag_encode("made by AI") + "﻿"
        clean, counts = scrub_text(text)
        self.assertEqual(clean, "Hello world!")
        self.assertEqual(counts["Invisible characters"], 3)
        self.assertEqual(counts["Text-direction controls"], 1)
        self.assertEqual(counts["Hidden tag characters"], 10)

    def test_spaces(self):
        clean, counts = scrub_text("10 000 euro per　jaar")
        self.assertEqual(clean, "10 000 euro per jaar")
        self.assertEqual(counts["Unusual spaces"], 3)

    def test_lookalikes_only_inside_latin_words(self):
        clean, counts = scrub_text("Thе rеport (Cyrillic е) and Москва and α-test")
        self.assertEqual(clean, "The report (Cyrillic е) and Москва and α-test")
        self.assertEqual(counts["Look-alike letters"], 2)

    def test_styled_letters(self):
        clean, counts = scrub_text("𝐁𝐨𝐥𝐝 and ＦＵＬＬ")
        self.assertEqual(clean, "Bold and FULL")
        self.assertEqual(counts["Fullwidth or styled letters"], 8)

    def test_normal_dutch_and_emoji_untouched(self):
        text = "Ĳsselmeer, één café, € 40.000 en ❤️ — “quotes”"
        self.assertEqual(scrub_text(text), (text, {}))


def jpeg_with_metadata(orientation=1):
    img = Image.new("RGB", (16, 8), (200, 30, 30))
    exif = Image.Exif()
    exif[0x0112] = orientation
    exif[0x0131] = "DALL-E"
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif.tobytes(), quality=95)
    data = buf.getvalue()
    extra = b""
    for marker, payload in [
        (0xE1, b"http://ns.adobe.com/xap/1.0/\0" + XMP),
        (0xEB, b"JP\0\x01c2pa manifest"),
        (0xFE, b"Generated with AI"),
    ]:
        extra += bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload
    # Insert after the first segment (JFIF/EXIF header), where real tools put metadata.
    (first_len,) = struct.unpack(">H", data[4:6])
    at = 4 + first_len
    return data[:at] + extra + data[at:]


def png_chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))


class ImageTests(unittest.TestCase):
    def pixels(self, data):
        with Image.open(io.BytesIO(data)) as img:
            return img.convert("RGB").tobytes()

    def test_jpeg(self):
        data = jpeg_with_metadata()
        clean, removed = strip_image_metadata(data)
        self.assertEqual(set(removed), {"EXIF", "XMP", "C2PA", "comment"})
        for needle in (b"Exif", b"trainedAlgorithmicMedia", b"c2pa", b"Generated", b"DALL-E"):
            self.assertNotIn(needle, clean)
        self.assertEqual(self.pixels(clean), self.pixels(data))

    def test_jpeg_keeps_exif_needed_for_rotation(self):
        clean, removed = strip_image_metadata(jpeg_with_metadata(orientation=6))
        self.assertNotIn("EXIF", removed)
        self.assertIn(b"Exif", clean)
        self.assertNotIn(b"trainedAlgorithmicMedia", clean)

    def test_png(self):
        info = PngInfo()
        info.add_text("Software", "Midjourney")
        info.add_itxt("XML:com.adobe.xmp", XMP.decode())
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), (0, 90, 200)).save(buf, "PNG", pnginfo=info)
        data = buf.getvalue()
        data = data[:-12] + png_chunk(b"caBX", b"c2pa manifest") + data[-12:]
        clean, removed = strip_image_metadata(data)
        self.assertEqual(set(removed), {"text", "XMP", "C2PA"})
        for needle in (b"Midjourney", b"xmpmeta", b"caBX"):
            self.assertNotIn(needle, clean)
        self.assertEqual(self.pixels(clean), self.pixels(data))

    def test_webp(self):
        exif = Image.Exif()
        exif[0x0131] = "Stable Diffusion"
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), (10, 120, 10)).save(buf, "WEBP", exif=exif.tobytes(), xmp=XMP, lossless=True)
        data = buf.getvalue()
        clean, removed = strip_image_metadata(data)
        self.assertEqual(set(removed), {"EXIF", "XMP"})
        self.assertNotIn(b"Stable Diffusion", clean)
        self.assertEqual(struct.unpack("<I", clean[4:8])[0], len(clean) - 8)
        self.assertEqual(self.pixels(clean), self.pixels(data))

    def test_clean_and_unknown_images_are_unchanged(self):
        buf = io.BytesIO()
        Image.new("RGB", (4, 4)).save(buf, "PNG")
        self.assertEqual(strip_image_metadata(buf.getvalue()), (buf.getvalue(), []))
        for data in (b"GIF89a....", b"\xff\xd8garbage", b""):
            self.assertEqual(strip_image_metadata(data), (data, []))


if __name__ == "__main__":
    unittest.main()
