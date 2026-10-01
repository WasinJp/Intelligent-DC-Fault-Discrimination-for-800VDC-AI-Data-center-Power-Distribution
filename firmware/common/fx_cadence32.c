/* fx_cadence32.c — see fx_cadence32.h. Structure follows fx_cadence.c one to one; every place that
 * held a double array over the history is replaced by an on-the-fly series. */
#include "fx_cadence32.h"
#include <math.h>
#include <string.h>
#include <stdlib.h>

#define FX_PI 3.14159265358979323846
#define B FX_CAD32_BLOCK
#define NFFT FX_CAD32_FFT_N

/* ---------------------------------------------------------------- history */
void fx_hist32_init(fx_hist32_t *h, double fs, double t0)
{
    h->count = 0; h->fs = fs; h->t0 = t0;
}

void fx_hist32_push(fx_hist32_t *h, float x)
{
    h->x[h->count % FX_CAD32_H] = x;
    h->count++;
}

void fx_cadence32_bind(fx_cadence32_t *c, double *e1, double *e2, double *e2cur, float *shadow, float *ac, float *acc,
                       uint8_t *cnt, uint8_t *state1, float *fa, float *fb, float *fc, int *peaks, float *heights, int *bounds)
{
    memset(c, 0, sizeof *c);
    c->e1 = e1; c->e2 = e2; c->e2cur = e2cur; c->shadow = shadow; c->ac = ac; c->acc = acc; c->cnt = cnt;
    c->state1 = state1; c->fa = fa; c->fb = fb; c->fc = fc; c->peaks = peaks; c->heights = heights; c->bounds = bounds;
}

/* ---------------------------------------------------------------- series: x[k] = raw[first + k] - sub */
typedef struct {
    const fx_hist32_t *h;
    uint32_t first;          /* absolute sample index of element 0 */
    int n;
    double sub;              /* subtracted offset (tier-2 segments: 10th percentile) */
    int n_sm;                /* moving-average length applied on top (1 = none) */
} series_t;

static inline double raw_at(const series_t *s, int k)
{
    return (double)s->h->x[(s->first + (uint32_t)k) % FX_CAD32_H] - s->sub;
}

/* Python _movavg(x, n)[k]: mean of x[k-n+1 .. k] for k >= n-1, else the value at n-1 */
static double ma_at(const series_t *s, int k)
{
    int n = s->n_sm;
    if (n <= 1) return raw_at(s, k);
    int kk = k < n - 1 ? n - 1 : k;
    if (kk > s->n - 1) kk = s->n - 1;
    double sum = 0.0;
    for (int j = kk - n + 1; j <= kk; ++j) sum += raw_at(s, j < 0 ? 0 : j);
    return sum / (double)n;
}

/* sequential iterator over ma_at with a sliding sum (same arithmetic order as a running sum) */
typedef struct { const series_t *s; int k; double sum; double value; } ma_iter_t;
static void ma_begin(ma_iter_t *it, const series_t *s)
{
    it->s = s; it->k = 0;
    int n = s->n_sm;
    if (n <= 1) { it->sum = 0.0; it->value = raw_at(s, 0); return; }
    it->sum = 0.0;
    for (int j = 0; j < n && j < s->n; ++j) it->sum += raw_at(s, j);
    it->value = it->sum / (double)n;              /* value for k < n-1 */
}
static void ma_next(ma_iter_t *it)
{
    const series_t *s = it->s;
    int n = s->n_sm;
    it->k++;
    if (n <= 1) { it->value = raw_at(s, it->k); return; }
    if (it->k >= n) {
        it->sum += raw_at(s, it->k) - raw_at(s, it->k - n);
        it->value = it->sum / (double)n;
    }
    /* k <= n-1: value stays the first window mean */
}

/* ---------------------------------------------------------------- exact order statistics */
typedef double (*getter_t)(const void *ctx, int k);

static int cmp_f(const void *a, const void *b)
{
    float x = *(const float *)a, y = *(const float *)b;
    return (x > y) - (x < y);
}

