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

// Forward declarations needed before MarlinConfig.h circular include.
// The top-level HAL/HAL.h defines watchdog_refresh() calling HAL_watchdog_refresh(),
// which isn't defined until later in this file. Declaring it here breaks the cycle.
inline void HAL_watchdog_refresh();

#include "../../inc/MarlinConfig.h"

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
#if ENABLED(EMERGENCY_PARSER)
  extern "C" void usart_rx_irq_hook(uint8_t ch, uint8_t usart);
#endif

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

//
// 2.0.8 free-function HAL API bridged to 2.1.x MarlinHAL class methods
//
inline void HAL_init()                { MarlinHAL::init(); }
inline void HAL_init_board()          { MarlinHAL::init_board(); }
inline void HAL_idletask()            { MarlinHAL::idletask(); }
inline void HAL_watchdog_init()       { MarlinHAL::watchdog_init(); }
inline void HAL_watchdog_refresh()    { MarlinHAL::watchdog_refresh(); }
inline void watchdog_init()           { MarlinHAL::watchdog_init(); }
inline void HAL_reboot()              { MarlinHAL::reboot(); }
inline uint8_t HAL_get_reset_source() { return MarlinHAL::get_reset_source(); }
inline void HAL_clear_reset_source()  { MarlinHAL::clear_reset_source(); }
inline void HAL_adc_init()            { MarlinHAL::adc_init(); }

inline void set_pwm_duty(const pin_t pin, const uint16_t v,
                         const uint16_t scale=255, const bool invert=false) {
  MarlinHAL::set_pwm_duty(pin, v, scale, invert);
}
inline void set_pwm_frequency(const pin_t pin, const uint16_t f) {
  MarlinHAL::set_pwm_frequency(pin, f);
}

#define HAL_START_ADC(pin)  do { MarlinHAL::adc_enable(pin); MarlinHAL::adc_start(pin); } while(0)
#define HAL_ADC_READY()     MarlinHAL::adc_ready()
#define HAL_READ_ADC()      MarlinHAL::adc_value()

// 2.0.8 ADC vref alias: 2.1.x HC32 HAL uses HAL_ADC_VREF_MV
#ifndef HAL_ADC_VREF
  #define HAL_ADC_VREF HAL_ADC_VREF_MV
#endif

// 2.0.8 free-function alias for MarlinHAL::freeMemory()
inline int freeMemory() { return MarlinHAL::freeMemory(); }

#define HAL_IDLETASK 1
