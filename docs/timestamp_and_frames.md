# Timestamps and Frames

- Preserve source timestamps and their units and clock domains.
- Record monotonicity failures, duplicates, gaps, and resets.
- Every aligned value records its source timestamp, alignment method, allowed
  delta, actual sync error, and validity.
- Translation uses explicit distance units; rotation declares representation and
  quaternion ordering.
- Spatial values identify `frame_from`, `frame_to`, transform direction, and the
  calibration ID/version. Missing calibration must invalidate dependent results.
