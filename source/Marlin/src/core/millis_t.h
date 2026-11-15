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
#pragma once

#include <stdint.h>

typedef uint32_t millis_t;

#define SEC_TO_MS(N) millis_t((N)*1000UL)
#define MIN_TO_MS(N) SEC_TO_MS((N)*60UL)
#define MS_TO_SEC(N) millis_t((N)/1000UL)

#define PENDING(NOW,SOON) ((int32_t)(NOW-(SOON))<0)
#define ELAPSED(NOW,SOON) (!PENDING(NOW,SOON))

// A deadline of 0 means "no timeout" in several places. millis() + delay can wrap to exactly 0 (once in 49.7 days), which would silently
// disable a heater watch or idle timeout; use 1 instead (upstream 45c56c38, #28753; only the heater watch and the idle timeout are changed here).
static inline millis_t next_millis(const millis_t t) { return t ? t : 1; }
