/**
 * Kobra Max: settings in the chip's own flash, two sectors (A / B), so the mesh and the Z offset no longer depend on the SD card.
 *
 *   A = 0x3C000, B = 0x3E000, 8 KB each, above the firmware image (board_upload.maximum_size = 245760 = 0x3C000 - 0x8000), inside a 256 KB chip.
 *   Each copy: 16 byte header { magic, sequence, length, CRC32 } followed by the settings block. The CRC covers the sequence, the length
 *   and the data (magic "MAXC"); copies written before that (magic "MAXB", CRC of the data only) are still read.
 *   Load: the valid copy with the higher sequence number. Save: erase and write the OTHER sector, the magic word last, and only a
 *   copy that reads back with a correct CRC counts. A power cut during a save therefore always leaves the previous copy intact.
 *   A save whose data equals the current copy writes nothing (each sector takes about 10,000 erases).
 *
 * Migration: when neither sector holds a valid copy, eeprom.dat (or eeprom.tmp) on the SD card is read once and written to flash.
 *
 * Saves while the printer moves are HELD: erasing / programming stalls the CPU (code runs from flash) for tens of milliseconds, so every
 * interrupt waits, the stepper included. A save during a print, or while moves are queued or babysteps pending, stays in RAM and is
 * written from the idle task once the print is over and the planner is empty. The caller (M500, the display) is told "success" at once:
 * a power cut before the end of the print loses that save (the About page shows "held" meanwhile).
 */
#ifdef ARDUINO_ARCH_HC32

#include "../../../inc/MarlinConfig.h"

#if ENABLED(FLASH_EEPROM_EMULATION)

#include "../../shared/eeprom_api.h"
#include "../../../sd/cardreader.h"
#include "../../../MarlinCore.h"
#include "../../../core/serial.h"
#include "../../../module/planner.h"
#if ENABLED(BABYSTEPPING)
  #include "../../../feature/babystep.h"
#endif

#include <hc32_ddl.h>

#ifndef MARLIN_EEPROM_SIZE
  #define MARLIN_EEPROM_SIZE 0x1000 // 4KB
#endif

#define FLASH_SECTOR_A    0x0003C000UL
#define FLASH_SECTOR_B    0x0003E000UL
#define FLASH_SECTOR_SIZE 0x2000UL
#define FLASH_MAGIC       0x4D415843UL   // "MAXC": CRC over sequence, length and data
#define FLASH_MAGIC_OLD   0x4D415842UL   // "MAXB": CRC over the data only (read, never written)
#define HEADER_WORDS      4              // magic, sequence, length, crc32
#define DATA_OFFSET       (HEADER_WORDS * 4)

static_assert(MARLIN_EEPROM_SIZE + DATA_OFFSET <= FLASH_SECTOR_SIZE, "the settings block does not fit one flash sector");
static_assert(MARLIN_EEPROM_SIZE % 4 == 0, "the settings block must be a whole number of words");

// Linker symbols: the end of the firmware image in flash (as upstream's eeprom_sector_free())
extern "C" char __etext_ret_ram[], __data_start_ret_ram__[], __data_end_ret_ram__[];

size_t PersistentStore::capacity() { return MARLIN_EEPROM_SIZE; }

#define _ALIGN(x) __attribute__((aligned(x)))
static char _ALIGN(4) HAL_eeprom_data[MARLIN_EEPROM_SIZE];
static bool     eeprom_dirty   = false;   // set by write_data: a load never writes
static bool     from_sd        = false;   // the block came from eeprom.dat: write it to flash at the end of the access
static bool     pending_write  = false;   // a save was held back (printer busy)
static uint32_t current_seq    = 0;       // sequence number of the newest valid copy (0 = none)
static uint32_t current_sector = 0;       // its address
static bool     last_save_failed = false;

static uint32_t crc32_add(uint32_t crc, const uint8_t *p, size_t n) {
  while (n--) {
    crc ^= *p++;
    for (uint8_t k = 0; k < 8; k++) crc = (crc >> 1) ^ (0xEDB88320UL & (0UL - (crc & 1UL)));
  }
  return crc;
}

// CRC of a copy: new format = sequence and length (as stored, little endian) then the data; old format = the data only
static uint32_t copy_crc(const bool with_header, const uint32_t seq, const uint32_t len, const uint8_t *data) {
  uint32_t crc = 0xFFFFFFFFUL;
  if (with_header) {
    const uint32_t hdr[2] = { seq, len };
    crc = crc32_add(crc, (const uint8_t*)hdr, sizeof(hdr));
  }
  return ~crc32_add(crc, data, len);
}

static inline uint32_t rd32(const uint32_t addr) { return *(const volatile uint32_t*)addr; }

