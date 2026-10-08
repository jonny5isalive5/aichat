import ctypes, numpy as np, os
_lib = ctypes.CDLL(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bin', 'libdtw.so'))
_lib.dtw_many.argtypes = [np.ctypeslib.ndpointer(np.float32, flags='C'), np.ctypeslib.ndpointer(np.int32, flags='C'), ctypes.c_int,
                          np.ctypeslib.ndpointer(np.float32, flags='C'), np.ctypeslib.ndpointer(np.int32, flags='C'), ctypes.c_int,
                          ctypes.c_int, ctypes.c_int, np.ctypeslib.ndpointer(np.float32, flags='C')]
def dtw_dist(Q, lq, Tm, lt):
    Q = np.ascontiguousarray(Q, np.float32); Tm = np.ascontiguousarray(Tm, np.float32)
    nq, T, NB = Q.shape; nt = Tm.shape[0]; out = np.zeros((nq, nt), np.float32)
    _lib.dtw_many(Q, np.ascontiguousarray(lq, np.int32), nq, Tm, np.ascontiguousarray(lt, np.int32), nt, T, NB, out)
    return out
