/**
 * Marlin 3D Printer Firmware
 *
 * Copyright (c) 2020 MarlinFirmware [https://github.com/MarlinFirmware/Marlin]
 * Copyright (c) 2016 Bob Cousins bobcousins42@googlemail.com
 * Copyright (c) 2015-2016 Nico Tonnhofer wurstnase.reprap@gmail.com
 * Copyright (c) 2016 Victor Perez victor_pv@hotmail.com
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

#include <stddef.h>
#include <stdint.h>

#include "../../libs/crc16.h"
#ifndef ARDUINO_ARCH_HC32
  #include "../../cores/flash.h"

  enum
  {
    FLASHIF_OK = 0,
    FLASHIF_ERASEKO,
    FLASHIF_WRITINGCTRL_ERROR,
    FLASHIF_WRITING_ERROR,
    FLASHIF_PROTECTION_ERRROR
  };
#endif



class PersistentStore {
public:
  // 2.1.x: reserved bytes excluded from EEPROM capacity (0 for all current backends)
  static constexpr int eeprom_exclude_size = 0;

  // Total available persistent storage space (in bytes)
  static size_t capacity();

  // Prepare to read or write
  static bool access_start();

  // Housecleaning after read or write
  static bool access_finish();

  // Write one or more bytes of data and update the CRC
  // Return 'true' on write error
  static bool write_data(int &pos, const uint8_t *value, size_t size, uint16_t *crc);

  // Read one or more bytes of data and update the CRC
  // Return 'true' on read error
  static bool read_data(int &pos, uint8_t* value, size_t size, uint16_t *crc, const bool writing=true);

  // Write one or more bytes of data
  // Return 'true' on write error
  static inline bool write_data(const int pos, const uint8_t* value, const size_t size=sizeof(uint8_t)) {
    int data_pos = pos;
    uint16_t crc = 0;
    return write_data(data_pos, value, size, &crc);
  }

  // Write a single byte of data
  // Return 'true' on write error
  static inline bool write_data(const int pos, const uint8_t value) { return write_data(pos, &value); }

  // Read one or more bytes of data
  // Return 'true' on read error
  static inline bool read_data(const int pos, uint8_t* value, const size_t size=1) {
    int data_pos = pos;
    uint16_t crc = 0;
    return read_data(data_pos, value, size, &crc);
  }

#ifndef ARDUINO_ARCH_HC32
  static uint32_t FLASH_If_Erase(uint32_t addr_start, uint32_t addr_end);
  static uint32_t FLASH_If_Write(uint32_t destination, const void *p_source, uint32_t length);
#endif
};

extern PersistentStore persistentStore;