// A copy is valid when the magic is there and the CRC matches. Returns the sequence number, 0 when not valid.
static uint32_t copy_seq(const uint32_t sector) {
  const uint32_t magic = rd32(sector);
  if (magic != FLASH_MAGIC && magic != FLASH_MAGIC_OLD) return 0;
  const uint32_t seq = rd32(sector + 4), len = rd32(sector + 8), crc = rd32(sector + 12);
  if (seq == 0 || seq == 0xFFFFFFFFUL || len != MARLIN_EEPROM_SIZE) return 0;
  return copy_crc(magic == FLASH_MAGIC, seq, len, (const uint8_t*)(sector + DATA_OFFSET)) == crc ? seq : 0;
}

static void find_current() {
  const uint32_t sa = copy_seq(FLASH_SECTOR_A), sb = copy_seq(FLASH_SECTOR_B);
  if (!sa && !sb)   { current_seq = 0;  current_sector = 0; }
  else if (sa >= sb) { current_seq = sa; current_sector = FLASH_SECTOR_A; }   // (sequence numbers never wrap in practice: 4 billion saves)
  else               { current_seq = sb; current_sector = FLASH_SECTOR_B; }
}

// The firmware image must end below the settings sectors: an erase there would destroy code (the build limit
// board_upload.maximum_size should already prevent it, this also covers a changed limit or linker script)
static bool sectors_free() {
  const uint32_t image_end = uint32_t(__etext_ret_ram) + uint32_t(__data_end_ret_ram__ - __data_start_ret_ram__);
  return image_end <= FLASH_SECTOR_A;
}

// Erase and program one sector with the settings block. Returns true on error.
static bool write_sector(const uint32_t sector, const uint32_t seq) {
  const uint32_t crc = copy_crc(true, seq, MARLIN_EEPROM_SIZE, (const uint8_t*)HAL_eeprom_data);
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

  // Drop what the flash data cache still holds of the old sector contents, so the read-back below (and later
  // loads) see the new data. FRMC is write protected, so this is done before the lock.
  EFM_DataCacheRstCmd(Enable);
  EFM_DataCacheRstCmd(Disable);

  EFM_Lock();
  return error || copy_seq(sector) != seq;   // must read back as a valid copy
}

static bool flash_store() {
  // Same data as the current copy: nothing to write (saves the sector an erase cycle)
  if (current_seq && !memcmp(HAL_eeprom_data, (const void*)(current_sector + DATA_OFFSET), MARLIN_EEPROM_SIZE)) {
    last_save_failed = false;
    SERIAL_ECHO_MSG("EEPROM: settings unchanged");
    return false;
  }
  if (!sectors_free()) {
    SERIAL_ERROR_MSG("EEPROM: the firmware reaches the settings flash, NOT saved");
    last_save_failed = true;
    return true;
  }
  const uint32_t target = (current_sector == FLASH_SECTOR_A) ? FLASH_SECTOR_B : FLASH_SECTOR_A;   // none yet: A
  const uint32_t seq = current_seq + 1;
  if (write_sector(target, seq)) {
    SERIAL_ECHO_MSG("EEPROM: flash write FAILED, the previous settings are kept");
    last_save_failed = true;
    return true;
  }
  last_save_failed = false;
  current_sector = target;
  current_seq = seq;
  SERIAL_ECHO_MSG("EEPROM: saved to flash");
  return false;
}

// Writing to flash stalls every interrupt: never while a print runs, moves are queued or babysteps are pending
static bool flash_write_blocked() {
  return printingIsActive() || planner.busy() || TERN0(BABYSTEPPING, babystep.has_steps());
}

// For the About page: save counter, current sector ('A' / 'B' / '-'), a failed or held save.
uint32_t flash_eeprom_seq() { return current_seq; }
char     flash_eeprom_sector() { return current_sector == FLASH_SECTOR_A ? 'A' : current_sector == FLASH_SECTOR_B ? 'B' : '-'; }
bool     flash_eeprom_failed() { return last_save_failed; }
bool     flash_eeprom_pending() { return pending_write; }

// Called from the HAL idle task: a save that was held back is written once the printer is idle.
void flash_eeprom_service() {
  if (!pending_write || flash_write_blocked()) return;
  pending_write = false;
  flash_store();
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
  if (flash_write_blocked()) {                  // held in RAM, written by flash_eeprom_service() (see the top of the file)
    if (!pending_write) SERIAL_ECHO_MSG("EEPROM: save held until the printer is idle");
    pending_write = true;
    return true;
  }
  pending_write = false;
  return !flash_store();
}

bool PersistentStore::write_data(int &pos, const uint8_t *value, size_t size, uint16_t *crc) {
  if (pos < 0 || size_t(pos) + size > MARLIN_EEPROM_SIZE) return true;   // would run past the block
  for (size_t i = 0; i < size; i++) HAL_eeprom_data[pos + i] = value[i];
  eeprom_dirty = true;

  crc16(crc, value, size);
  pos += size;
  return false;
}

bool PersistentStore::read_data(int &pos, uint8_t *value, const size_t size, uint16_t *crc, const bool writing /*=true*/) {
  if (pos < 0 || size_t(pos) + size > MARLIN_EEPROM_SIZE) return true;   // would run past the block
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
