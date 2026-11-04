/**
 * Kobra Max: settings in the chip's own flash, two sectors (A / B), so the mesh and the Z offset no longer depend on the SD card.
 *
 *   A = 0x3C000, B = 0x3E000, 8 KB each, above the firmware image (board_upload.maximum_size = 245760 = 0x3C000 - 0x8000), inside a 256 KB chip.
 *   Each copy: 16 byte header { magic, sequence, length, CRC32 of the data } followed by the settings block.
 *   Load: the valid copy with the higher sequence number. Save: erase and write the OTHER sector, the magic word last, and only a
 *   copy that reads back with a correct CRC counts. A power cut during a save therefore always leaves the previous copy intact.
 *
 * Migration: when neither sector holds a valid copy, eeprom.dat (or eeprom.tmp) on the SD card is read once and written to flash.
 * Saves while a print runs (erasing stalls the CPU for tens of milliseconds) are held in RAM and written when the print is over.
 */
#ifdef ARDUINO_ARCH_HC32

#include "../../../inc/MarlinConfig.h"

#if ENABLED(FLASH_EEPROM_EMULATION)

#include "../../shared/eeprom_api.h"
#include "../../../sd/cardreader.h"
#include "../../../MarlinCore.h"
#include "../../../core/serial.h"

#include <hc32_ddl.h>

#ifndef MARLIN_EEPROM_SIZE
  #define MARLIN_EEPROM_SIZE 0x1000 // 4KB
#endif

#define FLASH_SECTOR_A    0x0003C000UL
#define FLASH_SECTOR_B    0x0003E000UL
#define FLASH_SECTOR_SIZE 0x2000UL
#define FLASH_MAGIC       0x4D415842UL   // "MAXB"
#define HEADER_WORDS      4              // magic, sequence, length, crc32
#define DATA_OFFSET       (HEADER_WORDS * 4)

static_assert(MARLIN_EEPROM_SIZE + DATA_OFFSET <= FLASH_SECTOR_SIZE, "the settings block does not fit one flash sector");
static_assert(MARLIN_EEPROM_SIZE % 4 == 0, "the settings block must be a whole number of words");

size_t PersistentStore::capacity() { return MARLIN_EEPROM_SIZE; }

#define _ALIGN(x) __attribute__((aligned(x)))
static char _ALIGN(4) HAL_eeprom_data[MARLIN_EEPROM_SIZE];
static bool     eeprom_dirty   = false;   // set by write_data: a load never writes
static bool     from_sd        = false;   // the block came from eeprom.dat: write it to flash at the end of the access
static bool     pending_write  = false;   // a save was held back (print running)
static uint32_t current_seq    = 0;       // sequence number of the newest valid copy (0 = none)
static uint32_t current_sector = 0;       // its address

static uint32_t crc32_block(const uint8_t *p, size_t n) {
  uint32_t crc = 0xFFFFFFFFUL;
  while (n--) {
    crc ^= *p++;
    for (uint8_t k = 0; k < 8; k++) crc = (crc >> 1) ^ (0xEDB88320UL & (0UL - (crc & 1UL)));
  }
  return ~crc;
}

static inline uint32_t rd32(const uint32_t addr) { return *(const volatile uint32_t*)addr; }

// A copy is valid when the magic is there and the CRC of its data matches. Returns the sequence number, 0 when not valid.
static uint32_t copy_seq(const uint32_t sector) {
  if (rd32(sector) != FLASH_MAGIC) return 0;
  const uint32_t seq = rd32(sector + 4), len = rd32(sector + 8), crc = rd32(sector + 12);
  if (seq == 0 || seq == 0xFFFFFFFFUL || len != MARLIN_EEPROM_SIZE) return 0;
  return crc32_block((const uint8_t*)(sector + DATA_OFFSET), len) == crc ? seq : 0;
}

static void find_current() {
  const uint32_t sa = copy_seq(FLASH_SECTOR_A), sb = copy_seq(FLASH_SECTOR_B);
  if (!sa && !sb)   { current_seq = 0;  current_sector = 0; }
  else if (sa >= sb) { current_seq = sa; current_sector = FLASH_SECTOR_A; }   // (sequence numbers never wrap in practice: 4 billion saves)
  else               { current_seq = sb; current_sector = FLASH_SECTOR_B; }
}

