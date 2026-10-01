/* test_units.c — hardware-free unit tests of firmware/common (ctest target unit_common).
 * Reference vectors in fx_test_vectors.h are written by tools/export_filters.py. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "fx_config.h"
#include "fx_filters.h"
#include "fx_onset.h"
#include "fx_features.h"
#include "fx_model.h"
#include "fx_relay.h"
#include "fx_record.h"
#include "fx_cadence.h"
#include "fx_can.h"
#include "fx_upload.h"
#include "fx_test_vectors.h"

static int n_fail = 0;
#define CHECK(cond, ...) do { if (!(cond)) { n_fail++; printf("  FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

static double max_abs(const double *a, const double *b, int n)
{
    double m = 0.0;
    for (int k = 0; k < n; ++k) { double d = fabs(a[k] - b[k]); if (d > m) m = d; }
    return m;
}
static double max_abs_val(const double *a, int n)
{
    double m = 0.0;
    for (int k = 0; k < n; ++k) if (fabs(a[k]) > m) m = fabs(a[k]);
    return m;
}

static void test_constants(void)
{
    const double fs = FX_FS_FAST;
    int n_pre = (int)(0.15e-3 * fs); if (n_pre < 4) n_pre = 4;
    int n5 = (int)(5e-6 * fs); if (n5 < 1) n5 = 1;
    int n10 = (int)(10e-6 * fs); if (n10 < 1) n10 = 1;
    int n50 = (int)(50e-6 * fs); if (n50 < 1) n50 = 1;
    int n_skip = (int)(60e-6 * fs); if (n_skip > n_pre - 3) n_skip = n_pre - 3;
    CHECK(n_pre == FX_N_PRE, "n_pre %d", n_pre);
    CHECK(n5 == FX_N_SM5, "n5 %d", n5);
    CHECK(n10 == FX_N_SM10, "n10 %d", n10);
    CHECK(n50 == FX_N_50US, "n50 %d", n50);
    CHECK(n_skip == FX_N_SKIP, "n_skip %d", n_skip);
    CHECK((int)(FX_W_025 * fs) == FX_N_W_025, "nW 0.25");
    CHECK((int)(FX_W_050 * fs) == FX_N_W_050, "nW 0.5");
    CHECK((int)(FX_W_100 * fs) == FX_N_W_100, "nW 1.0");
    CHECK(fx_n_tail(125) == 12 && fx_n_tail(250) == 25 && fx_n_tail(500) == 50, "n_tail");
    CHECK(fx_k_half(125) == 37 && fx_k_half(250) == 75 && fx_k_half(500) == 150, "k_half");
    CHECK(sizeof(fx_node_t) == 12, "node size %lu", (unsigned long)sizeof(fx_node_t));
    printf("  constants ok\n");
}

static double xd[FX_TV_N];
static double y[FX_TV_N];
static fx_iir_t yf[FX_TV_N];

static void test_filters(void)
{
    for (int k = 0; k < FX_TV_N; ++k) xd[k] = (double)FX_TV_X[k];
    /* moving average n = 5 (bit-compatible with the numpy expression) */
    fx_movavg(xd, FX_TV_N, 5, y);
    double e = max_abs(y, FX_TV_MA5, FX_TV_N);
    printf("  movavg(5): max abs err %.3e\n", e);
    CHECK(e <= 1e-12, "movavg err %.3e", e);
    for (int k = 4; k < FX_TV_N; k += 997) {          /* brute-force window semantics */
        double s = 0.0;
        for (int j = k - 4; j <= k; ++j) s += xd[j];
        CHECK(fabs(y[k] - s / 5.0) <= 1e-12, "movavg window k=%d", k);
    }
    CHECK(y[0] == y[4] && y[3] == y[4], "movavg padding");
    /* mean / std */
    double m = fx_mean(xd, FX_TV_N), s = fx_std(xd, FX_TV_N);
    printf("  mean err %.3e  std err %.3e\n", fabs(m - FX_TV_MEAN), fabs(s - FX_TV_STD));
    CHECK(fabs(m - FX_TV_MEAN) <= 1e-12 * fabs(FX_TV_MEAN) + 1e-15, "mean");
    CHECK(fabs(s - FX_TV_STD) <= 1e-12 * FX_TV_STD, "std");
    /* band-pass, zero initial state, on the float32 test signal */
    int n_sec;
    const fx_sos_t *bp = fx_sos_bandpass(&n_sec);
    fx_sos_state_t st[FX_N_SOS_BP];
    fx_sos_zero(st, n_sec);
    for (int k = 0; k < FX_TV_N; ++k) yf[k] = fx_sos_step(bp, n_sec, st, (fx_iir_t)xd[k]);
    for (int k = 0; k < FX_TV_N; ++k) y[k] = (double)yf[k];
    double ref = max_abs_val(FX_TV_BP, FX_TV_N);
    e = max_abs(y, FX_TV_BP, FX_TV_N);
    printf("  band-pass (%s): max abs err %.3e, max |ref| %.3e, normalised %.3e\n",
           sizeof(fx_iir_t) == 4 ? "float32" : "float64", e, ref, e / ref);
    CHECK(e / ref <= 1e-4, "band-pass err %.3e", e / ref);
    /* the std ratio as the spectral features use it, C output vs reference */
    double pre_c = fx_std_iir(yf + FX_N_SKIP, FX_N_PRE - FX_N_SKIP), pre_r = fx_std(FX_TV_BP + FX_N_SKIP, FX_N_PRE - FX_N_SKIP);
    double post_c = fx_std_iir(yf + 600, 125), post_r = fx_std(FX_TV_BP + 600, 125);
    double sc = log10(post_c / pre_c), sr = log10(post_r / pre_r);
    printf("  log10 std ratio: C %.8f ref %.8f diff %.3e\n", sc, sr, fabs(sc - sr));
    CHECK(fabs(sc - sr) <= 1e-4, "spec-like ratio");
    /* anti-alias decimator 100:1 */
    fx_decim_t d;
    fx_decim_init(&d, FX_DECIM_SLOW);
    int n_out = 0;
    for (int k = 0; k < FX_TV_N; ++k) {
        fx_iir_t o;
        if (fx_decim_push(&d, (fx_iir_t)xd[k], &o)) { if (n_out < FX_TV_N_AA) y[n_out] = (double)o; n_out++; }
    }
    CHECK(n_out == FX_TV_N_AA, "decimator count %d vs %d", n_out, FX_TV_N_AA);
    ref = max_abs_val(FX_TV_AA, FX_TV_N_AA);
    e = max_abs(y, FX_TV_AA, FX_TV_N_AA);
    printf("  decimator: max abs err %.3e normalised %.3e\n", e, e / ref);
    CHECK(e / ref <= 1e-4, "decimator err %.3e", e / ref);
}

