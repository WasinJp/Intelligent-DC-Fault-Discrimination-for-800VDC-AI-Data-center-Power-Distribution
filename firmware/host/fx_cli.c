/* fx_cli.c — host front end for the fx common library (FIRMWARE_SPEC.md §2, §6).
 *
 *   fx_cli extract --dir <fixtures> [--out csv] [--W 0.25,0.5,1.0] [--theta 0.5]
 *   fx_cli extract <record.bin> ...            same, explicit files
 *   fx_cli score   --features <csv> [--out csv] class scores of every row (feeder/rack by the
 *                                              node column, plus the paired two-node model)
 *   fx_cli bench   --features <csv> [--model feeder|rack|both] [--repeat N]
 *   fx_cli stream  --dir <fixtures> [--out csv] [--W 0.25] [--freeze f] [--prefix N] [--seed s]
 *                                              stream-mode vs record-mode onset and decisions on
 *                                              replayed records (§4.2); --prefix adds a random quiet
 *                                              prefix of 0..N-1 samples before each record
 *   fx_cli info                                 model table sizes
 *
 * Host only: uses stdio, malloc and dirent; nothing here is compiled for the target.
 * Record arrays are read with fread and therefore assume a little-endian host. */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include <dirent.h>
#include "fx_config.h"
#include "fx_record.h"
#include "fx_features.h"
#include "fx_model.h"
#include "fx_relay.h"
#include "fx_cadence.h"
#include "fx_cadence32.h"
#if defined(__x86_64__) || defined(__i386__)
#include <x86intrin.h>
#define CYCLES() __rdtsc()
#else
#define CYCLES() 0ull
#endif

#define MAX_SLOW 65536
#define MAX_FILES 8192
#define MAX_W 8

typedef struct {
    fx_record_header_t h;
    uint16_t ci[FX_N_REC_MAX], cv[FX_N_REC_MAX];
    float si[MAX_SLOW], sv[MAX_SLOW];
    double fi[FX_N_REC_MAX], fv[FX_N_REC_MAX];
} rec_buf_t;

static rec_buf_t g_rec;
static fx_work_t g_work;
static fx_cadence_t g_cad;
/* float32 (target) learner and its buffers, bound as the node would bind them */
static fx_hist32_t g_hist32;
static fx_cadence32_t g_cad32;
static double g_c32_e1[FX_CAD32_EDGES], g_c32_e2[FX_CAD32_EDGES], g_c32_e2cur[FX_CAD32_EDGES];
static float g_c32_shadow[FX_CAD32_H], g_c32_ac[FX_CAD32_K], g_c32_acc[FX_CAD32_K];
static uint8_t g_c32_cnt[FX_CAD32_K], g_c32_state[FX_CAD32_STATE_BYTES];
static float g_c32_fa[FX_CAD32_FFT_N], g_c32_fb[FX_CAD32_FFT_N], g_c32_fc[FX_CAD32_FFT_N];
static int g_c32_peaks[FX_CAD32_NPEAKS]; static float g_c32_heights[FX_CAD32_NPEAKS];
static int g_c32_bounds[FX_CAD32_NBOUNDS];

static double now_ns(void)
{
    struct timespec ts;
    timespec_get(&ts, TIME_UTC);
    return (double)ts.tv_sec * 1e9 + (double)ts.tv_nsec;
}

static void pd(FILE *fp, double v)
{
    if (isnan(v)) fputs("nan", fp);
    else fprintf(fp, "%.17g", v);
}

