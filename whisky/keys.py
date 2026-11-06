"""Virtual-key helpers: names, modifiers, config parsing."""
import ctypes

DEFAULT = [0xA3]  # Right Ctrl

MODIFIERS = {0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C}
WIN = {0x5B, 0x5C}
ESC = 0x1B

NAMES = {
    0xA2: "Left Ctrl", 0xA3: "Right Ctrl", 0x11: "Ctrl",
    0xA0: "Left Shift", 0xA1: "Right Shift", 0x10: "Shift",
    0xA4: "Left Alt", 0xA5: "Right Alt", 0x12: "Alt",
    0x5B: "Win", 0x5C: "Right Win", 0x5D: "Menu",
    0x14: "Caps Lock", 0x90: "Num Lock", 0x91: "Scroll Lock",
    0x20: "Space", 0x0D: "Enter", 0x09: "Tab", 0x08: "Backspace", 0x1B: "Esc",
    0x2D: "Insert", 0x2E: "Delete", 0x24: "Home", 0x23: "End", 0x21: "Page Up", 0x22: "Page Down",
    0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down", 0x13: "Pause", 0x2C: "Print Screen",
    0xC0: "`", 0xBD: "-", 0xBB: "=", 0xDB: "[", 0xDD: "]", 0xDC: "\\", 0xBA: ";", 0xDE: "'",
    0xBC: ",", 0xBE: ".", 0xBF: "/",
}
# Old string names (v1.0 config) -> vk
LEGACY = {"ctrl_r": 0xA3, "ctrl_l": 0xA2, "alt_r": 0xA5, "alt_l": 0xA4, "alt_gr": 0xA5,
          "shift_r": 0xA1, "shift": 0xA0, "cmd": 0x5B, "cmd_r": 0x5C, "caps_lock": 0x14,
          "space": 0x20, **{f"f{i}": 0x6F + i for i in range(1, 25)}}

# keep combo display order stable: modifiers first, Ctrl, Win, Alt, Shift
_ORDER = [0xA2, 0xA3, 0x11, 0x5B, 0x5C, 0xA4, 0xA5, 0x12, 0xA0, 0xA1, 0x10]


def name(vk):
    if vk in NAMES:
        return NAMES[vk]
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return f"Num {vk - 0x60}"
    try:
        sc = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
        buf = ctypes.create_unicode_buffer(32)
        if sc and ctypes.windll.user32.GetKeyNameTextW(sc << 16, buf, 32):
            return buf.value
    except Exception:
        pass
    return f"Key {vk:#04x}"


def ordered(vks):
    return sorted(set(vks), key=lambda v: (_ORDER.index(v) if v in _ORDER else 100, v))


def label(vks):
    return " + ".join(name(v) for v in ordered(vks)) if vks else "—"


def parse(value):
    """Config value -> list of vks. Accepts list of ints, legacy name string or 'a+b'."""
    if isinstance(value, list):
        vks = [int(v) for v in value if isinstance(v, int) and 0 < v < 256]
        return vks or list(DEFAULT)
    if isinstance(value, str):
        out = []
        for part in value.lower().split("+"):
            part = part.strip()
            if part in LEGACY:
                out.append(LEGACY[part])
            elif len(part) == 1 and part.isalnum():
                out.append(ord(part.upper()))
        return out or list(DEFAULT)
    return list(DEFAULT)


def validate(vks):
    """Error text or None."""
    if not vks:
        return "No key pressed"
    if set(vks) <= WIN:
        return "Win alone opens Start — add another key"
    if ESC in vks:
        return "Esc can't be used"
    if len(vks) > 4:
        return "Max 4 keys"
    return None