static void test_model(void)
{
    /* one iteration, three classes: tree0 splits f0 <= 0.5 (missing -> left), tree1 is a leaf,
     * tree2 splits f1 <= 0.25 (missing -> right) */
    static const fx_node_t nodes[] = {
        { 0.5, 1, 2, 0, FX_NODE_MISSING_LEFT }, { -1.0, 0, 0, 0, FX_NODE_LEAF }, { 2.0, 0, 0, 0, FX_NODE_LEAF },
        { 0.25, 0, 0, 0, FX_NODE_LEAF },
        { 0.25, 1, 2, 1, 0 }, { 10.0, 0, 0, 0, FX_NODE_LEAF }, { -3.0, 0, 0, 0, FX_NODE_LEAF },
    };
    static const uint32_t starts[] = { 0, 3, 4, 7 };
    fx_model_t m = { "test", nodes, starts, 7, 3, 3, 2, { 0.1, 0.2, 0.3 } };
    double raw[3], p[3];
    double x1[2] = { 0.2, 1.0 };
    fx_model_raw(&m, x1, raw);
    CHECK(raw[0] == 0.1 - 1.0 && raw[1] == 0.2 + 0.25 && raw[2] == 0.3 - 3.0, "walk 1: %g %g %g", raw[0], raw[1], raw[2]);
    double x2[2] = { 0.7, NAN };
    fx_model_raw(&m, x2, raw);
    CHECK(raw[0] == 0.1 + 2.0 && raw[2] == 0.3 - 3.0, "walk 2 (nan -> right): %g %g", raw[0], raw[2]);
    double x3[2] = { NAN, 0.1 };
    fx_model_raw(&m, x3, raw);
    CHECK(raw[0] == 0.1 - 1.0 && raw[2] == 0.3 + 10.0, "walk 3 (nan -> left): %g %g", raw[0], raw[2]);
    double x4[2] = { 0.5, 0.25 };
    fx_model_raw(&m, x4, raw);
    CHECK(raw[0] == 0.1 - 1.0 && raw[2] == 0.3 + 10.0, "walk 4 (x == threshold goes left)");
    fx_model_softmax(raw, 3, p);
    CHECK(fabs(p[0] + p[1] + p[2] - 1.0) < 1e-15 && fx_model_argmax(raw, 3) == 2, "softmax/argmax");
    fx_relay_cfg_t cfg;
    fx_relay_cfg_default(&cfg);
    fx_relay_result_t r;
    fx_relay_layer2(&cfg, &m, x4, &r);
    CHECK(r.decision == FX_DEC_TRIP && r.p_trip > 0.99, "relay trip");
    fx_relay_layer2(&cfg, &m, x1, &r);
    CHECK(r.decision == FX_DEC_HOLD, "relay hold");
    CHECK(!fx_relay_layer1(&cfg, 100.0, -100.0), "layer 1 off by default");
    cfg.l1_di = 1.0;
    CHECK(fx_relay_layer1(&cfg, 1.5, 1.0) && !fx_relay_layer1(&cfg, 0.5, 1.0), "layer 1 di");
    /* the exported tables are present and well-formed */
    CHECK(fx_model_count() >= 1, "no exported models");
    for (int i = 0; i < fx_model_count(); ++i) {
        const fx_model_t *em = fx_model_at(i);
        CHECK(em->n_classes == FX_N_CLASSES, "%s classes", em->name);
        CHECK(em->tree_start[em->n_trees] == em->n_nodes, "%s tree table", em->name);
        CHECK(em->n_trees % FX_N_CLASSES == 0, "%s trees", em->name);
    }
    printf("  model ok (%d exported models)\n", fx_model_count());
}