static int load_record(const char *path, rec_buf_t *r)
{
    FILE *fp = fopen(path, "rb");
    if (!fp) { fprintf(stderr, "cannot open %s\n", path); return -1; }
    uint8_t hb[FX_REC_HEADER_BYTES];
    if (fread(hb, 1, sizeof hb, fp) != sizeof hb) { fprintf(stderr, "%s: short header\n", path); fclose(fp); return -1; }
    int rc = fx_record_parse_header(hb, sizeof hb, &r->h);
    if (rc != 0) { fprintf(stderr, "%s: bad header (%d)\n", path, rc); fclose(fp); return -1; }
    if (r->h.n_fast > FX_N_REC_MAX || r->h.n_slow > MAX_SLOW) { fprintf(stderr, "%s: record too long\n", path); fclose(fp); return -1; }
    size_t nf = r->h.n_fast;
    if (fread(r->ci, 2, nf, fp) != nf || fread(r->cv, 2, nf, fp) != nf) { fprintf(stderr, "%s: short fast data\n", path); fclose(fp); return -1; }
    if (r->h.slow_format == FX_REC_SLOW_F32 && r->h.n_slow) {
        size_t ns = r->h.n_slow;
        if (fread(r->si, 4, ns, fp) != ns || fread(r->sv, 4, ns, fp) != ns) { fprintf(stderr, "%s: short slow data\n", path); fclose(fp); return -1; }
    }
    fclose(fp);
    fx_record_codes_to_phys(r->ci, (int)nf, r->h.offset_i, r->h.gain_i, r->fi);
    fx_record_codes_to_phys(r->cv, (int)nf, r->h.offset_v, r->h.gain_v, r->fv);
    return 0;
}

static int cmp_str(const void *a, const void *b) { return strcmp(*(char *const *)a, *(char *const *)b); }

static int list_dir(const char *dir, char **files, int max)
{
    DIR *d = opendir(dir);
    if (!d) { fprintf(stderr, "cannot list %s\n", dir); return -1; }
    int n = 0;
    struct dirent *e;
    while ((e = readdir(d)) != NULL && n < max) {
        size_t L = strlen(e->d_name);
        if (L < 4 || strcmp(e->d_name + L - 4, ".bin") != 0) continue;
        size_t Lp = strlen(dir) + 1 + L + 1;
        char *p = malloc(Lp);
        snprintf(p, Lp, "%s/%s", dir, e->d_name);
        files[n++] = p;
    }
    closedir(d);
    qsort(files, (size_t)n, sizeof *files, cmp_str);
    return n;
}

static const char *node_name(int node) { return node == 1 ? "rack" : "feeder"; }

static void fail_usage(void)
{
    fputs("usage: fx_cli extract|score|bench|info ... (see the header of fx_cli.c)\n", stderr);
    exit(2);
}

