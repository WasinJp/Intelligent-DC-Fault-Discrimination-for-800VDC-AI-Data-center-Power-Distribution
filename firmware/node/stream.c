#include "stream.h"
#include "board.h"
#include "settings.h"
#include "timing.h"
#include "trip.h"
#include "cadence_task.h"
#include "can_link.h"
#include "usb_upload.h"
#include "fx_onset.h"
#include "fx_model.h"
#include "fx_can.h"
#include "fx_upload.h"
#include <string.h>
#include <stdio.h>
#include <math.h>

/* big buffers: D2 SRAM (AXI SRAM holds the cadence history and learner, cadence_task.c) */
__attribute__((section(".ram_d2"))) static uint16_t ring_i[RING_N], ring_v[RING_N];
__attribute__((section(".ram_d2"))) static double rec_i[FX_N_REC_MAX], rec_v[FX_N_REC_MAX];
__attribute__((section(".ram_d2"))) static fx_work_t g_work;
__attribute__((section(".ram_d2"))) static uint8_t g_upload_buf[FX_UPLOAD_HEAD_BYTES + FX_REC_HEADER_BYTES + 4 * FX_N_REC + FX_UPLOAD_TRAILER_BYTES + 4];
__attribute__((section(".ram_d2"))) static uint16_t g_up_i[FX_N_REC], g_up_v[FX_N_REC];

static volatile uint32_t g_count;          /* absolute number of samples acquired */
static fx_onset_stream_t g_det;
static fx_relay_cfg_t g_cfg;
static const fx_model_t *g_model, *g_model_both;
static volatile int g_pending;             /* onset detected, waiting for the window close */
static volatile uint32_t g_k_on, g_cyc_onset, g_cyc_close;
static decision_t g_last;
static volatile uint32_t g_sync_sample;
static volatile int g_upload_pending, g_capture_request;
static uint32_t g_upload_k_on;

static const fx_model_t *pick_model(void)
{
    const fx_model_t *m = NULL;
    switch (g_set.model_id) {
    case 1: m = fx_model_get("feeder"); break;
    case 2: m = fx_model_get("rack"); break;
    case 3: m = fx_model_get("both"); break;
    default: m = fx_model_get(g_set.role ? "rack" : "feeder"); break;
    }
    return m ? m : fx_model_at(0);
}

void stream_init(void)
{
    g_count = 0; g_pending = 0; g_sync_sample = 0; g_upload_pending = 0; g_capture_request = 0;
    memset(&g_last, 0, sizeof g_last);
    fx_relay_cfg_default(&g_cfg);
    g_cfg.theta = g_set.theta; g_cfg.l1_di = g_set.l1_di; g_cfg.l1_v = g_set.l1_v;
    g_model = pick_model();
    g_model_both = fx_model_get("both");
    fx_onset_stream_init(&g_det, g_set.fs_i, g_set.fs_v);
    NVIC_SetPriority(PendSV_IRQn, PRIO_PENDSV);
}

void stream_arm(void)
{
    trip_clear();
    alert_set(0);
    g_pending = 0;
    fx_onset_stream_init(&g_det, g_set.fs_i, g_set.fs_v);
    g_last.valid = 0;
}

int stream_detector_armed(void) { return g_det.armed; }
uint32_t stream_sample_count(void) { return g_count; }
const decision_t *stream_last(void) { return &g_last; }
void stream_sync_mark(void) { g_sync_sample = g_count; }
void stream_capture_request(void) { g_capture_request = 1; }

static inline double code_to_phys(uint16_t code, uint32_t offset, float gain)
{
    return (double)((float)((int)code - (int)offset) * gain);   /* the fx_record conversion */
}

