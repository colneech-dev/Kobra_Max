#!/usr/bin/env python3
"""Replace M306 T single-command enqueue with injectCommands_P sequence so M500
runs automatically after MPC autotune completes. Also update the terminal echo."""

path = r'C:\Users\Colin\Documents\GitHub\Kobra_Max\source\Marlin\src\lcd\extui\lib\anycubic_dgus\dgus_tft.cpp'

with open(path, 'rb') as f:
    raw = f.read()
content = raw.decode('utf-8', errors='replace').replace('\r\n', '\n')

OLD = (
    "    case KEY_TUNE_HOTEND:\n"
    "      #if ENABLED(MPCTEMP)\n"
    "        term_push(\"> M306 T\");\n"
    "        queue.enqueue_one_now(\"M306 T\");\n"
    "        ChangePageOfTFT(PAGE_TERMINAL);\n"
    "      #endif\n"
    "      break;"
)
NEW = (
    "    case KEY_TUNE_HOTEND:\n"
    "      #if ENABLED(MPCTEMP)\n"
    "        term_push(\"> M306 T  (M500 auto-queued)\");\n"
    "        // M500 is injected after M306 T — Marlin processes sequentially\n"
    "        injectCommands_P(PSTR(\"M306 T\\nM500\"));\n"
    "        ChangePageOfTFT(PAGE_TERMINAL);\n"
    "      #endif\n"
    "      break;"
)

if OLD in content:
    content = content.replace(OLD, NEW, 1)
    print("OK: MPC save fix applied")
    with open(path, 'wb') as f:
        f.write(content.replace('\n', '\r\n').encode('utf-8'))
    print("Written.")
else:
    print("MISS: pattern not found — file not modified")