// Erase and program one sector with the settings block. Returns true on error.
static bool write_sector(const uint32_t sector, const uint32_t seq) {
  const uint32_t crc = crc32_block((const uint8_t*)HAL_eeprom_data, MARLIN_EEPROM_SIZE);
  bool error = false;

  EFM_Unlock();
  EFM_FlashCmd(Enable);
  while (Set != EFM_GetFlagStatus(EFM_FLAG_RDY)) { }

  if (EFM_SectorErase(sector) != Ok) error = true;

  // Header words 1..3 and the data first, the magic LAST: a copy is not valid before its magic is there.
  if (!error && EFM_SingleProgramRB(sector + 4, seq) != Ok) error = true;
  if (!error && EFM_SingleProgramRB(sector + 8, MARLIN_EEPROM_SIZE) != Ok) error = true;
  if (!error && EFM_SingleProgramRB(sector + 12, crc) != Ok) error = true;
  for (uint32_t i = 0; !error && i < MARLIN_EEPROM_SIZE; i += 4) {
    uint32_t w;
    memcpy(&w, &HAL_eeprom_data[i], 4);
    if (EFM_SingleProgramRB(sector + DATA_OFFSET + i, w) != Ok) error = true;
  }
  if (!error && EFM_SingleProgramRB(sector, FLASH_MAGIC) != Ok) error = true;

  EFM_Lock();
  return error || copy_seq(sector) != seq;   // must read back as a valid copy
}

static bool flash_store() {
  const uint32_t target = (current_sector == FLASH_SECTOR_A) ? FLASH_SECTOR_B : FLASH_SECTOR_A;   // none yet: A
  const uint32_t seq = current_seq + 1;
  if (write_sector(target, seq)) {
    SERIAL_ECHO_MSG("EEPROM: flash write FAILED, the previous settings are kept");
    return true;
  }
  current_sector = target;
  current_seq = seq;
  return false;
}

// Called from the HAL idle task: a save that was held back during a print is written once the print is over.
void flash_eeprom_service() {
  if (!pending_write || printingIsActive()) return;
  pending_write = false;
  if (!flash_store()) SERIAL_ECHO_MSG("EEPROM: held settings saved to flash");
}

bool PersistentStore::access_start() {
  eeprom_dirty = false;
  from_sd = false;

  if (pending_write) return true;   // a save is waiting: the RAM block is newer than flash, keep it

  find_current();
  if (current_seq) {
    memcpy(HAL_eeprom_data, (const void*)(current_sector + DATA_OFFSET), MARLIN_EEPROM_SIZE);
    return true;
  }

  // No copy in flash: erased block (defaults will be written), or a first start after the SD card days: read eeprom.dat once.
  memset(HAL_eeprom_data, 0xFF, MARLIN_EEPROM_SIZE);
  if (card.isMounted()) {
    MediaFile file, root = card.getroot();
    bool have = file.open(&root, "eeprom.dat", O_RDONLY);
    if (have && file.fileSize() == 0) { file.close(); have = false; }
    if (!have) have = file.open(&root, "eeprom.tmp", O_RDONLY);
    if (have) {
      const int n = file.read(HAL_eeprom_data, MARLIN_EEPROM_SIZE);
      file.close();
      if (n > 0) { from_sd = true; SERIAL_ECHO_MSG("EEPROM: settings taken over from the SD card file"); }
    }
  }
  return true;
}

bool PersistentStore::access_finish() {
  if (!eeprom_dirty && !from_sd) return true;   // only read
  eeprom_dirty = from_sd = false;
  if (printingIsActive()) {                     // erasing stalls the CPU: wait for the end of the print
    pending_write = true;
    SERIAL_ECHO_MSG("EEPROM: save held until the print is over");
    return true;
  }
  pending_write = false;
  const bool error = flash_store();
  if (!error) SERIAL_ECHO_MSG("EEPROM: saved to flash");
  return !error;
}

bool PersistentStore::write_data(int &pos, const uint8_t *value, size_t size, uint16_t *crc) {
  for (size_t i = 0; i < size; i++) HAL_eeprom_data[pos + i] = value[i];
  eeprom_dirty = true;

  crc16(crc, value, size);
  pos += size;
  return false;
}

bool PersistentStore::read_data(int &pos, uint8_t *value, const size_t size, uint16_t *crc, const bool writing /*=true*/) {
  for (size_t i = 0; i < size; i++) {
    const uint8_t c = HAL_eeprom_data[pos + i];
    if (writing) value[i] = c;
    crc16(crc, &c, 1);
  }
  pos += size;
  return false;
}

#endif // FLASH_EEPROM_EMULATION
#endif // ARDUINO_ARCH_HC32