/* k-th smallest (0-based) of the n doubles produced by get(). shadow[] receives the float32
 * roundings and is sorted (callers may reuse it for further ranks of the same series by passing
 * sorted = 1). Exact: the float32 rounding is monotone, so the k-th double rounds to shadow[k];
 * the candidates with that rounding are collected and ranked in double. */
static double select_k(getter_t get, const void *ctx, int n, int k, float *shadow, int sorted)
{
    if (!sorted) {
        for (int j = 0; j < n; ++j) shadow[j] = (float)get(ctx, j);
        qsort(shadow, (size_t)n, sizeof(float), cmp_f);
    }
    float f = shadow[k];
    int lo = 0, hi = n;                       /* first index with shadow >= f */
    while (lo < hi) { int m = (lo + hi) / 2; if (shadow[m] < f) lo = m + 1; else hi = m; }
    int c_lt = lo;
    int r = k - c_lt;                         /* rank inside the tie group */
    /* distinct double values of the tie group with their multiplicities: quantised series have
     * thousands of equal samples but only a few distinct values per float32 bucket */
    double dv[64]; int dc[64];
    int nd = 0, overflow = 0;
    for (int j = 0; j < n; ++j) {
        double v = get(ctx, j);
        if ((float)v != f) continue;
        int i = 0;
        while (i < nd && dv[i] != v) i++;
        if (i < nd) dc[i]++;
        else if (nd < 64) { dv[nd] = v; dc[nd] = 1; nd++; }
        else overflow = 1;
    }
    if (overflow || nd == 0) return (double)f;   /* > 64 distinct values within one float32 ulp */
    for (int i = 1; i < nd; ++i) {
        double v = dv[i]; int cnt = dc[i]; int j = i - 1;
        while (j >= 0 && dv[j] > v) { dv[j + 1] = dv[j]; dc[j + 1] = dc[j]; j--; }
        dv[j + 1] = v; dc[j + 1] = cnt;
    }
    for (int i = 0; i < nd; ++i) { if (r < dc[i]) return dv[i]; r -= dc[i]; }
    return dv[nd - 1];
}

static double lerp_np(double a, double b, double t)
{
    double diff = b - a;
    double r = a + diff * t;
    if (t >= 0.5) r = b - diff * (1.0 - t);
    return r;
}

static double percentile_g(getter_t get, const void *ctx, int n, double q, float *shadow, int sorted)
{
    if (n <= 0) return NAN;
    double vi = (q / 100.0) * (double)(n - 1);
    double prev = floor(vi);
    int ip = (int)prev;
    int in = ip + 1 < n ? ip + 1 : n - 1;
    double a = select_k(get, ctx, n, ip, shadow, sorted);
    double b = (in == ip) ? a : select_k(get, ctx, n, in, shadow, 1);
    return lerp_np(a, b, vi - prev);
}

static double median_g(getter_t get, const void *ctx, int n, float *shadow)
{
    if (n <= 0) return NAN;
    if (n & 1) return select_k(get, ctx, n, n / 2, shadow, 0);
    double a = select_k(get, ctx, n, n / 2 - 1, shadow, 0);
    double b = select_k(get, ctx, n, n / 2, shadow, 1);
    return (a + b) / 2.0;
}

/* getters */
static double get_ma(const void *ctx, int k) { return ma_at((const series_t *)ctx, k); }
static double get_absdiff(const void *ctx, int k) { const series_t *s = ctx; return fabs(ma_at(s, k + 1) - ma_at(s, k)); }

/* ---------------------------------------------------------------- find_peaks (scipy) on float32 */
static int find_peaks_f(const float *x, int n, double hmin, double pmin, int *peaks, float *heights, int cap)
{
    int np = 0, i = 1;
    while (i < n - 1) {
        if (x[i - 1] < x[i]) {
            int ahead = i + 1;
            while (ahead < n - 1 && x[ahead] == x[i]) ahead++;
            if (x[ahead] < x[i]) {
                int p = (i + ahead - 1) / 2;
                if ((double)x[p] >= hmin) {
                    float left_min = x[p], right_min = x[p];
                    for (int k = p; k >= 0 && x[k] <= x[p]; --k) if (x[k] < left_min) left_min = x[k];
                    for (int k = p; k < n && x[k] <= x[p]; ++k) if (x[k] < right_min) right_min = x[k];
                    float base = left_min > right_min ? left_min : right_min;
                    if ((double)(x[p] - base) >= pmin && np < cap) { peaks[np] = p; heights[np] = x[p]; np++; }
                }
                i = ahead;
            } else i++;
        } else i++;
    }
    return np;
}

