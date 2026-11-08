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
#include <Timer0.h>
#include <drivers/gpio/gpio.h>
#include "sysclock.h"

// Non-blocking tone() for HC32: tone() starts the sound and returns at once, a timer interrupt toggles the pin and
// stops after `duration` ms (0 = 1000 ms, as the old version; noTone() stops it early). The old version busy-waited on millis(); Marlin's buzzer calls tone()
// with interrupts disabled, so millis() never advanced and the board hung until the watchdog reset it (HW-1).
// Timer0 Unit 1 Channel B (Timer0 Unit 2 is the step / temperature timer; Unit 1 Channel A only runs from the slow LRC).
// The pin stays a plain GPIO output, so Buzzer::off() (WRITE LOW) still silences it.

#define TONE_TIMER_PRESCALE 16UL
#define TONE_TIMER_RATE     (F_PCLK1 / TONE_TIMER_PRESCALE)   // 3.125 MHz

static void tone_isr();
static Timer0 tone_timer(&TIMER01B_config, &tone_isr);

static volatile gpio_pin_t tone_pin = 0;
static volatile uint32_t   tone_halfwaves = 0;   // pin toggles left
static volatile bool       tone_active = false;
static bool                tone_started = false;

static void tone_isr() {
  tone_timer.clearInterruptFlag();
  if (!tone_active) return;
  GPIO_Toggle(tone_pin);
  if (!--tone_halfwaves) {
    tone_active = false;
    GPIO_ResetBits(tone_pin);
    tone_timer.pause();
  }
}

extern "C" {

void noTone(gpio_pin_t pin) {
  tone_active = false;
  tone_timer.pause();
  digitalWrite(pin, LOW);
}

void tone(gpio_pin_t pin, uint32_t frequency, uint32_t duration) {
  if (frequency == 0) { noTone(pin); return; }
  if (frequency < 30) frequency = 30;     // keeps the compare value in 16 bits
  if (frequency > 5000) frequency = 5000; // limits the interrupt rate

  tone_active = false;
  if (tone_started) tone_timer.pause();
  if (pin != tone_pin) pinMode(pin, OUTPUT);
  digitalWrite(pin, LOW);
  tone_pin = pin;

  const uint32_t rate = frequency * 2;   // two toggles per period
  if (!duration) duration = 1000;       // as before: Buzzer::off() cannot stop the interrupt, so no endless tone
  tone_halfwaves = (duration * rate) / 1000UL + 1;

  if (!tone_started) {
    tone_timer.start(rate, TONE_TIMER_PRESCALE);
    tone_timer.setCallbackPriority(DDL_IRQ_PRIORITY_DEFAULT);   // lowest: never delays the step or temperature interrupts
    tone_started = true;
  }
  else {
    tone_timer.setCompareValue(uint16_t(TONE_TIMER_RATE / rate));
    TIMER0_WriteCntReg(M4_TMR01, Tim0_ChannelB, 0);
    tone_timer.resume();
  }
  tone_active = true;
}

} // extern "C"

#endif // ARDUINO_ARCH_HC32
