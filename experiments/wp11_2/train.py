import argparse,hashlib,json,math,platform
from pathlib import Path
from experiments.wp11_2.core import DEFAULT_FEATURES,TrainingConfig,fit,load

def metrics(rows,w):
    e=[w[0]+sum(a*b for a,b in zip(w[1:],x))-y for x,y in rows]
    return {"mae":sum(map(abs,e))/len(e),"rmse":math.sqrt(sum(x*x for x in e)/len(e))}

def train(path,config):
    rows=load(path,config); s=max(1,min(len(rows)-1,int(len(rows)*config.train_fraction)))
    tr,va=rows[:s],rows[s:]; w=fit(tr,config.ridge)
    return {"schema_version":1,"pipeline_version":VERSION,"status":"exploratory-not-promoted","input":{"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"rows":len(rows)},"split":{"method":"chronological","train_rows":s,"validation_rows":len(va)},"model":{"kind":"ridge_linear_regression","features":list(config.features),"target":config.target,"ridge":config.ridge,"intercept":w[0],"coefficients":w[1:]},"metrics":{"train":metrics(tr,w),"validation":metrics(va,w)},"runtime":{"python":platform.python_version()},"limitations":["Exploratory offline evidence only; not a promotion claim.","Holdout does not replace WP-11.3 validation.","Cannot overwrite navigation-core state."]}

def main():
    p=argparse.ArgumentParser(); p.add_argument("input",type=Path); p.add_argument("output",type=Path); p.add_argument("--target",required=True); p.add_argument("--features",nargs="+",default=list(DEFAULT_FEATURES)); p.add_argument("--ridge",type=float,default=1e-6); p.add_argument("--train-fraction",type=float,default=.8); a=p.parse_args()
    result=train(a.input,TrainingConfig(tuple(a.features),a.target,a.ridge,a.train_fraction)); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
if __name__=="__main__": main()
