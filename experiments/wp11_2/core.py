"""Deterministic evidence-bounded ridge training pipeline."""
import argparse,csv,hashlib,json,math,platform
from dataclasses import dataclass
from pathlib import Path

VERSION="wp11.2-v1"
DEFAULT_FEATURES=("accelerometer_x","accelerometer_y","accelerometer_z","gyroscope_x","gyroscope_y","gyroscope_z","gravity_x","gravity_y","gravity_z","orientation_x","orientation_y","orientation_z","speed_mps")
FORBIDDEN=("latitude","longitude","gnss","gps","ground_truth","target","label","position")

@dataclass(frozen=True)
class TrainingConfig:
    features:tuple[str,...]
    target:str
    ridge:float=1e-6
    train_fraction:float=.8
    def validate(self):
        if not self.features or len(set(self.features))!=len(self.features): raise ValueError("features must be non-empty and unique")
        if self.target in self.features: raise ValueError("target cannot also be a feature")
        if not 0<self.train_fraction<1: raise ValueError("train_fraction must be between 0 and 1")
        if not math.isfinite(self.ridge) or self.ridge<0: raise ValueError("invalid ridge")
        bad=[x for x in self.features if any(t in x.lower() for t in FORBIDDEN)]
        if bad: raise ValueError("forbidden/leaky features: "+", ".join(bad))

def load(path,config):
    config.validate()
    with path.open(encoding="utf-8-sig",newline="") as h:
        reader=csv.DictReader(h); required=set(config.features)|{config.target}
        missing=sorted(required-set(reader.fieldnames or ()))
        if missing: raise ValueError("missing columns: "+", ".join(missing))
        rows=[]
        for n,row in enumerate(reader,2):
            try: sample=[float(row[x]) for x in config.features]; target=float(row[config.target])
            except (TypeError,ValueError) as e: raise ValueError(f"non-numeric value on line {n}") from e
            if not all(math.isfinite(x) for x in (*sample,target)): raise ValueError(f"non-finite value on line {n}")
            rows.append((sample,target))
    if len(rows)<3: raise ValueError("at least three rows are required")
    return rows

def solve(a,b):
    n=len(b); m=[a[i][:]+[b[i]] for i in range(n)]
    for c in range(n):
        p=max(range(c,n),key=lambda r:abs(m[r][c]))
        if abs(m[p][c])<1e-15: raise ValueError("singular system; increase ridge")
        m[c],m[p]=m[p],m[c]; d=m[c][c]; m[c]=[x/d for x in m[c]]
        for r in range(n):
            if r!=c:
                f=m[r][c]; m[r]=[x-f*y for x,y in zip(m[r],m[c])]
    return [m[i][-1] for i in range(n)]

def fit(rows,ridge):
    n=len(rows[0][0])+1; a=[[0.]*n for _ in range(n)]; b=[0.]*n
    for features,target in rows:
        x=[1.,*features]
        for i in range(n):
            b[i]+=x[i]*target
            for j in range(n): a[i][j]+=x[i]*x[j]
    for i in range(1,n): a[i][i]+=ridge
    return solve(a,b)