static void test_record(void)
{
    uint8_t b[FX_REC_HEADER_BYTES];
    memset(b, 0, sizeof b);
    memcpy(b, "FXR1", 4); b[4] = 1; b[6] = 128; b[8] = 0x28; b[9] = 0x0A;      /* n_fast 2600 */
    float g = 0.125f; memcpy(b + 24, &g, 4); b[32] = 0x00; b[33] = 0x80;         /* gain_i, offset 32768 */
    double I = 246.5; memcpy(b + 36, &I, 8); b[92] = 1;
    memcpy(b + 96, "00012", 5); memcpy(b + 108, "high_z_48", 9);
    fx_record_header_t h;
    CHECK(fx_record_parse_header(b, sizeof b, &h) == 0, "parse");
    CHECK(h.n_fast == 2600 && h.gain_i == 0.125f && h.offset_i == 32768 && h.I_rated == 246.5 && h.node == 1, "fields");
    CHECK(!strcmp(h.event_id, "00012") && !strcmp(h.label, "high_z_48"), "strings");
    CHECK(fx_record_data_bytes(&h) == 2600u * 2u * 2u, "data bytes");
    uint16_t codes[3] = { 32768, 32769, 32000 };
    double out[3];
    fx_record_codes_to_phys(codes, 3, 32768, 0.125f, out);
    CHECK(out[0] == 0.0 && out[1] == 0.125 && out[2] == -96.0, "codes -> phys");
    printf("  record ok\n");
}

static double fi[FX_N_REC], fv[FX_N_REC];
static fx_work_t work;