/* ---------------------------------------------------------------- block autocorrelation */
/* ac[k] = sum_j x[j] x[j+k] for k < K, x = ma series (n samples) minus mean, via block pairs */
static void fill_block(const series_t *s, double mean, int blk, float *dst)
{
    int base = blk * B;
    if (s->n_sm <= 1) {
        for (int j = 0; j < B; ++j) { int idx = base + j; dst[j] = idx < s->n ? (float)(raw_at(s, idx) - mean) : 0.0f; }
    } else {
        /* moving average on the fly with a sliding sum, started at the block */
        ma_iter_t it; ma_begin(&it, s);
        for (int k = 0; k < base && k < s->n - 1; ++k) ma_next(&it);     /* position at base (O(n), done once per block) */
        for (int j = 0; j < B; ++j) {
            int idx = base + j;
            dst[j] = idx < s->n ? (float)(it.value - mean) : 0.0f;
            if (idx < s->n - 1) ma_next(&it);
        }
    }
    for (int j = B; j < NFFT; ++j) dst[j] = 0.0f;
}

static void autocorr_blocks(fx_cadence32_t *c, const series_t *s, double mean, int K)
{
    if (K > FX_CAD32_K) K = FX_CAD32_K;
    for (int k = 0; k < K; ++k) c->ac[k] = 0.0f;
    int nb = (s->n + B - 1) / B;
    int D = (K + B - 1) / B;
    for (int i = 0; i < nb; ++i) {
        fill_block(s, mean, i, c->fa);
        fx_fft32_rfft(c->fa, c->fb);                 /* fb = A_i (packed) */
        c->n_fft++;
        for (int d = 0; d <= D && i + d < nb; ++d) {
            fill_block(s, mean, i + d, c->fa);
            fx_fft32_rfft(c->fa, c->fc);             /* fc = B_{i+d} */
            c->n_fft++;
            /* conj(A) * B in packed format */
            c->fa[0] = c->fb[0] * c->fc[0];
            c->fa[1] = c->fb[1] * c->fc[1];
            for (int k = 1; k < NFFT / 2; ++k) {
                float ar = c->fb[2 * k], ai = c->fb[2 * k + 1], br = c->fc[2 * k], bi = c->fc[2 * k + 1];
                c->fa[2 * k] = ar * br + ai * bi;
                c->fa[2 * k + 1] = ar * bi - ai * br;
            }
            fx_fft32_irfft(c->fa, c->fc);            /* fc[kap] = corr for kap >= 0, fc[N+kap] for kap < 0 */
            c->n_fft++;
            int kmin = d == 0 ? 0 : -(B - 1), kmax = B - 1;
            for (int kap = kmin; kap <= kmax; ++kap) {
                int k = d * B + kap;
                if (k < 0 || k >= K) continue;
                c->ac[k] += c->fc[kap >= 0 ? kap : NFFT + kap];
            }
        }
    }
}

/* exact (double) autocorrelation sum_j (x[j]-mean)(x[j+k]-mean), j = 0 .. n-1-k, with two iterators */
static double exact_ac(const series_t *s, double mean, int k)
{
    if (k < 0 || k >= s->n) return 0.0;
    ma_iter_t a, b;
    ma_begin(&a, s); ma_begin(&b, s);
    for (int j = 0; j < k; ++j) ma_next(&b);
    double sum = 0.0;
    for (int j = 0; j + k < s->n; ++j) {
        sum += (a.value - mean) * (b.value - mean);
        if (j + k < s->n - 1) { ma_next(&a); ma_next(&b); }
    }
    return sum;
}

/* Refine a float32 peak at lag k (within [lo, hi]) to the exact argmax over k-R .. k+R; returns the
 * lag and writes the exact normalised height. Removes the one-bin plateau wander of the float32 FFT. */
