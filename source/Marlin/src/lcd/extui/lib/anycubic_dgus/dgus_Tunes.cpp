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

/**
 * lcd/extui/lib/Tunes.cpp
 *
 * Extensible_UI implementation for Anycubic Chiron
 * Written By Nick Wells, 2020 [https://github.com/SwiftNick]
 *  (not affiliated with Anycubic, Ltd.)
 */

/***********************************************************************
 * A Utility to play tunes using the buzzer in the printer controller. *
 * See Tunes.h for note and tune definitions.                          *
 ***********************************************************************/

#include "../../../../inc/MarlinConfigPre.h"

#if ENABLED(ANYCUBIC_LCD_DGUS)

#include "dgus_Tunes.h"
#include "../../ui_api.h"
#include "dgus_tft.h"   // Dgus.lcd_info.audio

namespace Anycubic {

  // A tune plays in the background: PlayTune() starts it, TuneService() (IdleLoop) starts the next note when the last one is over.
  // It used to block for the length of the tune (3.5 s for the power-on jingle) inside callbacks and the touch handler.
  // Not played when sound is switched off in the System menu; a new tune replaces one still playing.
  static const uint16_t *tune_cur = nullptr;
  static uint8_t  tune_pin = 0, tune_pos = 1;
  static uint16_t tune_whole = 0;
  static millis_t tune_next = 0;

  void TuneService() {
    if (!tune_cur || PENDING(millis(), tune_next)) return;
    if (tune_pos >= MAX_TUNE_LENGTH || tune_cur[tune_pos] == n_END) { tune_cur = nullptr; return; }
    const uint16_t freq = tune_cur[tune_pos], notelen = tune_whole / tune_cur[tune_pos + 1];
    ::tone(tune_pin, freq, notelen);
    tune_next = millis() + notelen;
    tune_pos += 2;
  }

  void PlayTune(uint8_t beeperPin, const uint16_t *tune, uint8_t speed) {
    if (Dgus.lcd_info.audio == ExtUI::OFF) return;
    tune_cur = tune; tune_pin = beeperPin; tune_pos = 1;
    tune_whole = tune[0] / (speed ? speed : 1);
    tune_next = millis();
    TuneService();
  }

}

#endif // ANYCUBIC_LCD_DGUS
