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

/**
 * HAL for HC32F460 based boards
 *
 * Note: MarlinHAL class is in MarlinHAL.h/cpp
 */
#pragma once

#define CPU_32_BIT

#include "../../inc/MarlinConfigPre.h"

#include "../shared/Marduino.h"
#include "../shared/math_32bit.h"
#include "../shared/HAL_SPI.h"

#include "fastio.h"
#include "timers.h"

//
// Serial Ports
//

#include "MarlinSerial.h"

//
// Emergency Parser
//
//
// Misc. Defines
//
#define square(x) ((x) * (x))

#ifndef strncpy_P
  #define strncpy_P(dest, src, num) strncpy((dest), (src), (num))
#endif

//
// Misc. Functions
//
#ifndef analogInputToDigitalPin
  #define analogInputToDigitalPin(p) pin_t(p)
#endif

#define CRITICAL_SECTION_START()        \
  const bool irqon = !__get_PRIMASK();  \
  __disable_irq();                      \
  __DSB();
#define CRITICAL_SECTION_END()          \
  __DSB();                              \
  if (irqon) __enable_irq();

#define cli() __disable_irq()
#define sei() __enable_irq()

#define DISABLE_ISRS() cli()
#define ENABLE_ISRS()  sei()

// HC32 framework defines F_CPU as SYSTEM_CLOCK_FREQUENCIES.hclk (a runtime struct member),
// which cannot be used in preprocessor #if expressions. Marlin uses F_CPU in
// CYCLES_PER_MICROSECOND which appears in #if guards in stepper.cpp / trinamic.cpp.
// sysclock.h targets F_SYSTEM_CLOCK = F_HCLK = 200 MHz; use that value here so stepper
// cycle-budget and pulse-width calculations are accurate.
#undef F_CPU
#define F_CPU 200000000UL

// bss_end alias
#define __bss_end __bss_end__

// Fix bug in pgm_read_ptr
#undef pgm_read_ptr
#define pgm_read_ptr(addr) (*(addr))

//
// ADC
//
#define HAL_ADC_VREF_MV 3300
#define HAL_ADC_RESOLUTION 12

#define GET_PIN_MAP_PIN(index) index
#define GET_PIN_MAP_INDEX(pin) pin
#define PARSED_PIN_INDEX(code, dval) parser.intval(code, dval)

//
// Debug port disable
// JTMS / SWDIO = PA13
// JTCK / SWCLK = PA14
// JTDI         = PA15
// JTDO         = PB3
// NJTRST       = PB4
//
#define DBG_SWCLK _BV(0)
#define DBG_SWDIO _BV(1)
#define DBG_TDO   _BV(2)
#define DBG_TDI   _BV(3)
#define DBG_TRST  _BV(4)
#define DBG_ALL (DBG_SWCLK | DBG_SWDIO | DBG_TDO | DBG_TDI | DBG_TRST)

#define JTAGSWD_RESET() PORT_DebugPortSetting(DBG_ALL, Enable);
#define JTAG_DISABLE() PORT_DebugPortSetting(DBG_TDO | DBG_TDI | DBG_TRST, Disable);
#define JTAGSWD_DISABLE() PORT_DebugPortSetting(DBG_ALL, Disable);

//
// MarlinHAL implementation
//
#include "MarlinHAL.h"
