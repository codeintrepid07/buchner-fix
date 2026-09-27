from pathlib import Path

p = Path("/root/montepython_public/input/base2018TTTEEE.param")
s = p.read_text()

old = "data.cosmo_arguments['sBBN file'] = data.path['cosmo']+'/external/bbn/sBBN.dat'"
new = "data.cosmo_arguments['sBBN file'] = 'external/bbn/sBBN.dat'"

if old not in s:
    raise SystemExit("Expected sBBN file line not found")

s = s.replace(old, new)

base_path_line = "data.cosmo_arguments['base_path'] = '/opt/conda/lib/python3.12/site-packages/classy/'"

if base_path_line not in s:
    s += "\n" + base_path_line + "\n"

p.write_text(s)
print("MontePython config fixed")
