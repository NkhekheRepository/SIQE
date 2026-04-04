"""
Slippage Models
Configurable slippage simulation for backtesting.
"""
import numpy as np
from abc import ABC, abstractmethod
from typing import Optional

from models.trade import SignalType


class SlippageModel(ABC):
    """Abstract base for slippage models."""

    @abstractmethod
    def apply(
        self,
        price: float,
        signal_type: SignalType,
        size: float,
        volume: float = 0.0,
        volatility: float = 0.02,
    ) -> float:
        """Return the simulated fill price after slippage."""
        pass


class FixedBPSSlippage(SlippageModel):
    """Fixed basis points slippage.
    Adds a constant spread regardless of trade size or market conditions.
    """

    def __init__(self, bps: float = 10.0):
        self.bps = bps

    def apply(
        self,
        price: float,
        signal_type: SignalType,
        size: float,
        volume: float = 0.0,
        volatility: float = 0.02,
    ) -> float:
        slip = price * (self.bps / 10000.0)
        if signal_type == SignalType.LONG:
            return price + slip
        return price - slip


class LinearSlippage(SlippageModel):
    """Linear slippage scaled by position size and volatility.
    Larger positions and higher volatility = more slippage.
    """

    def __init__(self, base_bps: float = 5.0, size_factor: float = 0.5):
        self.base_bps = base_bps
        self.size_factor = size_factor

    def apply(
        self,
        price: float,
        signal_type: SignalType,
        size: float,
        volume: float = 0.0,
        volatility: float = 0.02,
    ) -> float:
        size_penalty = self.size_factor * size / max(1.0, volume) if volume > 0 else 0
        effective_bps = self.base_bps + (size_penalty * 100) + (volatility * 500)
        slip = price * (effective_bps / 10000.0)

        if signal_type == SignalType.LONG:
            return price + slip
        return price - slip


class VolumeImpactSlippage(SlippageModel):
    """Volume-impact slippage based on square-root market impact model.
    slip ~ sigma * sqrt(size / volume)
    More realistic for larger orders.
    """

    def __init__(self, impact_factor: float = 0.1):
        self.impact_factor = impact_factor

    def apply(
        self,
        price: float,
        signal_type: SignalType,
        size: float,
        volume: float = 0.0,
        volatility: float = 0.02,
    ) -> float:
        if volume <= 0:
            volume = size * 100

        participation = min(1.0, size / volume)
        slip_pct = self.impact_factor * volatility * np.sqrt(participation)
        slip = price * slip_pct

        if signal_type == SignalType.LONG:
            return price + slip
        return price - slip


def create_slippage_model(model_type: str, **kwargs) -> SlippageModel:
    """Factory function to create a slippage model by name."""
    models = {
        "fixed_bps": FixedBPSSlippage,
        "linear": LinearSlippage,
        "volume_impact": VolumeImpactSlippage,
    }
    cls = models.get(model_type)
    if cls is None:
        raise ValueError(f"Unknown slippage model: {model_type}. Options: {list(models.keys())}")
    return cls(**kwargs)
