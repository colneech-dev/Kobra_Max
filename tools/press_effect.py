"""
Which picture the display shows over a button while it is held (the touch record's "Pic_On" field,
DWIN T5L DGUS II guide 6.6: "Button press effect page. 0xFF** means no button press effect").

The display copies the pressed button's rectangle out of that other picture, so every page that has
buttons needs a "pressed" twin: the same art with the buttons drawn in a lit-up style
(generate_screens.py renders them). The stock Anycubic UI does the same, with pressed picture =
page + 34 (Move Axes 128 -> 162).

Pages with identical art share one pressed picture: an ENG page (+120) uses its CHS twin's, and the
few other duplicates are listed in TWIN. Pressed IDs live in 35-84, which no page uses (page 16's is 84: 50 is the boot page).
"""

# Pages whose art generate_screens.py also emits at +120 (the ENG mirror).
CORE = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 16, 17, 18, 19, 20, 21, 22, 23,
        25, 26, 27, 29, 30, 32, 33, 34)

# page -> page with identical art
TWIN = {p + 120: p for p in CORE}
TWIN.update({213: 93, 170: 117, 173: 171, 199: 187, 200: 188, 204: 201, 206: 203})

# Pressed-picture IDs for pages outside 1-34 (those use page + 34, as in the stock UI).
SPECIAL_ID = {93: 69, 117: 70, 171: 71, 187: 72, 188: 73, 201: 74, 203: 75, 207: 76, 209: 77,
              211: 78, 212: 79, 214: 80, 215: 81, 216: 82, 217: 83}

NO_EFFECT = 0xFF00     # "no press effect" marker used by the stock touch file


def base_page(page):
    """The page whose art (and pressed picture) this page shares."""
    return TWIN.get(page, page)


def pressed_id(page, key=None):
    """Pressed-picture ID for a touch zone on `page`, or None for no effect.

    File-list rows (page 2/122, keys 7-11) are tap targets, not buttons: the firmware marks the
    selected row with text instead."""
    if page in (2, 122) and key is not None and 7 <= key <= 11:
        return None
    b = base_page(page)
    if 1 <= b <= 34:
        return _pic(b + 34)
    return SPECIAL_ID.get(b)


# Picture 50 is the first picture the display shows at power-on (the page that carries the boot
# Image Animation record), so no pressed picture may live there: page 16's moves to a free ID.
BOOT_PAGE_PICTURE = 50
MOVED_PRESSED = {BOOT_PAGE_PICTURE: 84}


def _pic(pid):
    return MOVED_PRESSED.get(pid, pid)


def all_pressed_ids():
    return sorted(set(list(SPECIAL_ID.values()) + [_pic(b + 34) for b in range(1, 35)]))