static void test_features_smoke(void)
{
    /* a synthetic step at sample 400 must give onset 400 and the obvious CONV values */
    for (int k = 0; k < FX_N_REC; ++k) { fi[k] = 100.0 + (k >= 400 ? 50.0 : 0.0); fv[k] = 800.0 - (k >= 400 ? 8.0 : 0.0); }
    fx_stream_t s = { fi, fv, FX_N_REC, FX_FS_FAST, 350.0, 1000.0 };
    fx_features_t f;
    int rc = fx_features_extract(&s, FX_W_025, 250.0, 800.0, &work, &f);
    CHECK(rc == 0, "extract rc %d", rc);
    CHECK(f.onset.k_on == 400 && f.onset.found, "onset %d", f.onset.k_on);
    CHECK(fabs(f.di_end - 0.2) < 1e-12 && fabs(f.di_max - 0.2) < 1e-12, "di_end %g di_max %g", f.di_end, f.di_max);
    CHECK(fabs(f.v_sag_end - 0.01) < 1e-12 && fabs(f.v_min - 0.99) < 1e-12 && f.collapse == 0.0, "voltage features");
    CHECK(f.t_rise > 0.0 && f.has_period == 0.0 && isnan(f.phase_err), "misc");
    double x[FX_N_FEATURES];
    fx_features_vector(&f, x);
    CHECK(x[0] == f.di_end && x[11] == f.spec_v && isnan(x[14]), "vector order");
    /* no onset: flat record */
    for (int k = 0; k < FX_N_REC; ++k) { fi[k] = 100.0; fv[k] = 800.0; }
    rc = fx_features_extract(&s, FX_W_025, 250.0, 800.0, &work, &f);
    CHECK(rc == 0 && !f.onset.found && f.onset.k_on == FX_N_PRE && fabs(f.t_rise - 0.25) < 1e-15, "flat record");
    printf("  features smoke ok\n");
}

static void test_cadence(void)
{
    static const double edges[] = { 1.0, 2.02, 2.98 };
    fx_cadence_tiers_t t;
    memset(&t, 0, sizeof t);
    t.n_tiers = 1; t.tier[0].T = 1.0; t.tier[0].edges = edges; t.tier[0].n_edges = 3;
    double pe = fx_cadence_phase_err(&t, 4.0);
    CHECK(pe < 0.02, "phase_err near an edge %g", pe);
    pe = fx_cadence_phase_err(&t, 4.5);
    CHECK(fabs(pe - 0.5) < 0.02, "phase_err half period %g", pe);
    t.tier[0].n_edges = 1;
    CHECK(isnan(fx_cadence_phase_err(&t, 4.0)), "one edge -> nan");
    printf("  cadence phase_err ok\n");
}