#define REFINE_R 4
static int refine_peak(const series_t *s, double mean, double ac0, int k, int lo, int hi, double *height)
{
    int best = k; double bh = -1e300;
    for (int q = k - REFINE_R; q <= k + REFINE_R; ++q) {
        if (q < lo || q > hi) continue;
        double v = exact_ac(s, mean, q) / ac0;
        if (v > bh) { bh = v; best = q; }
    }
    *height = bh;
    return best;
}

/* mean and std of a series (two passes, double) */
static void mean_std(const series_t *s, double *mean, double *std)
{
    ma_iter_t it; double sum = 0.0;
    ma_begin(&it, s);
    for (int k = 0; k < s->n; ++k) { sum += it.value; if (k < s->n - 1) ma_next(&it); }
    double m = sum / (double)s->n, q = 0.0;
    ma_begin(&it, s);
    for (int k = 0; k < s->n; ++k) { double d = it.value - m; q += d * d; if (k < s->n - 1) ma_next(&it); }
    *mean = m; *std = sqrt(q / (double)s->n);
}

/* ---------------------------------------------------------------- _cadence_candidates */
typedef struct { double L, h; } cand_t;

static void sort_cands(cand_t *v, int n, int by_height)
{
    for (int i = 1; i < n; ++i) {
        cand_t k = v[i]; int j = i - 1;
        while (j >= 0 && (by_height ? v[j].h < k.h : v[j].L < k.L)) { v[j + 1] = v[j]; j--; }
        v[j + 1] = k;
    }
}

static int cadence_candidates(fx_cadence32_t *c, const series_t *s, double dt, double lag_min, double lag_max,
                              double thr, double prom, int max_tiers, cand_t *out)
{
    int n = s->n;
    if (n < 100) return 0;
    double mean, std;
    mean_std(s, &mean, &std);
    if (std < 1e-9) return 0;
    double span = (double)(n - 1) * dt;              /* t[-1] - t[0] with t = t0 + k*dt: same up to rounding */
    if (lag_max < 0) lag_max = 0.45 * span;
    int k0 = (int)(lag_min / dt);
    int k1 = (int)(lag_max / dt);
    if (k1 > n - 1) k1 = n - 1;
    if (k1 <= k0 + 2) return 0;
    autocorr_blocks(c, s, mean, k1 + 1);
    double a0 = (double)c->ac[0] + 1e-30;
    for (int k = 0; k <= k1 && k < FX_CAD32_K; ++k) c->ac[k] = (float)((double)c->ac[k] / a0);
    int np = find_peaks_f(c->ac + k0, k1 - k0, thr, prom, c->peaks, c->heights, FX_CAD32_NPEAKS);
    if (np == 0) return 0;
    /* exact refinement of every peak (lag and height in double) */
    double ac0 = (double)std * (double)std * (double)n + 1e-30;    /* sum (x-mean)^2 = n * var */
    ac0 = exact_ac(s, mean, 0) + 1e-30;
    if (np > 48) np = 48;
    for (int i = 0; i < np; ++i) {
        double hh;
        int k = refine_peak(s, mean, ac0, k0 + c->peaks[i], k0, k1 - 1, &hh);
        c->peaks[i] = k - k0; c->heights[i] = (float)hh;
        c->n_select++;
    }
    cand_t fund[64]; int nf = 0;
    for (int i = 0; i < np; ++i) {
        double L = (double)(k0 + c->peaks[i]) * dt;
        double h = exact_ac(s, mean, k0 + c->peaks[i]) / ac0;
        int harmonic = 0;
        for (int j = 0; j < nf; ++j) {
            double r = L / fund[j].L, rr = rint(r);
            if (rr >= 2.0 && fabs(r - rr) < 0.06) { harmonic = 1; break; }
        }
        if (!harmonic && nf < 64) { fund[nf].L = L; fund[nf].h = h; nf++; }
    }
    sort_cands(fund, nf, 1);
    if (nf > max_tiers) nf = max_tiers;
    sort_cands(fund, nf, 0);
    for (int i = 0; i < nf; ++i) out[i] = fund[i];
    return nf;
}