void stream_on_block(const uint32_t *words, int n)
{
    uint32_t t0 = dwt_now();
    uint32_t c = g_count;
    for (int k = 0; k < n; ++k) {
        uint16_t ci = (uint16_t)(words[k] & 0xFFFFu), cv = (uint16_t)(words[k] >> 16);
        ring_i[c & (RING_N - 1)] = ci;
        ring_v[c & (RING_N - 1)] = cv;
        double fi = code_to_phys(ci, g_set.offset_i, g_set.gain_i);
        double fv = code_to_phys(cv, g_set.offset_v, g_set.gain_v);
        cadence_push_fast(fi);                                    /* 100:1 anti-alias decimation -> history */
        /* Layer 1 on the stream against the detector's running baseline (§7.1) */
        if (!g_pending && g_det.armed && g_det.k > FX_N_PRE + FX_STREAM_PRE_END &&
            (isfinite(g_cfg.l1_di) || isfinite(g_cfg.l1_v))) {
            double i_pre = g_det.sum_i / (double)FX_N_PRE;
            double di = fabs(fi - i_pre) / g_set.I_rated, vpu = fv / g_set.V_ref;
            if (fx_relay_layer1(&g_cfg, di, vpu)) {
                trip_set();
                g_last.valid = 1; g_last.layer = 1; g_last.k_on = c; g_last.r.decision = FX_DEC_TRIP;
                g_det.armed = 0; g_det.holdoff = FX_STREAM_HOLDOFF;
            }
        }
        if (fx_onset_stream_push(&g_det, fi, fv) && !g_pending) {
            onset_pulse_begin();
            g_k_on = c;
            g_cyc_onset = dwt_now();
            g_pending = 1;
        }
        c++;
    }
    g_count = c;
    if (g_pending && c >= g_k_on + (uint32_t)FX_N_W_025) {
        g_cyc_close = dwt_now();
        SCB->ICSR = SCB_ICSR_PENDSVSET_Msk;      /* decide at lower priority: the DMA keeps flowing */
    }
    timing_add(T_DETECT_BLOCK, dwt_now() - t0);
}

void stream_decide(void)
{
    if (!g_pending) return;
    uint32_t t0 = dwt_now();
    const uint32_t k_on = g_k_on;
    const uint32_t start = (uint32_t)g_det.rec_start;             /* baseline window start (fx_onset.h) */
    int n = (int)(k_on + (uint32_t)FX_N_W_025 - start);           /* samples available at the window close */
    if (n > FX_N_REC_MAX) n = FX_N_REC_MAX;
    for (int k = 0; k < n; ++k) {
        uint32_t idx = (start + (uint32_t)k) & (RING_N - 1);
        rec_i[k] = code_to_phys(ring_i[idx], g_set.offset_i, g_set.gain_i);
        rec_v[k] = code_to_phys(ring_v[idx], g_set.offset_v, g_set.gain_v);
    }
    fx_stream_t s = { rec_i, rec_v, n, FX_FS_FAST, g_set.fs_i, g_set.fs_v };
    decision_t d;
    memset(&d, 0, sizeof d);
    int rc = fx_features_extract(&s, FX_W_025, g_set.I_rated, g_set.V_ref, &g_work, &d.f);
    if (rc == 0) {
        /* WORK features from the published cadence tiers (M5), t_on in the node time base */
        uint32_t gen;
        const fx_cadence_tiers_t *tiers = cadence_published(&gen);
        double t_on = (double)k_on / FX_FS_FAST;
        if (tiers) fx_cadence_work_features(tiers, t_on, &d.f.has_period, &d.f.period_strength, &d.f.phase_err);
    }
    uint32_t t1 = dwt_now();
    double x[FX_N_FEATURES];
    int used_two_node = 0;
    if (rc == 0) {
        fx_features_vector(&d.f, x);
        if (g_set.role == 0 && g_model_both) {
            /* feeder (§7.3): use the rack's features if they are here, else wait up to can_wait_us */
            fx_can_features_t rack; uint32_t rx_sample;
            uint32_t deadline = g_count + (uint32_t)(g_set.can_wait_us * FX_FS_FAST / 1e6);
            int have = can_peer_features(&rack, &rx_sample);
            while (!have && (int32_t)(deadline - g_count) > 0) have = can_peer_features(&rack, &rx_sample);
            fx_combined_decide(&g_cfg, g_model, g_model_both, x, have ? &rack : NULL, k_on,
                               (uint32_t)g_set.onset_tol_samples, &d.r, &used_two_node);
        } else {
            fx_relay_layer2(&g_cfg, g_model, x, &d.r);
        }
        if (d.r.decision == FX_DEC_TRIP) trip_set();
        else if (d.r.decision == FX_DEC_ALERT) alert_set(1);
    }
    uint32_t t2 = dwt_now();
    onset_pulse_end();
    /* CAN: summary within 20 us of the close, then the features (M6) */
    if (rc == 0) {
        fx_can_summary_t sm = { (uint8_t)g_set.role, (uint8_t)d.r.decision, (uint8_t)(d.f.has_period > 0.5), (uint8_t)(used_two_node ? 2 : 0),
                                (float)d.r.p_trip, (float)d.f.phase_err, k_on };
        can_send_summary(&sm);
        fx_can_features_t ft; memset(&ft, 0, sizeof ft);
        ft.node = (uint8_t)g_set.role; ft.onset_sample = k_on; memcpy(ft.x, x, sizeof x);
        can_send_features(&ft);
    }
    d.valid = 1; d.layer = 2; d.k_on = k_on; d.rec_start = start; d.used_two_node = used_two_node;
    d.cyc_extract = t1 - t0; d.cyc_infer = t2 - t1;
    d.cyc_close_to_trip = t2 - g_cyc_close; d.cyc_onset_to_trip = t2 - g_cyc_onset;
    d.sync_sample = g_sync_sample;
    g_last = d;
    timing_add(T_EXTRACT, d.cyc_extract);
    timing_add(T_INFER, d.cyc_infer);
    timing_add(T_CLOSE_TO_TRIP, d.cyc_close_to_trip);
    timing_add(T_ONSET_TO_TRIP, d.cyc_onset_to_trip);
    g_upload_k_on = k_on; g_upload_pending = 1;                   /* record upload at k_on + 2500 (§8) */
    g_pending = 0;
}

