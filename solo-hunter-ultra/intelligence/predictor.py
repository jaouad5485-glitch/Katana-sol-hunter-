"""ONNX Runtime predictor with rule-based fallback."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import structlog

LOGGER = structlog.get_logger(__name__)


class OnnxPredictor:
    """Loads an ONNX model, warms inference, and supports hot swapping."""

    def __init__(self, model_path: str | None = None) -> None:
        self.model_path = model_path
        self._session = None

    async def start(self) -> None:
        """Load and warm the model when available."""
        if self.model_path and Path(self.model_path).exists():
            import onnxruntime as ort
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            self._session = ort.InferenceSession(self.model_path, providers=providers)
            dummy = np.zeros((1, 50), dtype=np.float32)
            for _ in range(10):
                self.predict(dummy[0])
        else:
            LOGGER.warning("onnx_model_missing_using_fallback", model_path=self.model_path)

    def predict(self, features: np.ndarray) -> float:
        """Return a probability from 0.0 to 1.0."""
        if self._session is None:
            liquidity_score = min(float(features[0]) / 10_000.0, 1.0)
            risk_penalty = min(float(features[9]) * 0.2, 0.5)
            return max(0.0, min(1.0, 0.55 + liquidity_score * 0.35 - risk_penalty))
        input_name = self._session.get_inputs()[0].name
        output = self._session.run(None, {input_name: features.reshape(1, 50).astype(np.float32)})
        return float(np.asarray(output[0]).reshape(-1)[0])

    async def reload(self, model_path: str) -> None:
        """Hot-swap the model without restarting the bot."""
        self.model_path = model_path
        await self.start()