/* ------------------------------------------------------------------ extract */
static int cmd_extract(int argc, char **argv)
{
    const char *dir = NULL, *out = NULL;
    double W[MAX_W] = { FX_W_025, FX_W_050, FX_W_100 };
    int nW = 3, cad32 = 0, dump_tiers = 0;
    fx_relay_cfg_t cfg; fx_relay_cfg_default(&cfg);
    char **files = malloc(sizeof(char *) * MAX_FILES);
    int nfiles = 0;
    for (int i = 0; i < argc; ++i) {
        if (!strcmp(argv[i], "--dir") && i + 1 < argc) dir = argv[++i];
        else if (!strcmp(argv[i], "--out") && i + 1 < argc) out = argv[++i];
        else if (!strcmp(argv[i], "--cadence") && i + 1 < argc) cad32 = !strcmp(argv[++i], "f32");   /* double (default) | f32 */
        else if (!strcmp(argv[i], "--dump-tiers")) dump_tiers = 1;
        else if (!strcmp(argv[i], "--theta") && i + 1 < argc) cfg.theta = atof(argv[++i]);
        else if (!strcmp(argv[i], "--W") && i + 1 < argc) {
            nW = 0;
            char *tok = strtok(argv[++i], ",");
            while (tok && nW < MAX_W) { W[nW++] = atof(tok) * 1e-3; tok = strtok(NULL, ","); }
        } else if (argv[i][0] == '-') fail_usage();
        else if (nfiles < MAX_FILES) files[nfiles++] = argv[i];
    }
    if (dir) nfiles = list_dir(dir, files, MAX_FILES);
    if (nfiles <= 0) { fputs("no records\n", stderr); return 1; }
    FILE *fp = out ? fopen(out, "w") : stdout;
    if (!fp) { fprintf(stderr, "cannot write %s\n", out); return 1; }
    fputs("event,node,label,W_ms,k_on,onset_found,i_pre,v_pre,sig_i,sig_v", fp);
    for (int j = 0; j < FX_N_FEATURES; ++j) fprintf(fp, ",%s", fx_feature_names[j]);
    fputs(",raw_ALERT,raw_HOLD,raw_TRIP,p_TRIP,decision\n", fp);
    double t_sum = 0.0, t_max = 0.0, c_sum = 0.0, c_max = 0.0;
    unsigned long long cyc_sum = 0, cyc_max = 0, fft_sum = 0;
    int n_rows = 0, n_err = 0, n_learn = 0;
    if (cad32) {
        fx_fft32_init();
        fx_cadence32_bind(&g_cad32, g_c32_e1, g_c32_e2, g_c32_e2cur, g_c32_shadow, g_c32_ac, g_c32_acc, g_c32_cnt,
                          g_c32_state, g_c32_fa, g_c32_fb, g_c32_fc, g_c32_peaks, g_c32_heights, g_c32_bounds);
    }
    for (int i = 0; i < nfiles; ++i) {
        if (load_record(files[i], &g_rec) != 0) { n_err++; continue; }
        const fx_record_header_t *h = &g_rec.h;
        fx_stream_t s = { g_rec.fi, g_rec.fv, (int)h->n_fast, (double)h->fs_fast, h->fs_i, h->fs_v };
        const fx_model_t *m = fx_model_get(node_name(h->node));
        int has_slow = (h->slow_format == FX_REC_SLOW_F32 && h->n_slow > 0);
        for (int j = 0; j < nW; ++j) {
            fx_features_t f;
            double x[FX_N_FEATURES];
            fx_relay_result_t r;
            memset(&r, 0, sizeof r);
            double t0 = now_ns();
            int rc = fx_features_extract(&s, W[j], h->I_rated, h->V_ref, &g_work, &f);
            if (rc == 0 && has_slow) {
                /* M5: WORK features from the slow-stream history before the onset (features.extract) */
                double t_on = h->t0_fast + (double)f.onset.k_on / (double)h->fs_fast;
                double tc = now_ns();
                unsigned long long cy0 = CYCLES();
                if (cad32) {
                    fx_hist32_init(&g_hist32, (double)h->fs_slow, h->t0_slow);
                    for (uint32_t k = 0; k < h->n_slow; ++k) fx_hist32_push(&g_hist32, g_rec.si[k]);
                    cy0 = CYCLES();
                    fx_cadence32_learn(&g_cad32, &g_hist32, W[j], t_on - 0.5e-3);
                    fx_cadence_work_features(&g_cad32.tiers, t_on, &f.has_period, &f.period_strength, &f.phase_err);
                    fft_sum += g_cad32.n_fft;
                } else {
                    fx_cadence_learn(&g_cad, g_rec.si, (int)h->n_slow, h->t0_slow, (double)h->fs_slow, W[j], t_on - 0.5e-3);
                    fx_cadence_work_features(&g_cad.tiers, t_on, &f.has_period, &f.period_strength, &f.phase_err);
                }
                unsigned long long cy = CYCLES() - cy0;
                cyc_sum += cy; if (cy > cyc_max) cyc_max = cy;
                if (dump_tiers) {
                    const fx_cadence_tiers_t *tt = cad32 ? &g_cad32.tiers : &g_cad.tiers;
                    fprintf(stderr, "TIERS %s %s W=%g n_tiers=%d", h->event_id, node_name(h->node), W[j] * 1e3, tt->n_tiers);
                    for (int q = 0; q < tt->n_tiers; ++q)
                        fprintf(stderr, " | T=%.17g s=%.9g n_edges=%d tier2=%d phase_start=%.17g n_cur=%d off2=%.17g",
                                tt->tier[q].T, tt->tier[q].strength, tt->tier[q].n_edges, tt->tier[q].is_tier2,
                                tt->tier[q].phase_start, tt->tier[q].n_current, tt->tier[q].off2);
                    fprintf(stderr, " | phase_err=%.17g\n", f.phase_err);
                }
                double dc = now_ns() - tc;
                c_sum += dc; if (dc > c_max) c_max = dc; n_learn++;
            }
            if (rc == 0 && m) { fx_features_vector(&f, x); fx_relay_layer2(&cfg, m, x, &r); }
            double dt = now_ns() - t0;
            if (rc != 0) { fprintf(stderr, "%s: extract failed (%d)\n", files[i], rc); n_err++; continue; }
            t_sum += dt; if (dt > t_max) t_max = dt; n_rows++;
            fprintf(fp, "%s,%s,%s,", h->event_id, node_name(h->node), h->label);
            pd(fp, W[j] * 1e3);
            fprintf(fp, ",%d,%d,", f.onset.k_on, f.onset.found);
            pd(fp, f.onset.i_pre); fputc(',', fp); pd(fp, f.onset.v_pre); fputc(',', fp);
            pd(fp, f.onset.sig_i); fputc(',', fp); pd(fp, f.onset.sig_v);
            fx_features_vector(&f, x);
            for (int k = 0; k < FX_N_FEATURES; ++k) { fputc(',', fp); pd(fp, x[k]); }
            if (m) {
                for (int c = 0; c < FX_N_CLASSES; ++c) { fputc(',', fp); pd(fp, r.raw[c]); }
                fputc(',', fp); pd(fp, r.p_trip);
                fprintf(fp, ",%s\n", fx_decision_name(r.decision));
            } else {
                fputs(",nan,nan,nan,nan,NONE\n", fp);
            }
        }
    }
    if (fp != stdout) fclose(fp);
    fprintf(stderr, "extract: %d records, %d rows, %d errors; extract+inference per row: mean %.1f us, max %.1f us\n",
            nfiles, n_rows, n_err, n_rows ? t_sum / n_rows * 1e-3 : 0.0, t_max * 1e-3);
    if (n_learn)
        fprintf(stderr, "cadence relearn (host, %s, included above): %d runs, mean %.2f ms, max %.2f ms; "
                "x86 cycles mean %.1f M, max %.1f M%s; FFTs per relearn %.1f (N = %d, %s)\n",
                cad32 ? "float32 target learner" : "double", n_learn, c_sum / n_learn * 1e-6, c_max * 1e-6,
                (double)cyc_sum / n_learn * 1e-6, (double)cyc_max * 1e-6, CYCLES() ? "" : " (no cycle counter)",
                cad32 ? (double)fft_sum / n_learn : 0.0, cad32 ? FX_CAD32_FFT_N : 0, cad32 ? fx_fft32_backend() : "-");
    return n_err ? 1 : 0;
}

