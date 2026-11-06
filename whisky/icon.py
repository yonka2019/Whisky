from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap


def draw(size=256, recording=False):
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 256
    bg = QPainterPath()
    bg.addRoundedRect(QRectF(8 * s, 8 * s, 240 * s, 240 * s), 56 * s, 56 * s)
    p.fillPath(bg, QColor(255, 69, 58) if recording else QColor(22, 22, 28))
    # five wave bars
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255))
    heights = [70, 130, 170, 130, 70]
    bw, gap = 24 * s, 18 * s
    x = (256 * s - (5 * bw + 4 * gap)) / 2
    for h in heights:
        h *= s
        p.drawRoundedRect(QRectF(x, 128 * s - h / 2, bw, h), bw / 2, bw / 2)
        x += bw + gap
    p.end()
    return img


def icon(recording=False):
    ic = QIcon()
    for sz in (16, 20, 24, 32, 48, 64, 256):
        ic.addPixmap(QPixmap.fromImage(draw(sz, recording)))
    return ic


def write_ico(path, sizes=(16, 20, 24, 32, 40, 48, 64, 128, 256)):
    """Multi-size .ico with PNG-encoded entries."""
    import struct
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    blobs = []
    for sz in sizes:
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        draw(sz).save(buf, "PNG")
        blobs.append((sz, bytes(ba)))
    head = struct.pack("<HHH", 0, 1, len(blobs))
    off = 6 + 16 * len(blobs)
    dirs, data = b"", b""
    for sz, png in blobs:
        dirs += struct.pack("<BBBBHHII", sz % 256, sz % 256, 0, 0, 1, 32, len(png), off + len(data))
        data += png
    with open(path, "wb") as f:
        f.write(head + dirs + data)
