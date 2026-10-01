/* fx_cadence.c — port of features._learn_cadence (dcsim v1, OPEN-9) and helpers. Every numpy /
 * scipy primitive used by the Python code has an exact-semantics counterpart here:
 *   _movavg            -> fx_movavg (bit-compatible)
 *   np.percentile      -> percentile() (method "linear", numpy's _lerp)
 *   np.median          -> median()
 *   scipy.find_peaks(height=, prominence=) -> find_peaks() (_local_maxima_1d + _peak_prominences, wlen=None)
 *   rfft autocorrelation -> autocorr() (radix-2 FFT, zero padded to a power of two >= 2n)
 *   Python round()     -> rint (round half to even)
 *   Python float %     -> fmod with the sign of the divisor */
#include "fx_cadence.h"
#include "fx_filters.h"
#include <math.h>
#include <string.h>
#include <stdlib.h>

#define FX_PI 3.14159265358979323846

/* ------------------------------------------------------------------ small numpy equivalents */
static int cmp_double(const void *a, const void *b)
{
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

static double lerp_np(double a, double b, double t)   /* numpy.lib._function_base_impl._lerp */
{
    double diff = b - a;
    double r = a + diff * t;
    if (t >= 0.5) r = b - diff * (1.0 - t);
    return r;
}

/* np.percentile(x, q), method "linear"; sorts a copy in buf (n doubles) */
static double percentile(const double *x, int n, double q, double *buf)
{
    if (n <= 0) return NAN;
    memcpy(buf, x, sizeof(double) * (size_t)n);
    qsort(buf, (size_t)n, sizeof(double), cmp_double);
    double vi = (q / 100.0) * (double)(n - 1);
    double prev = floor(vi);
    int ip = (int)prev;
    int in = ip + 1 < n ? ip + 1 : n - 1;
    double gamma = vi - prev;
    return lerp_np(buf[ip], buf[in], gamma);
}

static double median(const double *x, int n, double *buf)
{
    if (n <= 0) return NAN;
    memcpy(buf, x, sizeof(double) * (size_t)n);
    qsort(buf, (size_t)n, sizeof(double), cmp_double);
    if (n & 1) return buf[n / 2];
    return (buf[n / 2 - 1] + buf[n / 2]) / 2.0;
}

/* scipy.signal.find_peaks(x, height=hmin, prominence=pmin): local maxima (plateaus -> midpoint),
 * height filter, then prominence with wlen=None. Returns the number of peaks kept. */
static int find_peaks(const double *x, int n, double hmin, double pmin, int *peaks, double *heights)
{
    int np = 0;
    int i = 1;
    while (i < n - 1) {
        if (x[i - 1] < x[i]) {
            int ahead = i + 1;
            while (ahead < n - 1 && x[ahead] == x[i]) ahead++;
            if (x[ahead] < x[i]) {
                int left = i, right = ahead - 1;
                int p = (left + right) / 2;
                if (x[p] >= hmin) {
                    /* prominence */
                    double left_min = x[p], right_min = x[p];
                    for (int k = p; k >= 0 && x[k] <= x[p]; --k) if (x[k] < left_min) left_min = x[k];
                    for (int k = p; k < n && x[k] <= x[p]; ++k) if (x[k] < right_min) right_min = x[k];
                    double base = left_min > right_min ? left_min : right_min;
                    if (x[p] - base >= pmin) { peaks[np] = p; heights[np] = x[p]; np++; }
                }
                i = ahead;
            } else {
                i++;
            }
        } else {
            i++;
        }
    }
    return np;
}

/* ------------------------------------------------------------------ FFT autocorrelation */
static void fft(double *re, double *im, int log2n, int inverse)
{
    int n = 1 << log2n;
    for (int i = 1, j = 0; i < n; ++i) {               /* bit reversal */
        int bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) { double t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
    }
    for (int len = 2; len <= n; len <<= 1) {
        double ang = 2.0 * FX_PI / (double)len * (inverse ? 1.0 : -1.0);
        double wr = cos(ang), wi = sin(ang);
        for (int i = 0; i < n; i += len) {
            double cr = 1.0, ci = 0.0;
            for (int j = 0; j < len / 2; ++j) {
                int a = i + j, b = i + j + len / 2;
                double ur = re[a], ui = im[a];
                double vr = re[b] * cr - im[b] * ci, vi = re[b] * ci + im[b] * cr;
                re[a] = ur + vr; im[a] = ui + vi;
                re[b] = ur - vr; im[b] = ui - vi;
                double ncr = cr * wr - ci * wi;
                ci = cr * wi + ci * wr;
                cr = ncr;
            }
        }
    }
    if (inverse) for (int i = 0; i < n; ++i) { re[i] /= (double)n; im[i] /= (double)n; }
}

/* ac[k] = sum_j x[j] x[j+k], k = 0..n-1, normalised by ac[0] + 1e-30 (Python: rfft(x, 2n)) */
static void autocorr(fx_cadence_t *c, const double *x, int n, double *ac)
{
    int log2n = 1;
    while ((1 << log2n) < 2 * n) log2n++;
    int N = 1 << log2n;
    for (int i = 0; i < N; ++i) { c->re[i] = i < n ? x[i] : 0.0; c->im[i] = 0.0; }
    fft(c->re, c->im, log2n, 0);
    for (int i = 0; i < N; ++i) { c->re[i] = c->re[i] * c->re[i] + c->im[i] * c->im[i]; c->im[i] = 0.0; }
    fft(c->re, c->im, log2n, 1);
    double a0 = c->re[0] + 1e-30;
    for (int k = 0; k < n; ++k) ac[k] = c->re[k] / a0;
}

/* ------------------------------------------------------------------ _cadence_candidates */
typedef struct { double L, h; } cand_t;

static void sort_cands(cand_t *v, int n, int by_height)    /* stable insertion sort, descending */
{
    for (int i = 1; i < n; ++i) {
        cand_t k = v[i];
        int j = i - 1;
        while (j >= 0 && (by_height ? v[j].h < k.h : v[j].L < k.L)) { v[j + 1] = v[j]; j--; }
        v[j + 1] = k;
    }
}

static int cadence_candidates(fx_cadence_t *c, const double *t, const double *xin, int n,
                              double lag_min, double lag_max /* <0: None */, double thr, double prom,
                              int max_tiers, cand_t *out)
{
    if (n < 100) return 0;
    double m = fx_mean(xin, n);
    for (int k = 0; k < n; ++k) c->tmp[k] = xin[k] - m;
    if (fx_std(c->tmp, n) < 1e-9) return 0;
    autocorr(c, c->tmp, n, c->ac);
    double dt = t[1] - t[0];
    double span = t[n - 1] - t[0];
    if (lag_max < 0) lag_max = 0.45 * span;
    int k0 = (int)(lag_min / dt);
    int k1 = (int)(lag_max / dt);
    if (k1 > n - 1) k1 = n - 1;
    if (k1 <= k0 + 2) return 0;
    int np = find_peaks(c->ac + k0, k1 - k0, thr, prom, c->peaks, c->heights);
    if (np == 0) return 0;
    /* peaks are in ascending lag order already (argsort of distinct increasing lags) */
    cand_t fund[64];
    int nf = 0;
    for (int i = 0; i < np; ++i) {
        double L = (double)(k0 + c->peaks[i]) * dt, h = c->heights[i];
        int harmonic = 0;
        for (int j = 0; j < nf; ++j) {
            double r = L / fund[j].L;
            double rr = rint(r);
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

/* ------------------------------------------------------------------ _edges_two_level */
typedef struct { double *edges; int n_edges, cap; } edge_list_t;

/* x is smoothed into c->xs (n_sm) ; state out (0/1 per sample). Returns number of edges appended. */
static int edges_two_level(fx_cadence_t *c, const double *t, const double *x, int n, double T, int n_w, int n_sm,
                           edge_list_t *el, unsigned char *state)
{
    int n_before = el->n_edges;
    memset(state, 0, (size_t)n);
    if (n < 50) return 0;
    double *xs = c->xs;
    fx_movavg(x, n, n_sm > 1 ? n_sm : 1, xs);
    double lo = percentile(xs, n, 15.0, c->tmp), hi = percentile(xs, n, 85.0, c->tmp);
    for (int k = 0; k + 1 < n; ++k) c->seg[k] = fabs(xs[k + 1] - xs[k]);
    double noise = 1.4826 * median(c->seg, n - 1, c->tmp) / sqrt(2.0) + 1e-9;
    if (hi - lo < 4.0 * noise) return 0;
    double mid = 0.5 * (lo + hi), hyst = 0.15 * (hi - lo);
    int nlow = 0;
    for (int k = 0; k < n; ++k) if (xs[k] < mid) c->seg[nlow++] = xs[k];
    double med_low = median(c->seg, nlow, c->tmp);
    for (int k = 0; k < nlow; ++k) c->seg[k] = fabs(c->seg[k] - med_low);
    double sig_lo = 1.4826 * median(c->seg, nlow, c->tmp) + 1e-9;
    int st = xs[0] > mid;
    for (int k = 1; k < n; ++k) {
        if (!st && xs[k] > mid + hyst) {
            int j = k;
            while (j > 0 && xs[j] > lo + 3.0 * sig_lo) j--;
            if (el->n_edges == n_before || t[j] - el->edges[el->n_edges - 1] > 0.25 * T) {
                if (el->n_edges < el->cap) el->edges[el->n_edges++] = t[j];
            }
            st = 1;
        } else if (st && xs[k] < mid - hyst) {
            st = 0;
        }
        state[k] = (unsigned char)st;
    }
    state[0] = xs[0] > mid;
    (void)n_w;   /* steps (x[j + n_w] - x[j]) are a diagnostic (resid_period), not a model input */
    return el->n_edges - n_before;
}

/* ------------------------------------------------------------------ _tier2_from_segments */
static int seg_bounds(const unsigned char *state, int n, int *bounds)   /* [0, change points..., n] */
{
    int nb = 0;
    bounds[nb++] = 0;
    for (int k = 1; k < n; ++k) if (state[k] != state[k - 1]) bounds[nb++] = k;
    bounds[nb++] = n;
    return nb;
}

static void tier2_from_segments(fx_cadence_t *c, const double *x, const unsigned char *state1, int n,
                                double T1, double dts, double *T2, double *s2)
{
    const double lag_min = 15e-3, thr = 0.25, prom = 0.08;
    *T2 = 0.0; *s2 = 0.0;
    int *bounds = c->peaks;                     /* reuse: up to n+1 ints */
    int nb = seg_bounds(state1, n, bounds);
    int kmax = 0, nsegs = 0;
    for (int i = 0; i + 1 < nb; ++i) {
        int a = bounds[i], b = bounds[i + 1];
        if (state1[a] && (double)(b - a) * dts >= 0.1) { nsegs++; if (b - a > kmax) kmax = b - a; }
    }
    if (nsegs == 0) return;
    int k0 = (int)(lag_min / dts);
    int k1 = (int)(0.45 * (double)kmax);
    if (k1 <= k0 + 2) return;
    int L = k1 - k0;
    for (int k = 0; k < L; ++k) { c->acc[k] = 0.0; c->cnt[k] = 0; }
    int nseg = 0;
    for (int i = 0; i + 1 < nb; ++i) {
        int a = bounds[i], b = bounds[i + 1];
        if (!(state1[a] && (double)(b - a) * dts >= 0.1)) continue;
        int ns = b - a;
        double m = fx_mean(x + a, ns);
        for (int k = 0; k < ns; ++k) c->seg[k] = x[a + k] - m;
        if (fx_std(c->seg, ns) < 1e-9) continue;
        autocorr(c, c->seg, ns, c->ac);
        int k1s = (int)(0.45 * (double)ns);
        if (k1s > k1) k1s = k1;
        if (k1s <= k0) continue;
        for (int k = 0; k < k1s - k0; ++k) { c->acc[k] += c->ac[k0 + k]; c->cnt[k] += 1; }
        nseg++;
    }
    if (nseg == 0) return;
    int n_ok = 0;
    for (int k = 0; k < L; ++k) if (c->cnt[k] > 0) { c->acc[k] /= (double)c->cnt[k]; n_ok = k + 1; }
    /* cnt is non-increasing in k (prefix sums), so acc[m_ok] is the first n_ok entries */
    int *pk = c->peaks + (nb + 1);              /* separate area from bounds */
    int np = find_peaks(c->acc, n_ok, thr, prom, pk, c->heights);
    if (np == 0) return;
    double hmax = c->heights[0];
    for (int i = 1; i < np; ++i) if (c->heights[i] > hmax) hmax = c->heights[i];
    int kp = -1;
    for (int i = 0; i < np; ++i) if (c->heights[i] >= 0.85 * hmax) { kp = k0 + pk[i]; break; }   /* .min() */
    double half = (double)kp / 2.0;
    for (int i = 0; i < np; ++i) {
        int p = k0 + pk[i];
        if (fabs((double)p - half) < 0.06 * half && c->heights[i] >= 0.6 * c->acc[kp - k0]) { kp = p; break; }
    }
    double T = (double)kp * dts;
    if (T > 0.4 * T1) return;
    *T2 = T; *s2 = c->acc[kp - k0];
}

/* ------------------------------------------------------------------ _learn_cadence */
int fx_cadence_learn(fx_cadence_t *c, const float *si, int n_all, double t0, double fs_slow, double W_s, double t_end)
{
    c->tiers.n_tiers = 0;
    if (n_all < 2) return 0;
    if (n_all > FX_CAD_MAX_HIST) n_all = FX_CAD_MAX_HIST;
    double dts = (t0 + 1.0 / fs_slow) - (t0 + 0.0 / fs_slow);        /* st[1] - st[0] */
    int n = 0;
    while (n < n_all && t0 + (double)n / fs_slow < t_end) n++;        /* m = st < t_end */
    if (n < 200) return 0;
    double *t = c->t, *x = c->x;
    for (int k = 0; k < n; ++k) { t[k] = t0 + (double)k / fs_slow; x[k] = (double)si[k]; }
    int n_w = (int)(W_s / dts); if (n_w < 1) n_w = 1;

    cand_t cands[8];
    int nc = cadence_candidates(c, t, x, n, 15e-3, -1.0, 0.15, 0.08, 3, cands);
    if (nc == 0) return 0;
    double T_s = cands[0].L;
    for (int i = 1; i < nc; ++i) if (cands[i].L < T_s) T_s = cands[i].L;
    int n_env = (int)(2.0 * T_s / dts); if (n_env < 3) n_env = 3;
    fx_movavg(x, n, n_env, c->xenv);
    cand_t env[2];
    int ne = cadence_candidates(c, t, c->xenv, n, 3.0 * T_s, -1.0, 0.15, 0.08, 1, env);
    double T1, s1, T2_hint;
    if (ne > 0 && env[0].L > 2.5 * T_s) {
        T1 = env[0].L; s1 = env[0].h; T2_hint = T_s;
    } else {
        int best = 0;
        for (int i = 1; i < nc; ++i) if (cands[i].h > cands[best].h) best = i;   /* stable: first max */
        T1 = cands[best].L; s1 = cands[best].h; T2_hint = 0.0;
    }
    edge_list_t el1 = { c->e1, 0, FX_CAD_MAX_EDGES };
    edges_two_level(c, t, x, n, T1, n_w, 10, &el1, c->state1);
    if (el1.n_edges < 2 && T2_hint == 0.0) {
        for (int i = 0; i < nc; ++i) {                 /* cands are sorted by period descending */
            edge_list_t elb = { c->e1, 0, FX_CAD_MAX_EDGES };
            edges_two_level(c, t, x, n, cands[i].L, n_w, 10, &elb, c->st_tmp);
            if (elb.n_edges >= 2) {
                T1 = cands[i].L; s1 = cands[i].h; el1 = elb;
                memcpy(c->state1, c->st_tmp, (size_t)n);
                break;
            }
        }
        if (el1.n_edges < 2) {                         /* no candidate gave two edges: keep the first result */
            el1.n_edges = 0;
            edges_two_level(c, t, x, n, T1, n_w, 10, &el1, c->state1);
        }
    }
    fx_tier_t *t1 = &c->tiers.tier[0];
    memset(t1, 0, sizeof *t1);
    t1->T = T1; t1->strength = s1; t1->edges = c->e1; t1->n_edges = el1.n_edges;
    t1->phase_start = NAN; t1->off2 = NAN;
    c->tiers.n_tiers = 1;

    double T2, s2;
    tier2_from_segments(c, x, c->state1, n, T1, dts, &T2, &s2);
    if (T2 == 0.0 && T2_hint > 0.0 && T2_hint < 0.4 * T1) {
        T2 = T2_hint;
        for (int i = 0; i < nc; ++i) if (cands[i].L == T2_hint) { s2 = cands[i].h; break; }
    }
    if (T2 > 0.0) {
        int *bounds = c->peaks;
        int nb = seg_bounds(c->state1, n, bounds);
        edge_list_t el2 = { c->e2, 0, FX_CAD_MAX_EDGES };
        for (int i = 0; i + 1 < nb; ++i) {
            int a = bounds[i], b = bounds[i + 1];
            if (!c->state1[a] || (double)(b - a) * dts < 2.0 * T2) continue;
            double p10 = percentile(x + a, b - a, 10.0, c->tmp);
            for (int k = 0; k < b - a; ++k) c->seg[k] = x[a + k] - p10;
            /* edges_two_level smooths into c->xs and uses c->tmp; seg is its input */
            int before = el2.n_edges;
            edges_two_level(c, t + a, c->seg, b - a, T2, n_w, 3, &el2, c->st_tmp);
            (void)before;
            nb = seg_bounds(c->state1, n, bounds);     /* c->peaks may have been reused inside; rebuild */
        }
        if (el2.n_edges >= 2) {
            /* starts of the tier-1 high segments */
            double cur_start = NAN, off2 = NAN;
            int last_state = c->state1[n - 1];
            double offs[FX_CAD_MAX_EDGES]; int noffs = 0;
            double last_start = NAN; int nstarts = 0;
            for (int i = 0; i + 1 < nb; ++i) if (c->state1[bounds[i]]) { last_start = t[bounds[i]]; nstarts++; }
            if (nstarts && last_state) cur_start = last_start;
            for (int i = 0; i + 1 < nb; ++i) {
                if (!c->state1[bounds[i]]) continue;
                double s0 = t[bounds[i]];
                if (last_state && s0 == last_start) continue;      /* starts[:-1] when in a compute phase */
                double nxt = NAN;
                for (int k = 0; k < el2.n_edges; ++k) if (c->e2[k] > s0 && (isnan(nxt) || c->e2[k] < nxt)) nxt = c->e2[k];
                if (!isnan(nxt) && noffs < FX_CAD_MAX_EDGES) offs[noffs++] = nxt - s0;
            }
            if (noffs) off2 = median(offs, noffs, c->tmp);
            int ncur = 0;
            if (!isnan(cur_start))
                for (int k = 0; k < el2.n_edges; ++k) if (c->e2[k] > cur_start) c->e2cur[ncur++] = c->e2[k];
            fx_tier_t *t2 = &c->tiers.tier[1];
            memset(t2, 0, sizeof *t2);
            t2->T = T2; t2->strength = s2; t2->edges = c->e2; t2->n_edges = el2.n_edges;
            t2->is_tier2 = 1; t2->phase_start = cur_start; t2->edges_current = c->e2cur; t2->n_current = ncur; t2->off2 = off2;
            c->tiers.n_tiers = 2;
        }
    }
    return c->tiers.n_tiers;
}

/* ------------------------------------------------------------------ phase_err (features.extract) */
static double fold(double t_on, double t_ref, double T)
{
    double dphi = fmod((t_on - t_ref) / T, 1.0);
    if (dphi < 0.0) dphi += 1.0;                 /* Python float % takes the sign of the divisor */
    return dphi < 1.0 - dphi ? dphi : 1.0 - dphi;
}

static double t_ref_from_edges(const double *e, int n, double T)
{
    double re = 0.0, im = 0.0;
    for (int k = 0; k < n; ++k) {
        double a = 2.0 * FX_PI * e[k] / T;
        re += cos(a); im += sin(a);
    }
    re /= (double)n; im /= (double)n;
    return atan2(im, re) / (2.0 * FX_PI) * T;
}

double fx_cadence_phase_err(const fx_cadence_tiers_t *t, double t_on)
{
    double best = NAN;
    for (int i = 0; i < t->n_tiers; ++i) {
        const fx_tier_t *ti = &t->tier[i];
        double pe;
        if (ti->is_tier2) {
            if (isnan(ti->phase_start)) continue;
            double t_ref;
            if (ti->n_current >= 1) t_ref = t_ref_from_edges(ti->edges_current, ti->n_current, ti->T);
            else if (!isnan(ti->off2)) t_ref = ti->phase_start + ti->off2;
            else continue;
            pe = fold(t_on, t_ref, ti->T);
        } else {
            if (ti->n_edges < 2) continue;
            pe = fold(t_on, t_ref_from_edges(ti->edges, ti->n_edges, ti->T), ti->T);
        }
        if (isnan(best) || pe < best) best = pe;
    }
    return best;
}

void fx_cadence_work_features(const fx_cadence_tiers_t *t, double t_on,
                              double *has_period, double *period_strength, double *phase_err)
{
    *has_period = t->n_tiers ? 1.0 : 0.0;
    *period_strength = t->n_tiers ? t->tier[0].strength : 0.0;
    *phase_err = fx_cadence_phase_err(t, t_on);
}
