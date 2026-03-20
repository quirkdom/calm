import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Mocking MLX and other dependencies that might fail on Linux
sys_modules = {
    "mlx": MagicMock(),
    "mlx.nn": MagicMock(),
    "mlx_lm": MagicMock(),
    "mlx_lm.tokenizer_utils": MagicMock(),
    "mlx_lm.generate": MagicMock(),
    "mlx_lm.models.cache": MagicMock(),
    "mlx_lm.sample_utils": MagicMock(),
}

with patch.dict("sys.modules", sys_modules):
    from calm.config import CalmdConfig
    from calmd.daemon import CalmdServer


class TestPrefillConformance(unittest.TestCase):
    def test_prefill_passed_to_backend(self):
        # Setup config with prefill enabled
        config = CalmdConfig(
            socket_path=Path("/tmp/test.sock"),
            model_path="test-model",
            use_fast_model=False,
            verbose=True,
            skip_warmup=True,
            idle_offload_secs=450,
            disable_prefix_cache=True,
            max_kv_size=4096,
            prefill_completion=True,
        )

        # Mock backend
        mock_backend = MagicMock()
        mock_backend.generate_completion.return_value = (
            "[TYPE: ANALYSIS]\n[RUNNABLE: NO]\n[SAFE: YES]\n[CONTENT]\n4\n[/CONTENT]"
        )
        mock_backend.last_metrics = {}

        server = CalmdServer(
            model_path="test-model", socket_path=Path("/tmp/test.sock"), verbose=True
        )
        server.config = config  # Force config
        server.backend = mock_backend
        server.smart_base_state = MagicMock()

        # Simulate a smart request
        req = {"query": "what is 2+2", "mode": "smart"}

        # We need to mock _backend_lock and other state
        server._backend_lock = MagicMock()

        response = server._answer_smart(req)

        # Verify prefill was passed
        args, kwargs = mock_backend.generate_completion.call_args
        self.assertEqual(kwargs.get("prefill"), "[TYPE:")
        self.assertEqual(response["content"], "4")


if __name__ == "__main__":
    unittest.main()
