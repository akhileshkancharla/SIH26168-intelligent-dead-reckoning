# Deterministic analyzer fixture

`deterministic_session` deliberately contains one duplicate sensor timestamp,
one non-monotonic sensor timestamp, and one large gap. It also contains two GPS
provider fixes, screen/thermal state, and a coarse one-hour battery change. The
fixture is synthetic and is not physical-device evidence.
