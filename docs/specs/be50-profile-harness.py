#!/usr/bin/env python
"""BE50 — per-phase timing of ONE fimeval evaluation, under a named configuration.

    python profile_phases.py --config A|B|B2|C --method intersected_extent|bootstrap \
        --data DIR --out results.jsonl [--runs 2]

Configs (what each app actually passes to fimeval.EvaluateFIM):
  A   web worker today : fimeval 0.1.64, BE31 pre-clip of candidates to the benchmark
                         extent, target_crs=EPSG:5070 only; bootstrap = stratified,
                         100 it x 500 pts, no seed, plot_metrics=False
  B   desktop kwargs on the web library : 0.1.64, NO pre-clip, target_crs + target_resolution=10;
                         bootstrap = random, seed 42, plot_metrics=True   (desktop GUI defaults)
  B2  as B but plot_metrics=False                                        (isolates plotting)
  C   desktop as shipped : B's kwargs on fimeval 0.1.62 (run with PYTHONPATH=<0.1.62 dir>)
Run 1 in a process is COLD (import time reported separately), run 2 is WARM.
Phases are measured by wrapping the names fimeval itself calls; fimeval is not modified.
"""
import argparse, functools, glob, json, os, resource, shutil, sys, tempfile, time

T_IMPORT0 = time.perf_counter()
import fimeval                                   # noqa: E402
import fimeval.utilis as U                       # noqa: E402
import fimeval.ContingencyMap.evaluationFIM as E # noqa: E402
T_IMPORT = time.perf_counter() - T_IMPORT0

TARGET_CRS = 'EPSG:5070'
PHASES = {}

def timed(name, fn):
    @functools.wraps(fn)
    def w(*a, **k):
        t = time.perf_counter()
        try:
            return fn(*a, **k)
        finally:
            PHASES[name] = PHASES.get(name, 0.0) + time.perf_counter() - t
    return w

# Names looked up at call time inside fimeval → wrapping the module attributes is enough.
E.MakeFIMsUniform = timed('uniform_total', E.MakeFIMsUniform)
U.reprojectFIMs = timed('uniform.reproject', U.reprojectFIMs)
U.resample_to_resolution = timed('uniform.resample', U.resample_to_resolution)
U.compress_tif_lzw = timed('uniform.compress', U.compress_tif_lzw)
E.ExtractPWB = timed('pwb_fetch_arcgis', E.ExtractPWB)
E.run_bootstrap = timed('bootstrap', E.run_bootstrap)
E.evaluateFIM = timed('evaluate_total', E.evaluateFIM)


def stage(data, main_dir, copy):
    case = os.path.join(main_dir, 'case_study'); os.makedirs(case)
    # The web worker stores the benchmark as benchmark.tif and candidates under their
    # own names (BE31's pre-clip keys on that); the desktop user keeps the _BM name.
    for tif in sorted(glob.glob(os.path.join(data, '*.tif'))):
        base = os.path.basename(tif)
        if copy and base.upper().endswith('_BM.TIF'):
            base = 'benchmark.tif'
        dst = os.path.join(case, base)
        (shutil.copy2 if copy else os.symlink)(os.path.abspath(tif), dst)
    return case


def kwargs_for(config, method):
    k = {'target_crs': TARGET_CRS}
    if config in ('A', 'A0'):
        if method == 'bootstrap':
            k.update(sub_method='stratified', n_iterations=100, n_points=500, plot_metrics=False)
    else:  # B, B2, C = desktop GUI defaults
        k['target_resolution'] = 10
        if method == 'bootstrap':
            k.update(sub_method='random', n_iterations=100, n_points=500, seed=42,
                     save_points=False, save_every=1,
                     plot_metrics=(config != 'B2'), spacing_range=None)
    return k


def one_run(config, method, data, run_idx):
    PHASES.clear()
    with tempfile.TemporaryDirectory() as main_dir:
        case = stage(data, main_dir, copy=(config in ('A', 'A0')))
        out = os.path.join(main_dir, 'out'); os.makedirs(out)
        t_all = time.perf_counter()
        if config == 'A':
            from tethysapp.fimeval_gui.job_types.evaluate_fim import _clip_candidates_to_benchmark
            t = time.perf_counter(); _clip_candidates_to_benchmark(case); PHASES['preclip'] = time.perf_counter() - t
        t = time.perf_counter()
        fimeval.EvaluateFIM(main_dir, method, out, **kwargs_for(config, method))
        PHASES['EvaluateFIM'] = time.perf_counter() - t
        wall = time.perf_counter() - t_all
        csvs = [os.path.join(r, f) for r, _, fs in os.walk(out) for f in fs if f == 'EvaluationMetrics.csv']
        metrics = {}
        if csvs:
            import csv
            with open(csvs[0]) as fh:
                for row in csv.reader(fh):
                    if row and len(row) > 1 and row[0] != 'Metrics':
                        metrics[row[0]] = row[1]
        n_out = sum(len(fs) for _, _, fs in os.walk(out))
        pngs = sum(1 for _, _, fs in os.walk(out) for f in fs if f.lower().endswith('.png'))
    ph = dict(PHASES)
    ph['evaluate.other(mask+metrics+contingency)'] = round(
        ph.get('evaluate_total', 0) - ph.get('bootstrap', 0) - ph.get('pwb_fetch_arcgis', 0), 3)
    return {
        'config': config, 'method': method, 'data': os.path.basename(data.rstrip('/')),
        'fimeval': getattr(fimeval, '__version__', '?'), 'fimeval_dir': os.path.dirname(fimeval.__file__),
        'run': 'cold' if run_idx == 0 else 'warm', 'import_s': round(T_IMPORT, 2) if run_idx == 0 else 0,
        'wall_s': round(wall, 2), 'phases_s': {k: round(v, 2) for k, v in ph.items()},
        'peak_rss_mb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024,
        'loadavg_1m': round(os.getloadavg()[0], 2),
        'ok': bool(csvs), 'n_outputs': n_out, 'n_png': pngs, 'metrics': metrics,
    }


def main():
    p = argparse.ArgumentParser(); p.add_argument('--config', required=True); p.add_argument('--method', required=True)
    p.add_argument('--data', required=True); p.add_argument('--out', required=True); p.add_argument('--runs', type=int, default=2)
    a = p.parse_args()
    os.environ.setdefault('PROJ_NETWORK', 'OFF')
    import contextlib, io
    for i in range(a.runs):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                r = one_run(a.config, a.method, a.data, i)
            except Exception as exc:
                r = {'config': a.config, 'method': a.method, 'run': i, 'error': repr(exc)}
        r['fimeval_said'] = [ln for ln in buf.getvalue().splitlines() if 'Error' in ln][:5]
        with open(a.out, 'a') as fh:
            fh.write(json.dumps(r) + '\n')
        print(json.dumps({k: r.get(k) for k in ('config', 'method', 'run', 'wall_s', 'ok', 'peak_rss_mb', 'error')}), flush=True)


if __name__ == '__main__':
    main()