/* ------------------------------------------------------------------ stream vs record (§4.2) */
static double g_sub_i[FX_N_REC_MAX], g_sub_v[FX_N_REC_MAX];

static int cmd_stream(int argc, char **argv)
{
    const char *dir = NULL, *out = NULL;
    double W = FX_W_025, freeze = FX_STREAM_FREEZE_DEFAULT;
    int prefix_max = 0;          /* --prefix N: a random quiet prefix of 0..N-1 samples (tiled pre-anchor noise) */
    unsigned seed = 1;
    fx_relay_cfg_t cfg; fx_relay_cfg_default(&cfg);
    for (int i = 0; i < argc; ++i) {
        if (!strcmp(argv[i], "--dir") && i + 1 < argc) dir = argv[++i];
        else if (!strcmp(argv[i], "--out") && i + 1 < argc) out = argv[++i];
        else if (!strcmp(argv[i], "--W") && i + 1 < argc) W = atof(argv[++i]) * 1e-3;
        else if (!strcmp(argv[i], "--freeze") && i + 1 < argc) freeze = atof(argv[++i]);   /* 0 = pure sliding (§4.2 text) */
        else if (!strcmp(argv[i], "--prefix") && i + 1 < argc) prefix_max = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--seed") && i + 1 < argc) seed = (unsigned)atoi(argv[++i]);
        else fail_usage();
    }
    srand(seed);
    if (!dir) fail_usage();
    char **files = malloc(sizeof(char *) * MAX_FILES);
    int nfiles = list_dir(dir, files, MAX_FILES);
    if (nfiles <= 0) { fputs("no records\n", stderr); return 1; }
    FILE *fp = out ? fopen(out, "w") : stdout;
    if (!fp) { fprintf(stderr, "cannot write %s\n", out); return 1; }
    fputs("event,node,k_on_record,found_record,k_on_stream,found_stream,delta,decision_record,decision_stream,p_trip_record,p_trip_stream\n", fp);
    int n = 0, n_both = 0, n_within2 = 0, n_same_dec = 0, n_rec_only = 0, n_str_only = 0, n_neither = 0;
    double det_sum = 0.0, det_max = 0.0;
    for (int i = 0; i < nfiles; ++i) {
        if (load_record(files[i], &g_rec) != 0) continue;
        const fx_record_header_t *h = &g_rec.h;
        const fx_model_t *m = fx_model_get(node_name(h->node));
        int nf = (int)h->n_fast;
        /* record mode on the whole record */
        fx_stream_t s = { g_rec.fi, g_rec.fv, nf, (double)h->fs_fast, h->fs_i, h->fs_v };
        fx_features_t fr; double x[FX_N_FEATURES]; fx_relay_result_t rr, rs;
        memset(&rr, 0, sizeof rr); memset(&rs, 0, sizeof rs);
        if (fx_features_extract(&s, W, h->I_rated, h->V_ref, &g_work, &fr) != 0) continue;
        fx_features_vector(&fr, x); fx_relay_layer2(&cfg, m, x, &rr);
        /* stream mode: push the record sample by sample. With --prefix, the detector first sees a random
         * length of quiet signal made by tiling the record's pre-anchor samples, so that the baseline
         * refresh phase (FX_STREAM_FREEZE_MAX) is not aligned with the event as it would be on the node. */
        fx_onset_stream_t st; fx_onset_stream_init(&st, h->fs_i, h->fs_v);
        st.freeze_factor = freeze;
        int npre = prefix_max > 0 ? rand() % prefix_max : 0;
        for (int k = 0; k < npre; ++k) {
            int src = k % FX_N_REC_PRE;            /* samples 0..99 are before the anchor */
            fx_onset_stream_push(&st, g_rec.fi[src], g_rec.fv[src]);
        }
        if (prefix_max > 0 && st.last.found) { st.holdoff = 0; st.armed = 1; st.last.found = 0; }   /* prefix must stay quiet */
        int k_s = -1;
        double t0 = now_ns();
        for (int k = 0; k < nf; ++k) if (fx_onset_stream_push(&st, g_rec.fi[k], g_rec.fv[k])) { k_s = k; break; }
        double dt = (now_ns() - t0) / (double)(k_s < 0 ? nf : k_s + 1);   /* ns per sample */
        det_sum += dt; if (dt > det_max) det_max = dt;
        int found_s = k_s >= 0;
        if (found_s && st.rec_start < 0) st.rec_start = 0;
        if (found_s && st.rec_start > 0 && (long)k_s - st.rec_start < 0) st.rec_start = 0;
        /* rec_start is an index in the stream = prefix + record; map it into the record */
        if (found_s) { st.rec_start -= npre; if (st.rec_start < 0) st.rec_start = 0; }
        /* features on the stream record [rec_start, k_on + N_W) in record mode, as the node does;
         * the onset the node uses is the record-mode one re-detected on that record */
        fx_features_t fs; memset(&fs, 0, sizeof fs);
        int k_node = -1;
        if (found_s) {
            int a = (int)st.rec_start;
            int ns = k_s + (int)(W * h->fs_fast) - a;          /* samples available at the window close */
            if (ns > nf - a) ns = nf - a;
            if (ns > FX_N_REC_MAX) ns = FX_N_REC_MAX;
            memcpy(g_sub_i, g_rec.fi + a, sizeof(double) * (size_t)ns);
            memcpy(g_sub_v, g_rec.fv + a, sizeof(double) * (size_t)ns);
            fx_stream_t s2 = { g_sub_i, g_sub_v, ns, (double)h->fs_fast, h->fs_i, h->fs_v };
            if (fx_features_extract(&s2, W, h->I_rated, h->V_ref, &g_work, &fs) == 0) {
                fx_features_vector(&fs, x); fx_relay_layer2(&cfg, m, x, &rs);
                k_node = a + fs.onset.k_on;
            }
        }
        int delta = (found_s && fr.onset.found) ? k_node - fr.onset.k_on : 0;
        fx_decision_t dec_s = found_s ? rs.decision : FX_DEC_HOLD;   /* nothing detected -> HOLD */
        fx_decision_t dec_r = fr.onset.found ? rr.decision : FX_DEC_HOLD;
        n++;
        if (found_s && fr.onset.found) { n_both++; if (abs(delta) <= 2) n_within2++; }
        else if (fr.onset.found) n_rec_only++;
        else if (found_s) n_str_only++;
        else n_neither++;
        if (dec_s == dec_r) n_same_dec++;
        fprintf(fp, "%s,%s,%d,%d,%d,%d,%d,%s,%s,", h->event_id, node_name(h->node), fr.onset.k_on, fr.onset.found,
                found_s ? k_node : -1, found_s, delta, fx_decision_name(dec_r), fx_decision_name(dec_s));
        pd(fp, fr.onset.found ? rr.p_trip : NAN); fputc(',', fp); pd(fp, found_s ? rs.p_trip : NAN); fputc('\n', fp);
    }
    if (fp != stdout) fclose(fp);
    double f_within = n_both ? 100.0 * n_within2 / n_both : 0.0, f_dec = n ? 100.0 * n_same_dec / n : 0.0;
    printf("stream vs record (W = %.2f ms, freeze %.2f, prefix %d): %d records; both detected %d (onset within +-2 samples: %d = %.2f %%); "
           "record only %d, stream only %d, neither %d; identical decisions %d/%d = %.2f %%; "
           "detector cost on host %.1f ns/sample mean, %.1f max\n",
           W * 1e3, freeze, prefix_max, n, n_both, n_within2, f_within, n_rec_only, n_str_only, n_neither, n_same_dec, n, f_dec,
           n ? det_sum / n : 0.0, det_max);
    return (f_within >= 99.0 && f_dec >= 99.5) ? 0 : 1;
}