/* ---------------------------------------------------------------- record upload (§8, M6) */
static void build_and_send(uint32_t k_on, const decision_t *d, int is_capture)
{
    /* the record starts where the decision's record started (baseline window), so the host's
     * record-mode extraction on the uploaded record reproduces the node's features exactly */
    uint32_t start = (!is_capture && d->valid) ? d->rec_start : (k_on >= FX_N_REC_PRE ? k_on - FX_N_REC_PRE : 0);
    for (int k = 0; k < FX_N_REC; ++k) {
        uint32_t idx = (start + (uint32_t)k) & (RING_N - 1);
        g_up_i[k] = ring_i[idx]; g_up_v[k] = ring_v[idx];
    }
    fx_record_header_t h; memset(&h, 0, sizeof h);
    h.n_fast = FX_N_REC; h.n_slow = 0; h.fs_fast = (float)FX_FS_FAST; h.fs_slow = (float)FX_FS_SLOW;
    h.gain_i = g_set.gain_i; h.gain_v = g_set.gain_v; h.offset_i = (uint16_t)g_set.offset_i; h.offset_v = (uint16_t)g_set.offset_v;
    h.I_rated = g_set.I_rated; h.V_ref = g_set.V_ref; h.fs_i = g_set.fs_i; h.fs_v = g_set.fs_v;
    h.t0_fast = (double)start / FX_FS_FAST; h.t_event = (double)k_on / FX_FS_FAST;
    h.node = (uint8_t)g_set.role; h.adc_bits = 16; h.slow_format = FX_REC_SLOW_NONE;
    snprintf(h.event_id, sizeof h.event_id, "n%08lx", (unsigned long)k_on);
    snprintf(h.label, sizeof h.label, is_capture ? "capture" : "bench");
    fx_upload_trailer_t t; memset(&t, 0, sizeof t);
    t.k_on = k_on; t.sample_count = g_count; t.sync_sample = d->sync_sample;
    t.decision = (uint8_t)d->r.decision; t.layer = (uint8_t)d->layer; t.has_period = (uint8_t)(d->f.has_period > 0.5);
    t.used_two_node = (uint8_t)d->used_two_node; t.p_trip = (float)d->r.p_trip;
    fx_features_vector(&d->f, t.x);
    t.cyc_extract = d->cyc_extract; t.cyc_infer = d->cyc_infer; t.cyc_close_to_trip = d->cyc_close_to_trip; t.cyc_onset_to_trip = d->cyc_onset_to_trip;
    size_t len = fx_upload_build(g_upload_buf, sizeof g_upload_buf, &h, g_up_i, g_up_v, &t);
    if (len) usb_upload_send(g_upload_buf, len);
}

void stream_poll_upload(void)
{
    if (g_upload_pending && g_count >= g_upload_k_on + (uint32_t)FX_N_REC_POST) {
        g_upload_pending = 0;
        build_and_send(g_upload_k_on, &g_last, 0);
    }
    if (g_capture_request) {
        g_capture_request = 0;
        decision_t d; memset(&d, 0, sizeof d);
        d.sync_sample = g_sync_sample;
        uint32_t k = g_count >= (uint32_t)FX_N_REC_POST ? g_count - (uint32_t)FX_N_REC_POST : (uint32_t)FX_N_REC_PRE;
        build_and_send(k, &d, 1);
    }
}