/* ---------------------------------------------------------------- _edges_two_level */
static inline int st_get(const uint8_t *bits, int k) { return (bits[k >> 3] >> (k & 7)) & 1; }
static inline void st_set(uint8_t *bits, int k, int v) { if (v) bits[k >> 3] |= (uint8_t)(1u << (k & 7)); else bits[k >> 3] &= (uint8_t)~(1u << (k & 7)); }

typedef struct { double *edges; int n, cap; } elist_t;

/* median of the low values (xs < mid), or of |low - med|: the filtered sequence is streamed once
 * into shadow (float32) and sorted; ties are resolved by a second streaming pass in double. */
static double median_low_stream(const series_t *s, double mid, double med_or_nan, int want_dev, float *shadow, int *n_out)
{
    ma_iter_t it; ma_begin(&it, s);
    int n = 0;
    for (int j = 0; j < s->n; ++j) {
        if (it.value < mid) shadow[n++] = (float)(want_dev ? fabs(it.value - med_or_nan) : it.value);
        if (j < s->n - 1) ma_next(&it);
    }
    *n_out = n;
    if (n == 0) return NAN;
    qsort(shadow, (size_t)n, sizeof(float), cmp_f);
    int ks[2] = { (n - 1) / 2, n / 2 };
    double vals[2];
    for (int q = 0; q < 2; ++q) {
        float f = shadow[ks[q]];
        int lo = 0, hi = n;
        while (lo < hi) { int m = (lo + hi) / 2; if (shadow[m] < f) lo = m + 1; else hi = m; }
        int r = ks[q] - lo;
        double dv[64]; int dc[64]; int nd = 0, overflow = 0;
        ma_begin(&it, s);
        for (int j = 0; j < s->n; ++j) {
            if (it.value < mid) {
                double v = want_dev ? fabs(it.value - med_or_nan) : it.value;
                if ((float)v == f) {
                    int i = 0;
                    while (i < nd && dv[i] != v) i++;
                    if (i < nd) dc[i]++;
                    else if (nd < 64) { dv[nd] = v; dc[nd] = 1; nd++; }
                    else overflow = 1;
                }
            }
            if (j < s->n - 1) ma_next(&it);
        }
        if (overflow || nd == 0) { vals[q] = (double)f; continue; }
        for (int i = 1; i < nd; ++i) {
            double v = dv[i]; int cnt = dc[i]; int jj = i - 1;
            while (jj >= 0 && dv[jj] > v) { dv[jj + 1] = dv[jj]; dc[jj + 1] = dc[jj]; jj--; }
            dv[jj + 1] = v; dc[jj + 1] = cnt;
        }
        double pick = dv[nd - 1];
        for (int i = 0; i < nd; ++i) { if (r < dc[i]) { pick = dv[i]; break; } r -= dc[i]; }
        vals[q] = pick;
    }
    return (n & 1) ? vals[1] : (vals[0] + vals[1]) / 2.0;
}

static int edges_two_level(fx_cadence32_t *c, series_t s /* copied: n_sm set here */, double T, int n_sm,
                           elist_t *el, uint8_t *state /* may be NULL */)
{
    int n = s.n, n_before = el->n;
    if (state) memset(state, 0, (size_t)((n + 7) / 8));
    if (n < 50) return 0;
    s.n_sm = n_sm > 1 ? n_sm : 1;
    double lo = percentile_g(get_ma, &s, n, 15.0, c->shadow, 0);
    double hi = percentile_g(get_ma, &s, n, 85.0, c->shadow, 1);
    double noise = 1.4826 * median_g(get_absdiff, &s, n - 1, c->shadow) / sqrt(2.0) + 1e-9;
    c->n_select += 3;
    if (hi - lo < 4.0 * noise) return 0;
    double mid = 0.5 * (lo + hi), hyst = 0.15 * (hi - lo);
    int nlow;
    double med_low = median_low_stream(&s, mid, NAN, 0, c->shadow, &nlow);
    double sig_lo = 1.4826 * median_low_stream(&s, mid, med_low, 1, c->shadow, &nlow) + 1e-9;
    c->n_select += 2;
    ma_iter_t it; ma_begin(&it, &s);
    int st = it.value > mid;
    double x0 = it.value;
    for (int k = 1; k < n; ++k) {
        ma_next(&it);
        double xk = it.value;
        if (!st && xk > mid + hyst) {
            int j = k;
            while (j > 0 && ma_at(&s, j) > lo + 3.0 * sig_lo) j--;
            double tj = s.h->t0 + (double)(s.first + (uint32_t)j) / s.h->fs;
            if (el->n == n_before || tj - el->edges[el->n - 1] > 0.25 * T) {
                if (el->n < el->cap) el->edges[el->n++] = tj;
            }
            st = 1;
        } else if (st && xk < mid - hyst) {
            st = 0;
        }
        if (state) st_set(state, k, st);
    }
    if (state) st_set(state, 0, x0 > mid);
    return el->n - n_before;
}

