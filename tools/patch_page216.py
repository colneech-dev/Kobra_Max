#!/usr/bin/env python3
"""Patch dgus_tft.cpp to add thermal tuning page 216 support."""

path = r'C:\Users\Colin\Documents\GitHub\Kobra_Max\source\Marlin\src\lcd\extui\lib\anycubic_dgus\dgus_tft.cpp'

with open(path, 'rb') as f:
    raw = f.read()
# Normalise to LF for matching, restore CRLF on write
content = raw.decode('utf-8', errors='replace').replace('\r\n', '\n')

changes = []

# 1 — IdleLoop: add page 216 dispatch before the closing 'else {'
OLD1 = (
    "  } else if (page_index_now == 215) {\n"
    "\n"
    "    page215_handle();\n"
    "\n"
    "  } else {"
)
NEW1 = (
    "  } else if (page_index_now == 215) {\n"
    "\n"
    "    page215_handle();\n"
    "\n"
    "  } else if (page_index_now == 216) {\n"
    "\n"
    "    page216_handle();\n"
    "\n"
    "  } else {"
)
changes.append(('IdleLoop dispatch', OLD1, NEW1))

# 2 — page15_handle: add case 6 for Thermal Tuning after case 5
OLD2 = (
    "    case 5:   // Input Shaping\n"
    "      ChangePageOfTFT(PAGE_KEYBPARD);\n"
    "      break;\n"
    "  }\n"
    "}\n"
    "\n"
    "void DgusTFT::page16_handle"
)
NEW2 = (
    "    case 5:   // Input Shaping\n"
    "      ChangePageOfTFT(PAGE_KEYBPARD);\n"
    "      break;\n"
    "\n"
    "    case 6:   // Thermal Tuning\n"
    "      ChangePageOfTFT(PAGE_THERMAL_TUNE);\n"
    "      break;\n"
    "  }\n"
    "}\n"
    "\n"
    "void DgusTFT::page16_handle"
)
changes.append(('page15_handle case 6', OLD2, NEW2))

# 3 — Insert page216_handle before closing namespace brace
OLD3 = (
    "} // namespace\n"
    "\n"
    "#endif // ANYCUBIC_LCD_DGUS"
)
NEW3 = (
    "void DgusTFT::page216_handle(void) {  // Thermal Tuning\n"
    "  switch (key_value) {\n"
    "    case 0: break;\n"
    "\n"
    "    case KEY_TUNE_BACK:\n"
    "      ChangePageOfTFT(PAGE_PREPARE);\n"
    "      break;\n"
    "\n"
    "    case KEY_TUNE_HOTEND:\n"
    "      #if ENABLED(MPCTEMP)\n"
    "        term_push(\"> M306 T\");\n"
    "        queue.enqueue_one_now(\"M306 T\");\n"
    "        ChangePageOfTFT(PAGE_TERMINAL);\n"
    "      #endif\n"
    "      break;\n"
    "\n"
    "    case KEY_TUNE_BED:\n"
    "      #if ENABLED(PIDTEMPBED)\n"
    "        term_push(\"> M303 E-1 S60 C8 U1\");\n"
    "        queue.enqueue_one_now(\"M303 E-1 S60 C8 U1\");\n"
    "        ChangePageOfTFT(PAGE_TERMINAL);\n"
    "      #endif\n"
    "      break;\n"
    "  }\n"
    "}\n"
    "\n"
    "} // namespace\n"
    "\n"
    "#endif // ANYCUBIC_LCD_DGUS"
)
changes.append(('page216_handle body', OLD3, NEW3))

ok = True
for name, old, new in changes:
    if old in content:
        content = content.replace(old, new, 1)
        print(f"OK  : {name}")
    else:
        print(f"MISS: {name}")
        ok = False

if ok:
    with open(path, 'wb') as f:
        f.write(content.replace('\n', '\r\n').encode('utf-8'))
    print("Written.")
else:
    print("Aborted — not all patterns found, file not modified.")
