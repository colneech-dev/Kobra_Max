#!/usr/bin/env python3
"""
Three targeted fixes for dgus_tft.cpp:

Fix 1 — ChangePageOfTFT ENG offset:
  Pages 214/215/216 are language-neutral shared pages. The generic ENG branch
  adds +120, sending the display to non-existent pages 334/335/336 and setting
  page_index_now to a value the IdleLoop dispatch never matches.
  Fix: add explicit pass-through for these pages before the final else.

Fix 2 — INPUT_SHAPING guard:
  #if ENABLED(INPUT_SHAPING_X) excludes the handler when only Y is enabled.
  Fix: #if ENABLED(INPUT_SHAPING_X) || ENABLED(INPUT_SHAPING_Y)

Fix 3 — term_push VP overflow:
  DGUS stores data + 0xFF 0xFF terminator in VP RAM. VP slot = 48 bytes.
  Max safe data = 48 - 2 = 46 chars. Current code allows 47 chars, overflowing
  one byte into the adjacent VP slot.
  Fix: limit strncpy to TERM_LINE_LEN-3 (45 chars). Also tighten j limit in
  ProcessPanelRequest so command echoes stay within bounds.
"""

path = r'C:\Users\Colin\Documents\GitHub\Kobra_Max\source\Marlin\src\lcd\extui\lib\anycubic_dgus\dgus_tft.cpp'

with open(path, 'rb') as f:
    raw = f.read()
content = raw.decode('utf-8', errors='replace').replace('\r\n', '\n')

changes = []

# ── Fix 1: ChangePageOfTFT language-neutral pages ────────────────────────────
OLD1 = (
    "    } else if (PAGE_CHS_PRINTING_SETTING == page_index) {\n"
    "      data_temp = page_index + 1;\n"
    "    } else {\n"
    "      data_temp = page_index + 120;\n"
    "    }"
)
NEW1 = (
    "    } else if (PAGE_CHS_PRINTING_SETTING == page_index) {\n"
    "      data_temp = page_index + 1;\n"
    "    } else if (page_index == PAGE_THUMBNAIL || page_index == PAGE_TERMINAL || page_index == PAGE_THERMAL_TUNE) {\n"
    "      data_temp = page_index;  // language-neutral shared pages — no ENG offset\n"
    "    } else {\n"
    "      data_temp = page_index + 120;\n"
    "    }"
)
changes.append(('ChangePageOfTFT ENG pass-through for 214/215/216', OLD1, NEW1))

# ── Fix 2: INPUT_SHAPING guard ────────────────────────────────────────────────
OLD2 = "void DgusTFT::page6_handle(void) {  // Input Shaping  M593\n#if ENABLED(INPUT_SHAPING_X)"
NEW2 = "void DgusTFT::page6_handle(void) {  // Input Shaping  M593\n#if ENABLED(INPUT_SHAPING_X) || ENABLED(INPUT_SHAPING_Y)"
changes.append(('INPUT_SHAPING guard includes Y', OLD2, NEW2))

# ── Fix 3a: term_push strncpy limit ──────────────────────────────────────────
OLD3 = (
    "  strncpy(term_log[term_head % TERM_LINES], s, TERM_LINE_LEN - 1);\n"
    "  term_log[term_head % TERM_LINES][TERM_LINE_LEN - 1] = '\\0';"
)
NEW3 = (
    "  // Max safe chars = VP slot (48) - 2 for 0xFF 0xFF terminator - 1 safety = 45\n"
    "  strncpy(term_log[term_head % TERM_LINES], s, TERM_LINE_LEN - 3);\n"
    "  term_log[term_head % TERM_LINES][TERM_LINE_LEN - 3] = '\\0';"
)
changes.append(('term_push VP overflow — limit to 45 chars', OLD3, NEW3))

# ── Fix 3b: ProcessPanelRequest cmd_buf j limit ───────────────────────────────
# cmd_buf j < 47 allows 47 chars; after snprintf "> %s" → 49 chars > VP safe limit.
# j < 43 gives 43 chars; "> " + 43 = 45 chars → 45 + 0xFF 0xFF = 47 bytes ≤ 48. Safe.
OLD4 = "        for (uint8_t i = 4; i < 63 && j < 47; i++) {"
NEW4 = "        for (uint8_t i = 4; i < 63 && j < 43; i++) {  // 43 + \"> \" = 45 chars, fits VP slot"
changes.append(('ProcessPanelRequest cmd_buf j limit 47 to 43', OLD4, NEW4))

ok = True
for name, old, new in changes:
    if old in content:
        content = content.replace(old, new, 1)
        print(f'OK  : {name}')
    else:
        print(f'MISS: {name}')
        ok = False

if ok:
    with open(path, 'wb') as f:
        f.write(content.replace('\n', '\r\n').encode('utf-8'))
    print('Written.')
else:
    print('Aborted — one or more patterns not found.')