/* ---------------------------------------------------------------- _tier2_from_segments */
static int seg_bounds(const uint8_t *state, int n, int *bounds, int cap)
{
    int nb = 0;
    bounds[nb++] = 0;
    for (int k = 1; k < n && nb < cap - 1; ++k) if (st_get(state, k) != st_get(state, k - 1)) bounds[nb++] = k;
    bounds[nb++] = n;
    return nb;
}

static void tier2_from_segments(fx_cadence32_t *c, const series_t *base, const uint8_t *state1, double T1, double dts,
                                double *T2, double *s2)
{
    const double lag_min = 15e-3, thr = 0.25, prom = 0.08;
    *T2 = 0.0; *s2 = 0.0;
    int n = base->n;
    int nb = seg_bounds(state1, n, c->bounds, FX_CAD32_NBOUNDS);
    int kmax = 0, nsegs = 0;
    for (int i = 0; i + 1 < nb; ++i) {
        int a = c->bounds[i], b = c->bounds[i + 1];
        if (st_get(state1, a) && (double)(b - a) * dts >= 0.1) { nsegs++; if (b - a > kmax) kmax = b - a; }
    }
    if (nsegs == 0) return;
    int k0 = (int)(lag_min / dts);
    int k1 = (int)(0.45 * (double)kmax);
    if (k1 <= k0 + 2) return;
    int L = k1 - k0;
    if (L > FX_CAD32_K) L = FX_CAD32_K;
    for (int k = 0; k < L; ++k) { c->acc[k] = 0.0f; c->cnt[k] = 0; }
    int nseg = 0;
    for (int i = 0; i + 1 < nb; ++i) {
        int a = c->bounds[i], b = c->bounds[i + 1];
        if (!(st_get(state1, a) && (double)(b - a) * dts >= 0.1)) continue;
        series_t seg = *base; seg.first = base->first + (uint32_t)a; seg.n = b - a; seg.n_sm = 1;
        double m, sd;
        mean_std(&seg, &m, &sd);
        if (sd < 1e-9) continue;
        int k1s = (int)(0.45 * (double)seg.n);
        if (k1s > k1) k1s = k1;
        if (k1s <= k0) continue;
        autocorr_blocks(c, &seg, m, k1s);
        double a0 = (double)c->ac[0] + 1e-30;
        for (int k = 0; k < k1s - k0 && k < L; ++k) { c->acc[k] += (float)((double)c->ac[k0 + k] / a0); if (c->cnt[k] < 255) c->cnt[k]++; }
        nseg++;
    }
    if (nseg == 0) return;
    int n_ok = 0;
    for (int k = 0; k < L; ++k) if (c->cnt[k] > 0) { c->acc[k] = (float)((double)c->acc[k] / (double)c->cnt[k]); n_ok = k + 1; }
    int *pk = c->peaks;
    int np = find_peaks_f(c->acc, n_ok, thr, prom, pk, c->heights, FX_CAD32_NPEAKS);
    if (np == 0) return;
    float hmax = c->heights[0];
    for (int i = 1; i < np; ++i) if (c->heights[i] > hmax) hmax = c->heights[i];
    int kp = -1;
    for (int i = 0; i < np; ++i) if ((double)c->heights[i] >= 0.85 * (double)hmax) { kp = k0 + pk[i]; break; }
    double half = (double)kp / 2.0;
    for (int i = 0; i < np; ++i) {
        int p = k0 + pk[i];
        if (fabs((double)p - half) < 0.06 * half && (double)c->heights[i] >= 0.6 * (double)c->acc[kp - k0]) { kp = p; break; }
    }
    /* exact refinement of kp: the averaged normalised autocorrelation in double at kp-R .. kp+R */
    {
        int best = kp; double bh = -1e300;
        for (int q = kp - REFINE_R; q <= kp + REFINE_R; ++q) {
            if (q < k0 || q - k0 >= n_ok) continue;
            double sum = 0.0; int cntq = 0;
            for (int i = 0; i + 1 < nb; ++i) {
                int a = c->bounds[i], b = c->bounds[i + 1];
                if (!(st_get(state1, a) && (double)(b - a) * dts >= 0.1)) continue;
                series_t seg = *base; seg.first = base->first + (uint32_t)a; seg.n = b - a; seg.n_sm = 1;
                double m, sd; mean_std(&seg, &m, &sd);
                if (sd < 1e-9) continue;
                int k1s = (int)(0.45 * (double)seg.n); if (k1s > k1) k1s = k1;
                if (k1s <= k0 || q >= k1s) continue;
                double a0 = exact_ac(&seg, m, 0) + 1e-30;
                sum += exact_ac(&seg, m, q) / a0; cntq++;
            }
            if (cntq == 0) continue;
            double v = sum / (double)cntq;
            if (v > bh) { bh = v; best = q; }
        }
        if (bh > -1e300) { kp = best; *s2 = bh; } else *s2 = (double)c->acc[kp - k0];
    }
    double T = (double)kp * dts;
    if (T > 0.4 * T1) { *s2 = 0.0; return; }
    *T2 = T;
}

