/* settings.h — node settings in flash (FIRMWARE_SPEC.md §8): role, ratings, calibration, theta,
 * Layer-1 thresholds, model id, CAN id. */
#ifndef SETTINGS_H
#define SETTINGS_H
#include <stdint.h>

typedef struct {
    uint32_t magic, version;
    uint32_t role;            /* 0 feeder, 1 rack */
    double I_rated, V_ref;    /* per-unit base of the features (bench: rack 10 A / 12 V, feeder 2.5 A / 48 V) */
    double fs_i, fs_v;        /* full scales for the onset threshold floor 0.004*fs (physical units) */
    float gain_i, gain_v;     /* physical units per code */
    uint32_t offset_i, offset_v;
    double theta;             /* P(TRIP) threshold */
    double l1_di, l1_v;       /* Layer 1 (p.u.); +inf / -inf = off */
    uint32_t model_id;        /* 0 = by role, 1 feeder, 2 rack, 3 both */
    uint32_t can_id;
    uint32_t can_wait_us;     /* feeder: wait for the rack features after its window close (§7.3, default 50) */
    uint32_t onset_tol_samples; /* rack onset must be within this many samples of the feeder's (default 500 = 1 ms) */
    uint32_t crc;
} settings_t;

extern settings_t g_set;
void settings_load(void);                    /* flash if valid, else defaults for the jumpered role */
void settings_defaults(settings_t *s, int rack);
int  settings_save(void);                    /* 0 ok */
int  settings_set(const char *key, const char *val);   /* 0 ok, -1 unknown key */
void settings_print(void (*out)(const char *));

#endif
