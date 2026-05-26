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

#ifdef ARDUINO_ARCH_HC32

#include "HAL.h"
#include <core_hooks.h>
#include <drivers/panic/panic.h>

// Anycubic Kobra Max uses fan_pwm_set_ratio() in controllerfan.cpp.
// Map fan indices to the board's physical fan pins.
void fan_pwm_set_ratio(uint8_t fan, uint8_t ratio) {
  switch (fan) {
    case 0: analogWrite(pin_t(FAN_PIN),  ratio); break;
    case 1: analogWrite(pin_t(FAN1_PIN), ratio); break;
    case 2: analogWrite(pin_t(FAN2_PIN), ratio); break;
    default: break;
  }
}

//
// Emergency Parser
//
#if ENABLED(EMERGENCY_PARSER)

extern "C" void core_hook_usart_rx_irq(uint8_t ch, uint8_t usart) {
  // Return if this is NOT a host serial port (filter using AND — usart must match one of the ports)
  if (true
    #ifdef SERIAL_PORT
      && usart != SERIAL_PORT
    #endif
    #ifdef SERIAL_PORT_2
      && usart != SERIAL_PORT_2
    #endif
    #ifdef SERIAL_PORT_3
      && usart != SERIAL_PORT_3
    #endif
  ) {
    return;
  }

  // Submit character to the emergency parser of the matching serial instance
  #ifdef SERIAL_PORT
    if (usart == SERIAL_PORT && MYSERIAL1.emergency_parser_enabled())
      emergency_parser.update(MYSERIAL1.emergency_state, ch);
  #endif
  #ifdef SERIAL_PORT_2
    if (usart == SERIAL_PORT_2 && MYSERIAL2.emergency_parser_enabled())
      emergency_parser.update(MYSERIAL2.emergency_state, ch);
  #endif
  #ifdef SERIAL_PORT_3
    if (usart == SERIAL_PORT_3 && MYSERIAL3.emergency_parser_enabled())
      emergency_parser.update(MYSERIAL3.emergency_state, ch);
  #endif
}

#endif // EMERGENCY_PARSER
#endif // ARDUINO_ARCH_HC32