/* ---------------------------------------------------------------- _learn_cadence */
int fx_cadence32_learn(fx_cadence32_t *c, const fx_hist32_t *h, double W_s, double t_end)
{
    c->tiers.n_tiers = 0; c->n_fft = 0; c->n_select = 0;
    uint32_t held = h->count < FX_CAD32_H ? h->count : FX_CAD32_H;
    if (held < 2) return 0;
    uint32_t first = h->count - held;                       /* oldest held sample */
    double dts = (h->t0 + 1.0 / h->fs) - (h->t0 + 0.0 / h->fs);
    /* samples with t < t_end */
    int n = 0;
    while ((uint32_t)n < held && h->t0 + (double)(first + (uint32_t)n) / h->fs < t_end) n++;
    if (n < 200) return 0;
    c->n_used = (uint32_t)n;
    series_t x = { h, first, n, 0.0, 1 };
    int n_w = (int)(W_s / dts); if (n_w < 1) n_w = 1;
    (void)n_w;

    cand_t cands[8];
    int nc = cadence_candidates(c, &x, dts, 15e-3, -1.0, 0.15, 0.08, 3, cands);
    if (nc == 0) return 0;
    double T_s = cands[0].L;
    for (int i = 1; i < nc; ++i) if (cands[i].L < T_s) T_s = cands[i].L;
    int n_env = (int)(2.0 * T_s / dts); if (n_env < 3) n_env = 3;
    series_t xenv = x; xenv.n_sm = n_env;
    cand_t env[2];
    int ne = cadence_candidates(c, &xenv, dts, 3.0 * T_s, -1.0, 0.15, 0.08, 1, env);
    double T1, s1, T2_hint;
    if (ne > 0 && env[0].L > 2.5 * T_s) { T1 = env[0].L; s1 = env[0].h; T2_hint = T_s; }
    else {
        int best = 0;
        for (int i = 1; i < nc; ++i) if (cands[i].h > cands[best].h) best = i;
        T1 = cands[best].L; s1 = cands[best].h; T2_hint = 0.0;
    }
    elist_t el1 = { c->e1, 0, FX_CAD32_EDGES };
    edges_two_level(c, x, T1, 10, &el1, c->state1);
    if (el1.n < 2 && T2_hint == 0.0) {
        int found = 0;
        for (int i = 0; i < nc; ++i) {
            elist_t elb = { c->e1, 0, FX_CAD32_EDGES };
            edges_two_level(c, x, cands[i].L, 10, &elb, c->state1);
            if (elb.n >= 2) { T1 = cands[i].L; s1 = cands[i].h; el1 = elb; found = 1; break; }
        }
        if (!found) { el1.n = 0; edges_two_level(c, x, T1, 10, &el1, c->state1); }
    }
    fx_tier_t *t1 = &c->tiers.tier[0];
    memset(t1, 0, sizeof *t1);
    t1->T = T1; t1->strength = s1; t1->edges = c->e1; t1->n_edges = el1.n; t1->phase_start = NAN; t1->off2 = NAN;
    c->tiers.n_tiers = 1;

    double T2, s2;
    tier2_from_segments(c, &x, c->state1, T1, dts, &T2, &s2);
    if (T2 == 0.0 && T2_hint > 0.0 && T2_hint < 0.4 * T1) {
        T2 = T2_hint;
        for (int i = 0; i < nc; ++i) if (cands[i].L == T2_hint) { s2 = cands[i].h; break; }
    }
    if (T2 > 0.0) {
        int nb = seg_bounds(c->state1, n, c->bounds, FX_CAD32_NBOUNDS);
        elist_t el2 = { c->e2, 0, FX_CAD32_EDGES };
        for (int i = 0; i + 1 < nb; ++i) {
            int a = c->bounds[i], b = c->bounds[i + 1];
            if (!st_get(c->state1, a) || (double)(b - a) * dts < 2.0 * T2) continue;
            series_t seg = x; seg.first = x.first + (uint32_t)a; seg.n = b - a; seg.n_sm = 1;
            double p10 = percentile_g(get_ma, &seg, seg.n, 10.0, c->shadow, 0);
            c->n_select++;
            seg.sub = p10;
            edges_two_level(c, seg, T2, 3, &el2, NULL);
        }
        if (el2.n >= 2) {
            double cur_start = NAN, off2 = NAN, last_start = NAN;
            int last_state = st_get(c->state1, n - 1), nstarts = 0;
            for (int i = 0; i + 1 < nb; ++i) if (st_get(c->state1, c->bounds[i])) { last_start = h->t0 + (double)(first + (uint32_t)c->bounds[i]) / h->fs; nstarts++; }
            if (nstarts && last_state) cur_start = last_start;
            double offs[512]; int noffs = 0;      /* one per tier-1 high phase; 4 kB of stack */
            for (int i = 0; i + 1 < nb; ++i) {
                if (!st_get(c->state1, c->bounds[i])) continue;
                double s0 = h->t0 + (double)(first + (uint32_t)c->bounds[i]) / h->fs;
                if (last_state && s0 == last_start) continue;
                double nxt = NAN;
                for (int k = 0; k < el2.n; ++k) if (c->e2[k] > s0 && (isnan(nxt) || c->e2[k] < nxt)) nxt = c->e2[k];
                if (!isnan(nxt) && noffs < 512) offs[noffs++] = nxt - s0;
            }
            if (noffs) {
                /* median of a small double array */
                for (int i = 1; i < noffs; ++i) { double v = offs[i]; int j = i - 1; while (j >= 0 && offs[j] > v) { offs[j + 1] = offs[j]; j--; } offs[j + 1] = v; }
                off2 = (noffs & 1) ? offs[noffs / 2] : (offs[noffs / 2 - 1] + offs[noffs / 2]) / 2.0;
            }
            int ncur = 0;
            if (!isnan(cur_start)) for (int k = 0; k < el2.n; ++k) if (c->e2[k] > cur_start) c->e2cur[ncur++] = c->e2[k];
            fx_tier_t *t2 = &c->tiers.tier[1];
            memset(t2, 0, sizeof *t2);
            t2->T = T2; t2->strength = s2; t2->edges = c->e2; t2->n_edges = el2.n; t2->is_tier2 = 1;
            t2->phase_start = cur_start; t2->edges_current = c->e2cur; t2->n_current = ncur; t2->off2 = off2;
            c->tiers.n_tiers = 2;
        }
    }
    return c->tiers.n_tiers;
}