/* ------------------------------------------------------------------ CSV */
typedef struct {
    char *buf;
    char **hdr; int ncol;
    char ***rows; int nrow;
} csv_t;

static int csv_load(const char *path, csv_t *c)
{
    FILE *fp = fopen(path, "rb");
    if (!fp) { fprintf(stderr, "cannot open %s\n", path); return -1; }
    fseek(fp, 0, SEEK_END); long L = ftell(fp); fseek(fp, 0, SEEK_SET);
    c->buf = malloc((size_t)L + 1);
    if (fread(c->buf, 1, (size_t)L, fp) != (size_t)L) { fclose(fp); return -1; }
    fclose(fp);
    c->buf[L] = 0;
    int nl = 0;
    for (long i = 0; i < L; ++i) if (c->buf[i] == '\n') nl++;
    c->rows = malloc(sizeof(char **) * (size_t)(nl + 2));
    c->nrow = 0; c->hdr = NULL; c->ncol = 0;
    char *p = c->buf;
    while (*p) {
        char *line = p;
        char *nlp = strchr(p, '\n');
        if (nlp) { *nlp = 0; p = nlp + 1; } else p += strlen(p);
        size_t Ll = strlen(line);
        if (Ll && line[Ll - 1] == '\r') line[Ll - 1] = 0;
        if (!*line) continue;
        int nf = 1;
        for (char *q = line; *q; ++q) if (*q == ',') nf++;
        char **f = malloc(sizeof(char *) * (size_t)nf);
        int k = 0; f[k++] = line;
        for (char *q = line; *q; ++q) if (*q == ',') { *q = 0; f[k++] = q + 1; }
        if (!c->hdr) { c->hdr = f; c->ncol = nf; }
        else if (nf == c->ncol) c->rows[c->nrow++] = f;
        else { fprintf(stderr, "%s: row %d has %d fields, header %d\n", path, c->nrow + 1, nf, c->ncol); return -1; }
    }
    return c->hdr ? 0 : -1;
}

