/**
 * Marlin 3D Printer Firmware
 * Copyright (c) 2023 MarlinFirmware [https://github.com/MarlinFirmware/Marlin]
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
#pragma once

// Map 2.0.8 USE_xMIN/MAX_PLUG defines to the 2.1.x USE_X_MIN/MAX form
// expected by the HC32 endstop_interrupts driver.
#if ENABLED(USE_XMIN_PLUG) && PIN_EXISTS(X_MIN)
  #define USE_X_MIN 1
#endif
#if ENABLED(USE_XMAX_PLUG) && PIN_EXISTS(X_MAX)
  #define USE_X_MAX 1
#endif
#if ENABLED(USE_YMIN_PLUG) && PIN_EXISTS(Y_MIN)
  #define USE_Y_MIN 1
#endif
#if ENABLED(USE_YMAX_PLUG) && PIN_EXISTS(Y_MAX)
  #define USE_Y_MAX 1
#endif
#if ENABLED(USE_ZMIN_PLUG) && PIN_EXISTS(Z_MIN)
  #define USE_Z_MIN 1
#endif
#if ENABLED(USE_ZMAX_PLUG) && PIN_EXISTS(Z_MAX)
  #define USE_Z_MAX 1
#endif
#if PIN_EXISTS(Z_MIN_PROBE)
  #define USE_Z_MIN_PROBE 1
#endif

// 2.0.8 uses SDSUPPORT; 2.1.x uses HAS_MEDIA. Bridge so HC32 SanityCheck.h doesn't
// undef SDCARD_EEPROM_EMULATION when the SD card is present.
#if ENABLED(SDSUPPORT) && !defined(HAS_MEDIA)
  #define HAS_MEDIA 1
#endif

#if ANY(I2C_EEPROM, SPI_EEPROM)
  #define USE_SHARED_EEPROM 1
#endif

// Allow SD support to be disabled
#if !HAS_MEDIA
  #undef ONBOARD_SDIO
#endif
