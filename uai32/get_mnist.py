#!/usr/bin/env python3
"""Download MNIST (70,000 handwritten digits) and write it in uAI-32's text format.

  python3 get_mnist.py            -> data/mnist14_train.txt (60,000 rows), data/mnist14_test.txt (10,000 rows)
  python3 get_mnist.py --full     -> data/mnist28_*.txt with all 784 pixels instead of 14x14

By default each 28x28 image is average-pooled 2x2 to 14x14 = 196 features (integers 0..255),
which keeps the text files and the training time small.  Files are not committed (see .gitignore).
Source: Yann LeCun / Corinna Cortes / Christopher Burges, MNIST database (CC BY-SA 3.0),
mirrored at storage.googleapis.com/cvdf-datasets/mnist/ and ossci-datasets.s3.amazonaws.com/mnist/.
"""
import gzip, os, struct, sys, urllib.request
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data")
MIRRORS = ["https://storage.googleapis.com/cvdf-datasets/mnist/", "https://ossci-datasets.s3.amazonaws.com/mnist/"]
FILES = {"train": ("train-images-idx3-ubyte.gz", "train-labels-idx1-ubyte.gz"),
         "test": ("t10k-images-idx3-ubyte.gz", "t10k-labels-idx1-ubyte.gz")}

def fetch(name):
    path = os.path.join(OUT, name)
    if not os.path.exists(path):
        for m in MIRRORS:
            try:
                print("downloading", m + name); urllib.request.urlretrieve(m + name, path); break
            except Exception as e:  # try the next mirror
                print("  failed:", e)
        else:
            sys.exit("could not download " + name)
    return gzip.open(path).read()

def main(full):
    os.makedirs(OUT, exist_ok=True)
    for split, (img, lab) in FILES.items():
        raw = fetch(img); magic, n, h, w = struct.unpack(">IIII", raw[:16])
        X = np.frombuffer(raw[16:], dtype=np.uint8).reshape(n, h, w)
        y = np.frombuffer(fetch(lab)[8:], dtype=np.uint8)
        if not full:  # 2x2 average pooling, 28x28 -> 14x14
            X = X.reshape(n, 14, 2, 14, 2).mean(axis=(2, 4)).round().astype(np.uint8)
        X = X.reshape(n, -1)
        name = f"mnist{X.shape[1] and (28 if full else 14)}_{split}.txt"
        with open(os.path.join(OUT, name), "w") as f:
            for row, lab in zip(X, y):
                f.write(" ".join(map(str, row.tolist())) + f" {lab}\n")
        print(f"{name}: {n} rows, {X.shape[1]} features")

if __name__ == "__main__":
    main("--full" in sys.argv)
