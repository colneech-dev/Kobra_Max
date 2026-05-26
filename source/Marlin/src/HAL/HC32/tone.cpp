/**
 * Marlin 3D Printer Firmware
 * Copyright (c) 2023 MarlinFirmware [https://github.com/MarlinFirmware/Marlin]
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 */
#ifdef ARDUINO_ARCH_HC32

#include <Arduino.h>

// Software-blocking tone() for HC32 — acceptable for short UI beeps.
// tone() plays for `duration` ms then returns; noTone() silences the pin.

extern "C" {

void tone(gpio_pin_t pin, uint32_t frequency, uint32_t duration) {
  if (frequency == 0) {
    digitalWrite(pin, LOW);
    return;
  }
  const uint32_t half_period_us = 500000UL / frequency;
  const uint32_t end_ms = millis() + (duration ? duration : 1000UL);
  while ((long)(millis() - end_ms) < 0) {
    digitalWrite(pin, HIGH);
    delayMicroseconds(half_period_us);
    digitalWrite(pin, LOW);
    delayMicroseconds(half_period_us);
  }
}

void noTone(gpio_pin_t pin) {
  digitalWrite(pin, LOW);
}

} // extern "C"

#endif // ARDUINO_ARCH_HC32
