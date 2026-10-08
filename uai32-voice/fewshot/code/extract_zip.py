# Extract only mini_speech_commands/<word>/*.wav from the zip (skip __MACOSX and anything odd).
import sys, zipfile, os, re
zpath, out = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(zpath)
pat = re.compile(r'^mini_speech_commands/([a-z]+)/([0-9a-f]+_nohash_[0-9]+\.wav)$')
n = 0
for info in z.infolist():
    m = pat.match(info.filename)
    if not m or info.is_dir():
        continue
    word, fn = m.group(1), m.group(2)
    d = os.path.join(out, word); os.makedirs(d, exist_ok=True)
    with z.open(info) as src, open(os.path.join(d, fn), 'wb') as dst:
        dst.write(src.read())
    n += 1
print("extracted", n)
