"""Synthetic source substitution and temporal leakage attacks."""
import copy
import unittest

from tools.dataset.feature_provenance import MINIMAL_BINDINGS, validate_minimal_window
from tools.dataset.feature_firewall import enforce_feature_window, FeatureFirewallError


def records():
    return [dict(name=name, value=0.01 if name == "imu.dt" else 1,
                 source=binding[0], field=binding[1], unit=binding[2], frame=binding[3],
                 epoch_ns=100, dependency_start_ns=90, dependency_end_ns=100,
                 available_at_ns=100, clock_id="synthetic") for name, binding in MINIMAL_BINDINGS.items()]


class ProvenanceTests(unittest.TestCase):
    def validate(self, rows):
        validate_minimal_window(rows, start_ns=0, end_ns=100, clock_id="synthetic")

    def test_complete_causal_sample(self):
        self.validate(records())

    def test_substitution_and_future_attacks(self):
        for patch in ({"source": "vehicle_CAN"}, {"name": "phone.gnss.speed"},
                      {"unit": "g"}, {"frame": "navigation"}, {"clock_id": "UTC"},
                      {"dependency_end_ns": 101}, {"dependency_start_ns": -1},
                      {"available_at_ns": 101}, {"value": float("nan")},
                      {"value": True}, {"epoch_ns": True}, {"value": 10**1000}):
            with self.subTest(patch=patch):
                rows = records()
                rows[0].update(patch)
                with self.assertRaises(ValueError):
                    self.validate(rows)

    def test_missing_duplicate_and_invalid_dt(self):
        for rows in (records()[:-1], records() + records(), []):
            with self.assertRaises(ValueError):
                self.validate(rows)
        rows = records()
        next(row for row in rows if row["name"] == "imu.dt")["value"] = 0.3
        with self.assertRaises(ValueError):
            self.validate(rows)

    def test_composed_gate_still_requires_active_reviewed_names(self):
        policy = {"schema_version": 1, "status": "ACTIVE", "runtime_allowed_features": list(MINIMAL_BINDINGS), "forbidden_labels": ["synthetic_label"]}
        kwargs = dict(start_ns=0, end_ns=100, clock_id="synthetic")
        enforce_feature_window(records(), policy, **kwargs)
        for change in ({"status": "TEMPLATE_PENDING_REVIEW"}, {"runtime_allowed_features": ["unrelated"]}):
            bad = copy.deepcopy(policy)
            bad.update(change)
            with self.assertRaises(FeatureFirewallError):
                enforce_feature_window(records(), bad, **kwargs)
        rows = records()
        rows[0]["source"] = "vehicle_CAN"
        with self.assertRaises(FeatureFirewallError):
            enforce_feature_window(rows, policy, **kwargs)
