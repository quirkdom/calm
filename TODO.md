# TODOs

- [ ] Implement our own version of `mlx_lm.generate` for use in [mlx_backend.py](calmd/backend/mlx_backend.py).
  - Should be able to use `mlx_lm.generate_stream` just like `mlx_lm.generate`.
  - Should be able to verbose log stats to our own logger.
  - Should be able to intercept and early-exit when our custom stop tokens are encountered.
