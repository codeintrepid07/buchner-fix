from pathlib import Path
import numpy as np
from scipy.special import gammaln as origgammaln

p = Path('/root/problems.py')
s = p.read_text()
old = """def mygammaln(c):
    if np.shape(c) == ():
        return origgammaln(c)
    o = c.copy()
    o[:] = origgammaln(c[0])
    return o
"""
new = """def mygammaln(c):
    if np.shape(c) == ():
        return origgammaln(c)
    return np.vectorize(origgammaln, otypes=[float])(c)
"""
if old not in s:
    raise SystemExit('Expected gammaln block not found in problems.py')
p.write_text(s.replace(old, new))
