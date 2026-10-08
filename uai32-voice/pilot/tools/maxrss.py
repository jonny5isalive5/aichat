"""maxrss.py CMD [ARGS...] -- run CMD with this process's stdin/stdout, then print to stderr the child's peak resident
set size in kB (ru_maxrss from wait4: the same kernel counter that /usr/bin/time -v reports as 'Maximum resident set
size (kbytes)'), its user+system CPU time, wall time and exit status.  Used because GNU time is not installed here."""
import sys, subprocess, resource, time
t0 = time.perf_counter(); r = subprocess.run(sys.argv[1:]); wall = time.perf_counter() - t0
u = resource.getrusage(resource.RUSAGE_CHILDREN)
sys.stderr.write('maxrss_kb=%d cpu_ms=%.1f wall_ms=%.1f exit=%d cmd=%s\n' % (u.ru_maxrss, 1e3 * (u.ru_utime + u.ru_stime), 1e3 * wall, r.returncode, ' '.join(sys.argv[1:])))
sys.exit(r.returncode)
