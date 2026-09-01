import hashlib
import os
import struct

from PIL import Image
from pypdf import PdfReader, PdfWriter

SUPPORTED_IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.bmp'}
SUPPORTED_TEXT_EXT = {'.txt'}
SUPPORTED_PDF_EXT = {'.pdf'}

ZW0 = '\u200b'          # zero width space  -> bit 0
ZW1 = '\u200c'          # zero width non-joiner -> bit 1
MARK_START = '\u2060'   # word joiner (invisible) -> delimiter start
MARK_END = '\u2061'     # function application (invisible) -> delimiter end


def sha256_of_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def _to_bits(data_bytes):
    bits = []
    for b in data_bytes:
        for i in range(7, -1, -1):
            bits.append((b >> i) & 1)
    return bits


def _bits_to_bytes(bits):
    out = bytearray()
    for i in range(0, len(bits) - len(bits) % 8, 8):
        byte = 0
        for bit in bits[i:i + 8]:
            byte = (byte << 1) | bit
        out.append(byte)
    return bytes(out)


# ---------------------------------------------------------------- images (LSB)

def embed_image(in_path, payload: str, out_path: str):
    img = Image.open(in_path).convert('RGB')
    payload_bytes = payload.encode('utf-8')
    header = struct.pack('>I', len(payload_bytes))
    bits = _to_bits(header + payload_bytes)

    pixels = list(img.getdata())
    capacity = len(pixels) * 3
    if len(bits) > capacity:
        raise ValueError('Image is too small to hold the watermark payload')

    new_pixels = []
    idx = 0
    for (r, g, b) in pixels:
        ch = [r, g, b]
        for c in range(3):
            if idx < len(bits):
                ch[c] = (ch[c] & ~1) | bits[idx]
                idx += 1
        new_pixels.append(tuple(ch))

    img.putdata(new_pixels)
    # Always save as PNG: JPEG re-compression would destroy the LSB payload.
    img.save(out_path, format='PNG')
    return out_path


def extract_image(in_path):
    try:
        img = Image.open(in_path).convert('RGB')
    except Exception:
        return None
    pixels = img.getdata()
    bits = []
    for (r, g, b) in pixels:
        bits.append(r & 1)
        bits.append(g & 1)
        bits.append(b & 1)

    if len(bits) < 32:
        return None
    length = struct.unpack('>I', _bits_to_bytes(bits[:32]))[0]
    total_needed = 32 + length * 8
    if length <= 0 or length > 4096 or total_needed > len(bits):
        return None
    payload_bytes = _bits_to_bytes(bits[32:32 + length * 8])
    try:
        return payload_bytes.decode('utf-8')
    except UnicodeDecodeError:
        return None


# ---------------------------------------------------------------- text (zero-width)

def embed_text(in_path, payload: str, out_path: str):
    with open(in_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    bits = _to_bits(payload.encode('utf-8'))
    zw = ''.join(ZW1 if b else ZW0 for b in bits)
    new_content = content + MARK_START + zw + MARK_END
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    return out_path


def extract_text(in_path):
    try:
        with open(in_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return None
    start = content.find(MARK_START)
    end = content.find(MARK_END)
    if start == -1 or end == -1 or end <= start:
        return None
    seq = content[start + 1:end]
    bits = [1 if ch == ZW1 else 0 for ch in seq if ch in (ZW0, ZW1)]
    if not bits:
        return None
    try:
        return _bits_to_bytes(bits).decode('utf-8')
    except UnicodeDecodeError:
        return None


# ---------------------------------------------------------------- pdf (hidden metadata)

def embed_pdf(in_path, payload: str, out_path: str):
    reader = PdfReader(in_path)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    try:
        existing = dict(reader.metadata) if reader.metadata else {}
    except Exception:
        existing = {}
    existing['/CustodyWatermark'] = payload
    writer.add_metadata(existing)
    with open(out_path, 'wb') as f:
        writer.write(f)
    return out_path


def extract_pdf(in_path):
    try:
        reader = PdfReader(in_path)
    except Exception:
        return None
    meta = reader.metadata
    if not meta:
        return None
    val = meta.get('/CustodyWatermark')
    return str(val) if val else None


# ---------------------------------------------------------------- dispatcher

def embed_watermark(ext, in_path, payload, out_path):
    ext = ext.lower()
    if ext in SUPPORTED_IMAGE_EXT:
        return embed_image(in_path, payload, out_path)
    if ext in SUPPORTED_TEXT_EXT:
        return embed_text(in_path, payload, out_path)
    if ext in SUPPORTED_PDF_EXT:
        return embed_pdf(in_path, payload, out_path)
    raise ValueError(f'Unsupported file type for watermarking: {ext}')


def extract_watermark(ext, in_path):
    ext = ext.lower()
    if ext in SUPPORTED_IMAGE_EXT:
        return extract_image(in_path)
    if ext in SUPPORTED_TEXT_EXT:
        return extract_text(in_path)
    if ext in SUPPORTED_PDF_EXT:
        return extract_pdf(in_path)
    raise ValueError(f'Unsupported file type for scanning: {ext}')
