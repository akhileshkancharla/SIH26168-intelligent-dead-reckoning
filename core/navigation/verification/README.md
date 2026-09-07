# S2 offline verification

This directory contains the accepted S2 replay driver, deterministic synthetic
fixtures, and independent NumPy oracle/checks imported by WP-03.1.

It is test/offline code. Production C++ must not import, bind, invoke, or
otherwise depend on Python. CMake/Eigen integration and runnable repository test
targets are intentionally deferred to issue #38.
