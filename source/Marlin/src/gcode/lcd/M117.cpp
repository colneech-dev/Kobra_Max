/**
 * Marlin 3D Printer Firmware
 * Copyright (c) 2020 MarlinFirmware [https://github.com/MarlinFirmware/Marlin]
 *
 * Based on Sprinter and grbl.
 * Copyright (c) 2011 Camiel Gubbels / Erik van der Zalm
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 *
 */


#include "../../inc/MarlinConfig.h"
#include "../../MarlinCore.h"
#include "../gcode.h"
#include "../../lcd/marlinui.h"

/**
 * M117: Set LCD Status Message
 */
void GcodeSuite::M117() {
  if (parser.string_arg && parser.string_arg[0]) {
    if (parser.command_letter == 'M' && parser.codenum == 117) {
      static char comment_buf[32];
      strncpy(comment_buf, parser.string_arg, 30);
      comment_buf[30] = '\0';
      gcodeComment = comment_buf;
    }
    ui.set_status(parser.string_arg);
  }
  else {
    gcodeComment = "G-Code Status Area";
    ui.reset_status();
  }
}