int stream_selftest(fx_features_t *f, uint32_t *cycles)
{
    int was_armed = g_det.armed;
    g_det.armed = 0;                                   /* no decision while the buffers are borrowed */
    while (g_pending) { }
    for (int k = 0; k < FX_N_REC; ++k) { rec_i[k] = 100.0 + (k >= 400 ? 50.0 : 0.0); rec_v[k] = 800.0 - (k >= 400 ? 8.0 : 0.0); }
    fx_stream_t s = { rec_i, rec_v, FX_N_REC, FX_FS_FAST, 350.0, 1000.0 };
    uint32_t t0 = dwt_now();
    int rc = fx_features_extract(&s, FX_W_025, 250.0, 800.0, &g_work, f);
    *cycles = dwt_now() - t0;
    g_det.armed = was_armed;
    return rc;
}

/* ---------------------------------------------------------------- parity (§6.4) */
static void pd(char *buf, size_t n, double v)
{
    if (isnan(v)) snprintf(buf, n, "nan");
    else snprintf(buf, n, "%.17g", v);
}

int stream_replay(const uint8_t *blob, uint32_t len, const double *W_s, int nW, void (*out)(const char *))
{
    fx_record_header_t h;
    if (fx_record_parse_header(blob, len, &h) != 0) return -1;
    if (h.n_fast > FX_N_REC_MAX || len < FX_REC_HEADER_BYTES + 4u * h.n_fast) return -2;
    const uint8_t *p = blob + FX_REC_HEADER_BYTES;
    for (uint32_t k = 0; k < h.n_fast; ++k) {
        uint16_t ci = (uint16_t)(p[2 * k] | (p[2 * k + 1] << 8));
        uint16_t cv = (uint16_t)(p[2 * h.n_fast + 2 * k] | (p[2 * h.n_fast + 2 * k + 1] << 8));
        rec_i[k] = code_to_phys(ci, h.offset_i, h.gain_i);
        rec_v[k] = code_to_phys(cv, h.offset_v, h.gain_v);
    }
    fx_stream_t s = { rec_i, rec_v, (int)h.n_fast, (double)h.fs_fast, h.fs_i, h.fs_v };
    const fx_model_t *m = fx_model_get(h.node ? "rack" : "feeder");
    fx_relay_cfg_t cfg; fx_relay_cfg_default(&cfg);
    static char line[1200];
    char num[32];
    for (int j = 0; j < nW; ++j) {
        fx_features_t f; fx_relay_result_t r; double x[FX_N_FEATURES];
        memset(&r, 0, sizeof r);
        uint32_t t0 = dwt_now();
        int rc = fx_features_extract(&s, W_s[j], h.I_rated, h.V_ref, &g_work, &f);
        uint32_t t1 = dwt_now();
        if (rc != 0) return -3;
        fx_features_vector(&f, x);
        if (m) fx_relay_layer2(&cfg, m, x, &r);
        uint32_t t2 = dwt_now();
        size_t L = 0;
        L += (size_t)snprintf(line + L, sizeof line - L, "%s,%s,%s,", h.event_id, h.node ? "rack" : "feeder", h.label);
        pd(num, sizeof num, W_s[j] * 1e3); L += (size_t)snprintf(line + L, sizeof line - L, "%s,%d,%d,", num, f.onset.k_on, f.onset.found);
        pd(num, sizeof num, f.onset.i_pre); L += (size_t)snprintf(line + L, sizeof line - L, "%s,", num);
        pd(num, sizeof num, f.onset.v_pre); L += (size_t)snprintf(line + L, sizeof line - L, "%s,", num);
        pd(num, sizeof num, f.onset.sig_i); L += (size_t)snprintf(line + L, sizeof line - L, "%s,", num);
        pd(num, sizeof num, f.onset.sig_v); L += (size_t)snprintf(line + L, sizeof line - L, "%s", num);
        for (int k = 0; k < FX_N_FEATURES; ++k) { pd(num, sizeof num, x[k]); L += (size_t)snprintf(line + L, sizeof line - L, ",%s", num); }
        for (int c = 0; c < FX_N_CLASSES; ++c) { pd(num, sizeof num, r.raw[c]); L += (size_t)snprintf(line + L, sizeof line - L, ",%s", num); }
        pd(num, sizeof num, r.p_trip);
        L += (size_t)snprintf(line + L, sizeof line - L, ",%s,%s,%lu,%lu\r\n", num, m ? fx_decision_name(r.decision) : "NONE",
                              (unsigned long)(t1 - t0), (unsigned long)(t2 - t1));
        out(line);
    }
    return 0;
}