static int csv_col(const csv_t *c, const char *name)
{
    for (int i = 0; i < c->ncol; ++i) if (!strcmp(c->hdr[i], name)) return i;
    return -1;
}

static double parse_d(const char *s)
{
    if (!*s || s[0] == 'n' || s[0] == 'N') return NAN;
    return strtod(s, NULL);
}

typedef struct {
    int c_event, c_node, c_W, c_feat[FX_N_FEATURES];
} cols_t;

static int cols_find(const csv_t *c, cols_t *k)
{
    k->c_event = csv_col(c, "event"); k->c_node = csv_col(c, "node"); k->c_W = csv_col(c, "W_ms");
    if (k->c_event < 0 || k->c_node < 0 || k->c_W < 0) { fputs("features csv needs event,node,W_ms\n", stderr); return -1; }
    for (int j = 0; j < FX_N_FEATURES; ++j) {
        k->c_feat[j] = csv_col(c, fx_feature_names[j]);
        if (k->c_feat[j] < 0) { fprintf(stderr, "features csv lacks column %s\n", fx_feature_names[j]); return -1; }
    }
    return 0;
}

static void row_x(const csv_t *c, const cols_t *k, int r, double *x)
{
    for (int j = 0; j < FX_N_FEATURES; ++j) x[j] = parse_d(c->rows[r][k->c_feat[j]]);
}