static void test_can_upload(void)
{
    /* CAN summary and feature frames round trip, combined-decision routing */
    fx_can_summary_t s = { 1, FX_DEC_TRIP, 1, 0, 0.93f, 0.12f, 123456u }, s2;
    uint8_t b[FX_CAN_SUMMARY_BYTES];
    fx_can_encode_summary(&s, b);
    CHECK(fx_can_decode_summary(b, &s2) == 0 && s2.node == 1 && s2.decision == FX_DEC_TRIP && s2.p_trip == 0.93f &&
          s2.phase_err == 0.12f && s2.onset_sample == 123456u, "summary round trip");
    fx_can_features_t f, acc;
    memset(&f, 0, sizeof f); memset(&acc, 0, sizeof acc);
    f.node = 1; f.onset_sample = 777u;
    for (int k = 0; k < FX_N_FEATURES; ++k) f.x[k] = 0.1 * k - 0.3;
    f.x[14] = NAN;
    uint8_t fr[FX_CAN_FEATURE_PARTS][FX_CAN_FEATURE_BYTES];
    fx_can_encode_features(&f, fr);
    int done = 0;
    for (int p = FX_CAN_FEATURE_PARTS - 1; p >= 0; --p) done = fx_can_decode_feature_part(fr[p], &acc);   /* any order */
    CHECK(done == 1 && acc.onset_sample == 777u && acc.x[3] == f.x[3] && acc.x[13] == f.x[13] && isnan(acc.x[14]), "feature frames round trip");
    const fx_model_t *mf = fx_model_get("feeder"), *mb = fx_model_get("both");
    if (mf && mb) {
        fx_relay_cfg_t cfg; fx_relay_cfg_default(&cfg);
        fx_relay_result_t r; int two;
        double own[FX_N_FEATURES] = { 0 };
        own[14] = NAN;
        fx_combined_decide(&cfg, mf, mb, own, &acc, 1000u, 500u, &r, &two);
        CHECK(two == 1, "two-node path when the rack set is complete and in time");
        fx_combined_decide(&cfg, mf, mb, own, &acc, 5000u, 500u, &r, &two);
        CHECK(two == 0, "own model when the rack onset is too far");
        fx_combined_decide(&cfg, mf, mb, own, NULL, 1000u, 500u, &r, &two);
        CHECK(two == 0, "own model without a rack set");
    }
    /* upload frame round trip */
    static uint16_t ci[FX_N_REC], cv[FX_N_REC];
    static uint8_t frame[FX_UPLOAD_HEAD_BYTES + FX_REC_HEADER_BYTES + 4 * FX_N_REC + FX_UPLOAD_TRAILER_BYTES + 4];
    for (int k = 0; k < FX_N_REC; ++k) { ci[k] = (uint16_t)(30000 + k); cv[k] = (uint16_t)(40000 - k); }
    fx_record_header_t h; memset(&h, 0, sizeof h);
    h.n_fast = FX_N_REC; h.fs_fast = 500000.0f; h.gain_i = 0.001f; h.gain_v = 0.002f; h.offset_i = 32768; h.offset_v = 32768;
    h.I_rated = 10.0; h.V_ref = 12.0; h.fs_i = 130.0; h.fs_v = 15.0; h.t0_fast = 1.25; h.t_event = 1.2502; h.node = 1; h.adc_bits = 16;
    memcpy(h.event_id, "n00001f40", 9); memcpy(h.label, "bench", 5);
    fx_upload_trailer_t t; memset(&t, 0, sizeof t);
    t.k_on = 8000u; t.sample_count = 10600u; t.decision = FX_DEC_TRIP; t.layer = 2; t.p_trip = 0.8f; t.cyc_infer = 4321u;
    for (int k = 0; k < FX_N_FEATURES; ++k) t.x[k] = k * 1.5;
    size_t len = fx_upload_build(frame, sizeof frame, &h, ci, cv, &t);
    CHECK(len == fx_upload_frame_bytes(FX_N_REC), "frame size %lu", (unsigned long)len);
    fx_record_header_t h2; const uint16_t *pi, *pv; fx_upload_trailer_t t2;
    CHECK(fx_upload_parse(frame, len, &h2, &pi, &pv, &t2) == 0, "frame parse");
    CHECK(h2.n_fast == FX_N_REC && h2.I_rated == 10.0 && h2.node == 1 && !strcmp(h2.event_id, "n00001f40") && h2.slow_format == 0, "frame header");
    CHECK(pi[5] == 30005 && pv[FX_N_REC - 1] == (uint16_t)(40000 - (FX_N_REC - 1)), "frame data");
    CHECK(t2.k_on == 8000u && t2.decision == FX_DEC_TRIP && t2.p_trip == 0.8f && t2.x[7] == 10.5 && t2.cyc_infer == 4321u, "frame trailer");
    frame[FX_UPLOAD_HEAD_BYTES + 200] ^= 0x55;
    CHECK(fx_upload_parse(frame, len, &h2, &pi, &pv, &t2) == -4, "crc detects corruption");
    printf("  can/upload framing ok\n");
}

int main(void)
{
    printf("unit_common\n");
    test_constants();
    test_filters();
    test_model();
    test_record();
    test_features_smoke();
    test_cadence();
    test_can_upload();
    printf("%s (%d failures)\n", n_fail ? "FAILED" : "PASSED", n_fail);
    return n_fail ? 1 : 0;
}
