#include "settings.h"
#include "board.h"
#include "trip.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

#define SET_MAGIC   0x46585354u   /* "FXST" */
#define SET_VERSION 2u

settings_t g_set;

static uint32_t crc32(const uint8_t *p, size_t n)
{
    uint32_t c = 0xFFFFFFFFu;
    for (size_t i = 0; i < n; ++i) {
        c ^= p[i];
        for (int k = 0; k < 8; ++k) c = (c >> 1) ^ (0xEDB88320u & (0u - (c & 1u)));
    }
    return ~c;
}

void settings_defaults(settings_t *s, int rack)
{
    memset(s, 0, sizeof *s);
    s->magic = SET_MAGIC; s->version = SET_VERSION;
    s->role = rack ? 1u : 0u;
    if (rack) {                                  /* SCALING_SHEET §3.6: 1 mOhm shunt x20, FS 13 x rated at 2.6 V */
        s->I_rated = 10.0; s->V_ref = 12.0;
        s->fs_i = 130.0; s->fs_v = 15.0;
        s->gain_i = (float)(130.0 / 65536.0 * 3.3 / 2.6);   /* A per code, to be replaced by calibration */
        s->gain_v = (float)(3.3 * (24.7 / 4.7) / 65536.0);  /* V per code, 20k / 4.7k divider */
    } else {                                     /* 10 mOhm x50, FS 2 x rated */
        s->I_rated = 2.5; s->V_ref = 48.0;
        s->fs_i = 5.0; s->fs_v = 60.0;
        s->gain_i = (float)(5.0 / 65536.0);
        s->gain_v = (float)(3.3 * (104.99 / 4.99) / 65536.0); /* 100k / 4.99k divider */
    }
    s->offset_i = 0; s->offset_v = 0;
    s->theta = 0.5;
    s->l1_di = INFINITY; s->l1_v = -INFINITY;
    s->model_id = 0; s->can_id = rack ? 0x102u : 0x101u;
    s->can_wait_us = 50; s->onset_tol_samples = 500;
}

void settings_load(void)
{
    const settings_t *f = (const settings_t *)SETTINGS_FLASH_ADDR;
    if (f->magic == SET_MAGIC && f->version == SET_VERSION &&
        f->crc == crc32((const uint8_t *)f, offsetof(settings_t, crc))) {
        g_set = *f;
    } else {
        settings_defaults(&g_set, role_is_rack());
    }
}

int settings_save(void)
{
    g_set.crc = crc32((const uint8_t *)&g_set, offsetof(settings_t, crc));
    static uint8_t buf[((sizeof(settings_t) + 31u) / 32u) * 32u] __attribute__((aligned(32)));
    memset(buf, 0xFF, sizeof buf);
    memcpy(buf, &g_set, sizeof g_set);
    HAL_FLASH_Unlock();
    FLASH_EraseInitTypeDef e = { 0 };
    e.TypeErase = FLASH_TYPEERASE_SECTORS;
    e.Banks = SETTINGS_FLASH_BANK;
    e.Sector = SETTINGS_FLASH_SECT;
    e.NbSectors = 1;
    e.VoltageRange = FLASH_VOLTAGE_RANGE_3;
    uint32_t err = 0;
    int rc = 0;
    if (HAL_FLASHEx_Erase(&e, &err) != HAL_OK) rc = -1;
    for (uint32_t off = 0; rc == 0 && off < sizeof buf; off += 32u)
        if (HAL_FLASH_Program(FLASH_TYPEPROGRAM_FLASHWORD, SETTINGS_FLASH_ADDR + off, (uint32_t)(buf + off)) != HAL_OK) rc = -2;
    HAL_FLASH_Lock();
    return rc;
}

int settings_set(const char *key, const char *val)
{
    double d = atof(val);
    if (!strcmp(key, "role")) g_set.role = (uint32_t)atoi(val);
    else if (!strcmp(key, "I_rated")) g_set.I_rated = d;
    else if (!strcmp(key, "V_ref")) g_set.V_ref = d;
    else if (!strcmp(key, "fs_i")) g_set.fs_i = d;
    else if (!strcmp(key, "fs_v")) g_set.fs_v = d;
    else if (!strcmp(key, "gain_i")) g_set.gain_i = (float)d;
    else if (!strcmp(key, "gain_v")) g_set.gain_v = (float)d;
    else if (!strcmp(key, "offset_i")) g_set.offset_i = (uint32_t)atoi(val);
    else if (!strcmp(key, "offset_v")) g_set.offset_v = (uint32_t)atoi(val);
    else if (!strcmp(key, "theta")) g_set.theta = d;
    else if (!strcmp(key, "l1_di")) g_set.l1_di = (!strcmp(val, "off")) ? INFINITY : d;
    else if (!strcmp(key, "l1_v")) g_set.l1_v = (!strcmp(val, "off")) ? -INFINITY : d;
    else if (!strcmp(key, "model_id")) g_set.model_id = (uint32_t)atoi(val);
    else if (!strcmp(key, "can_id")) g_set.can_id = (uint32_t)strtoul(val, NULL, 0);
    else if (!strcmp(key, "can_wait_us")) g_set.can_wait_us = (uint32_t)atoi(val);
    else if (!strcmp(key, "onset_tol")) g_set.onset_tol_samples = (uint32_t)atoi(val);
    else return -1;
    return 0;
}

void settings_print(void (*out)(const char *))
{
    char line[96];
    const settings_t *s = &g_set;
    snprintf(line, sizeof line, "role %lu (%s)\r\n", (unsigned long)s->role, s->role ? "rack" : "feeder"); out(line);
    snprintf(line, sizeof line, "I_rated %.6g V_ref %.6g fs_i %.6g fs_v %.6g\r\n", s->I_rated, s->V_ref, s->fs_i, s->fs_v); out(line);
    snprintf(line, sizeof line, "gain_i %.9g gain_v %.9g offset_i %lu offset_v %lu\r\n", (double)s->gain_i, (double)s->gain_v,
             (unsigned long)s->offset_i, (unsigned long)s->offset_v); out(line);
    snprintf(line, sizeof line, "theta %.4g l1_di %.4g l1_v %.4g model_id %lu can_id 0x%lx\r\n", s->theta, s->l1_di, s->l1_v,
             (unsigned long)s->model_id, (unsigned long)s->can_id); out(line);
    snprintf(line, sizeof line, "can_wait_us %lu onset_tol %lu samples\r\n", (unsigned long)s->can_wait_us,
             (unsigned long)s->onset_tol_samples); out(line);
}