/* index of the rack row pairing feeder row r (same event and W_ms), or -1 */
static int find_pair(const csv_t *c, const cols_t *k, int r)
{
    const char *ev = c->rows[r][k->c_event], *W = c->rows[r][k->c_W];
    for (int q = r + 1; q < c->nrow; ++q)          /* rows are event-major: the rack row is near */
        if (!strcmp(c->rows[q][k->c_node], "rack") && !strcmp(c->rows[q][k->c_event], ev) && !strcmp(c->rows[q][k->c_W], W)) return q;
    for (int q = 0; q < r; ++q)
        if (!strcmp(c->rows[q][k->c_node], "rack") && !strcmp(c->rows[q][k->c_event], ev) && !strcmp(c->rows[q][k->c_W], W)) return q;
    return -1;
}

static void print_scores(FILE *fp, const csv_t *c, const cols_t *k, int r, const char *node, const fx_model_t *m, const double *x)
{
    double raw[FX_N_CLASSES], p[FX_N_CLASSES];
    fx_model_raw(m, x, raw);
    fx_model_softmax(raw, m->n_classes, p);
    fprintf(fp, "%s,%s,%s,%s", c->rows[r][k->c_event], node, c->rows[r][k->c_W], m->name);
    for (int i = 0; i < FX_N_CLASSES; ++i) { fputc(',', fp); pd(fp, raw[i]); }
    for (int i = 0; i < FX_N_CLASSES; ++i) { fputc(',', fp); pd(fp, p[i]); }
    fprintf(fp, ",%s\n", fx_class_names[fx_model_argmax(raw, m->n_classes)]);
}

static int cmd_score(int argc, char **argv)
{
    const char *feat = NULL, *out = NULL;
    for (int i = 0; i < argc; ++i) {
        if (!strcmp(argv[i], "--features") && i + 1 < argc) feat = argv[++i];
        else if (!strcmp(argv[i], "--out") && i + 1 < argc) out = argv[++i];
        else fail_usage();
    }
    if (!feat) fail_usage();
    csv_t c; cols_t k;
    if (csv_load(feat, &c) != 0 || cols_find(&c, &k) != 0) return 1;
    const fx_model_t *mf = fx_model_get("feeder"), *mr = fx_model_get("rack"), *mb = fx_model_get("both");
    FILE *fp = out ? fopen(out, "w") : stdout;
    if (!fp) { fprintf(stderr, "cannot write %s\n", out); return 1; }
    fputs("event,node,W_ms,model,raw_ALERT,raw_HOLD,raw_TRIP,p_ALERT,p_HOLD,p_TRIP,argmax\n", fp);
    double x[FX_N_FEATURES_TWO];
    int n_out = 0;
    for (int r = 0; r < c.nrow; ++r) {
        const char *node = c.rows[r][k.c_node];
        const fx_model_t *m = !strcmp(node, "rack") ? mr : (!strcmp(node, "feeder") ? mf : NULL);
        if (!m) continue;
        row_x(&c, &k, r, x);
        print_scores(fp, &c, &k, r, node, m, x); n_out++;
    }
    if (mb) {
        for (int r = 0; r < c.nrow; ++r) {
            if (strcmp(c.rows[r][k.c_node], "feeder")) continue;
            int q = find_pair(&c, &k, r);
            if (q < 0) continue;
            row_x(&c, &k, r, x);
            row_x(&c, &k, q, x + FX_N_FEATURES);
            print_scores(fp, &c, &k, r, "both", mb, x); n_out++;
        }
    }
    if (fp != stdout) fclose(fp);
    fprintf(stderr, "score: %d input rows, %d score rows\n", c.nrow, n_out);
    return 0;
}

