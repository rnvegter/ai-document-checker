"""Find and remove hidden traces: invisible Unicode, look-alike letters and image metadata.

Everything here works on characters and bytes only. Images are never re-encoded,
so they keep their exact pixels and quality.
"""
import re
import struct
import unicodedata
from collections import Counter

# Characters that render as nothing and can carry hidden marks.
_DELETE = [
    ("Invisible characters", "[​-‍⁠-⁤﻿­͏ᅟᅠ឴឵᠎ㅤﾠ]"),
    ("Text-direction controls", "[؜‎‏‪-‮⁦-⁩]"),
    ("Hidden tag characters", "[\U000e0000-\U000e007f]"),
    # U+FE0F is kept: it selects the colour form of emoji.
    ("Variation selectors", "[︀-︎\U000e0100-\U000e01ef]"),
]
_DELETE = [(label, re.compile(pattern)) for label, pattern in _DELETE]

# Unusual spaces become a normal space; a narrow no-break space becomes a normal no-break space.
_SPACES = re.compile("[  -  　]")
_NARROW_NBSP = " "

# Fullwidth Latin (ＡＢＣ) and "styled" mathematical letters (𝐀𝐁𝐂) normalise to plain letters.
_STYLED = re.compile("[！-～\U0001d400-\U0001d7ff]")

# Cyrillic and Greek letters that look identical to Latin ones. They are only
# replaced inside words that also contain Latin letters, so real Greek or
# Cyrillic text is left alone.
_LOOKALIKES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j",
    "ѕ": "s", "ԁ": "d", "ԛ": "q", "ԝ": "w", "һ": "h", "ӏ": "l",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C",
    "Т": "T", "Х": "X", "І": "I", "Ј": "J", "Ѕ": "S", "Ү": "Y",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N",
    "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X", "ο": "o",
})
_LOOKALIKE_CHARS = set(chr(c) for c in _LOOKALIKES)
_WORD = re.compile(r"[^\W\d_]+")
_LATIN = re.compile(r"[A-Za-zÀ-ɏ]")


def _fix_word(match, counts):
    word = match.group(0)
    if not _LATIN.search(word) or not _LOOKALIKE_CHARS.intersection(word):
        return word
    fixed = word.translate(_LOOKALIKES)
    counts["Look-alike letters"] += sum(a != b for a, b in zip(word, fixed))
    return fixed


def scrub_text(text):
    """Return (clean text, Counter of what was removed or replaced)."""
    counts = Counter()
    for label, pattern in _DELETE:
        text, n = pattern.subn("", text)
        counts[label] += n
    text, n = _SPACES.subn(" ", text)
    counts["Unusual spaces"] += n + text.count(_NARROW_NBSP)
    text = text.replace(_NARROW_NBSP, " ")

    def styled(match):
        counts["Fullwidth or styled letters"] += 1
        return unicodedata.normalize("NFKC", match.group(0))

    text = _STYLED.sub(styled, text)
    text = _WORD.sub(lambda m: _fix_word(m, counts), text)
    return text, +counts


# ---------- Images ----------

def _exif_orientation(payload):
    """Orientation tag from an EXIF APP1 payload, 1 if absent, None if unreadable."""
    try:
        tiff = payload[6:]
        endian = "<" if tiff[:2] == b"II" else ">"
        ifd = struct.unpack(endian + "I", tiff[4:8])[0]
        (count,) = struct.unpack(endian + "H", tiff[ifd:ifd + 2])
        for k in range(count):
            entry = tiff[ifd + 2 + 12 * k: ifd + 14 + 12 * k]
            if struct.unpack(endian + "H", entry[:2])[0] == 0x0112:
                return struct.unpack(endian + "H", entry[8:10])[0]
        return 1
    except (struct.error, IndexError):
        return None


def _strip_jpeg(data):
    out, removed, i = [data[:2]], [], 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            return data, []  # not a layout we understand: leave the image untouched
        marker = data[i + 1]
        if marker == 0xFF:
            i += 1
            continue
        if marker in (0xDA, 0xD9):  # start of scan / end: the rest is image data
            out.append(data[i:])
            return b"".join(out), removed
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            out.append(data[i:i + 2])
            i += 2
            continue
        (length,) = struct.unpack(">H", data[i + 2:i + 4])
        segment, payload = data[i:i + 2 + length], data[i + 4:i + 2 + length]
        label = None
        if marker == 0xE1 and payload.startswith(b"Exif\0\0"):
            # Keep EXIF when it rotates the photo, or the image would display sideways.
            label = "EXIF" if _exif_orientation(payload) == 1 else None
        elif marker == 0xE1:
            label = "XMP"
        elif marker == 0xED:
            label = "IPTC"
        elif marker == 0xEB:
            label = "C2PA"
        elif marker == 0xFE:
            label = "comment"
        if label:
            removed.append(label)
        else:
            out.append(segment)
        i += 2 + length
    return data, []


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_DROP = {b"tEXt": "text", b"zTXt": "text", b"iTXt": "text", b"eXIf": "EXIF", b"caBX": "C2PA"}


def _strip_png(data):
    out, removed, i = [_PNG_SIGNATURE], [], 8
    while i + 12 <= len(data):
        (length,) = struct.unpack(">I", data[i:i + 4])
        kind, end = data[i + 4:i + 8], i + 12 + length
        if end > len(data):
            return data, []
        if kind in _PNG_DROP:
            is_xmp = kind == b"iTXt" and data[i + 8:end].startswith(b"XML:com.adobe.xmp")
            removed.append("XMP" if is_xmp else _PNG_DROP[kind])
        else:
            out.append(data[i:end])
        i = end
        if kind == b"IEND":
            return b"".join(out), removed
    return data, []


def _strip_webp(data):
    chunks, removed, i = [], [], 12
    while i + 8 <= len(data):
        kind = data[i:i + 4]
        (size,) = struct.unpack("<I", data[i + 4:i + 8])
        end = i + 8 + size + (size & 1)
        if end > len(data):
            return data, []
        if kind in (b"EXIF", b"XMP ", b"C2PA"):
            removed.append(kind.decode().strip())
        else:
            chunks.append(bytearray(data[i:end]))
        i = end
    if not removed:
        return data, []
    for chunk in chunks:
        if chunk[:4] == b"VP8X":
            chunk[8] &= ~0x0C & 0xFF  # clear the EXIF and XMP flags
    body = b"WEBP" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body, removed


def strip_image_metadata(data):
    """Return (image bytes without metadata, list of removed metadata kinds)."""
    if data[:2] == b"\xff\xd8":
        result, removed = _strip_jpeg(data)
    elif data.startswith(_PNG_SIGNATURE):
        result, removed = _strip_png(data)
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        result, removed = _strip_webp(data)
    else:
        return data, []
    return result, list(dict.fromkeys(removed))
