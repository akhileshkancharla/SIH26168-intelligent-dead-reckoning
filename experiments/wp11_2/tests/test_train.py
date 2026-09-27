import csv,json,tempfile,unittest
from pathlib import Path
from experiments.wp11_2.train import TrainingConfig,train

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"synthetic.csv"
        with self.path.open("w",newline="",encoding="utf-8") as h:
            w=csv.DictWriter(h,fieldnames=["accelerometer_x","speed_mps","residual_m"]); w.writeheader()
            for i in range(20): w.writerow({"accelerometer_x":i/10,"speed_mps":i,"residual_m":2+3*i})
        self.config=TrainingConfig(("accelerometer_x","speed_mps"),"residual_m",1e-3)
    def test_deterministic(self):
        a=json.dumps(train(self.path,self.config),sort_keys=True,allow_nan=False)
        b=json.dumps(train(self.path,self.config),sort_keys=True,allow_nan=False)
        self.assertEqual(a,b)
    def test_evidence_bounded(self):
        a=train(self.path,self.config)
        self.assertEqual(a["status"],"exploratory-not-promoted"); self.assertEqual(a["split"]["method"],"chronological"); self.assertEqual(a["split"]["train_rows"],16)
    def test_rejects_leakage(self):
        with self.assertRaisesRegex(ValueError,"forbidden/leaky"):
            train(self.path,TrainingConfig(("accelerometer_x","gnss_latitude"),"residual_m"))
    def test_target_cannot_be_feature(self):
        with self.assertRaisesRegex(ValueError,"target cannot"):
            train(self.path,TrainingConfig(("residual_m",),"residual_m"))

if __name__=="__main__": unittest.main()