/* ------------------------------------------------------------------ bench */
static int cmp_d(const void *a, const void *b)
{
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

static int cmd_bench(int argc, char **argv)
{
    const char *feat = NULL, *mname = NULL;
    int repeat = 20;
    for (int i = 0; i < argc; ++i) {
        if (!strcmp(argv[i], "--features") && i + 1 < argc) feat = argv[++i];
        else if (!strcmp(argv[i], "--model") && i + 1 < argc) mname = argv[++i];
        else if (!strcmp(argv[i], "--repeat") && i + 1 < argc) repeat = atoi(argv[++i]);
        else fail_usage();
    }
    if (!feat) fail_usage();
    csv_t c; cols_t k;
    if (csv_load(feat, &c) != 0 || cols_find(&c, &k) != 0) return 1;
    int rc = 0;
    for (int mi = 0; mi < fx_model_count(); ++mi) {
        const fx_model_t *m = fx_model_at(mi);
        if (mname && strcmp(m->name, mname)) continue;
        int nf = m->n_features;
        double *X = malloc(sizeof(double) * (size_t)c.nrow * (size_t)nf);
        int nrow = 0;
        for (int r = 0; r < c.nrow; ++r) {
            const char *node = c.rows[r][k.c_node];
            if (nf == FX_N_FEATURES) {
                if (strcmp(node, m->name)) continue;
                row_x(&c, &k, r, X + (size_t)nrow * (size_t)nf); nrow++;
            } else {
                if (strcmp(node, "feeder")) continue;
                int q = find_pair(&c, &k, r);
                if (q < 0) continue;
                row_x(&c, &k, r, X + (size_t)nrow * (size_t)nf);
                row_x(&c, &k, q, X + (size_t)nrow * (size_t)nf + FX_N_FEATURES); nrow++;
            }
        }
        if (nrow == 0) { fprintf(stderr, "bench: no rows for model %s\n", m->name); rc = 1; free(X); continue; }
        double *t = malloc(sizeof(double) * (size_t)nrow * (size_t)repeat);
        double raw[FX_N_CLASSES], p[FX_N_CLASSES], sink = 0.0;
        size_t n = 0;
        for (int rep = 0; rep < repeat; ++rep)
            for (int r = 0; r < nrow; ++r) {
                double t0 = now_ns();
                fx_model_raw(m, X + (size_t)r * (size_t)nf, raw);
                fx_model_softmax(raw, m->n_classes, p);
                t[n++] = now_ns() - t0;
                sink += p[FX_CLASS_TRIP];
            }
        qsort(t, n, sizeof(double), cmp_d);
        double mean = 0.0;
        for (size_t i = 0; i < n; ++i) mean += t[i];
        mean /= (double)n;
        printf("model %-6s trees %4u nodes %6u bytes %7lu features %2d | host inference (raw+softmax) over %d rows x %d: "
               "mean %.2f us  p50 %.2f us  p99 %.2f us  max %.2f us  (sink %.3f)\n",
               m->name, (unsigned)m->n_trees, (unsigned)m->n_nodes, (unsigned long)fx_model_bytes(m), nf, nrow, repeat,
               mean * 1e-3, t[n / 2] * 1e-3, t[(size_t)((double)n * 0.99)] * 1e-3, t[n - 1] * 1e-3, sink);
        free(t); free(X);
    }
    return rc;
}

static int cmd_info(void)
{
    for (int i = 0; i < fx_model_count(); ++i) {
        const fx_model_t *m = fx_model_at(i);
        printf("model %-6s trees %4u nodes %6u bytes %7lu features %2d classes %d baseline %.6f %.6f %.6f\n",
               m->name, (unsigned)m->n_trees, (unsigned)m->n_nodes, (unsigned long)fx_model_bytes(m),
               m->n_features, m->n_classes, m->baseline[0], m->baseline[1], m->baseline[2]);
    }
    printf("node size %lu bytes; FX_N_REC %d; N_PRE %d; IIR type %s\n", (unsigned long)sizeof(fx_node_t),
           FX_N_REC, FX_N_PRE, sizeof(fx_iir_t) == 4 ? "float32" : "float64");
    return 0;
}

int main(int argc, char **argv)
{
    if (argc < 2) fail_usage();
    if (!strcmp(argv[1], "extract")) return cmd_extract(argc - 2, argv + 2);
    if (!strcmp(argv[1], "score")) return cmd_score(argc - 2, argv + 2);
    if (!strcmp(argv[1], "stream")) return cmd_stream(argc - 2, argv + 2);
    if (!strcmp(argv[1], "bench")) return cmd_bench(argc - 2, argv + 2);
    if (!strcmp(argv[1], "info")) return cmd_info();
    fail_usage();
    return 2;
}
