"""Tiny numpy-compatible fallback for constrained test environments."""

from __future__ import annotations

from typing import Iterable, Iterator

float32 = "float32"


class ndarray:
    """List-backed minimal ndarray used by tests when numpy is unavailable."""

    def __init__(self, values: Iterable[float]) -> None:
        self._values = [float(value) for value in values]

    def __getitem__(self, index: int) -> float:
        return self._values[index]

    def __setitem__(self, index: int, value: float) -> None:
        self._values[index] = float(value)

    def __iter__(self) -> Iterator[float]:
        return iter(self._values)

    def reshape(self, *shape: int) -> "ndarray":
        """Return self; dimensionality is not needed in fallback tests."""
        return self

    def astype(self, dtype: object) -> "ndarray":
        """Return self; fallback stores floats only."""
        return self

    def tolist(self) -> list[float]:
        """Return a Python list."""
        return list(self._values)


def zeros(shape: int | tuple[int, ...], dtype: object = None) -> ndarray:
    """Return a zero-filled fallback array."""
    length = shape if isinstance(shape, int) else _product(shape)
    return ndarray([0.0] * length)


def asarray(values: object) -> ndarray:
    """Coerce nested/scalar values to fallback ndarray."""
    if isinstance(values, ndarray):
        return values
    if isinstance(values, (list, tuple)):
        flat: list[float] = []
        for value in values:
            if isinstance(value, (list, tuple, ndarray)):
                flat.extend(asarray(value)._values)
            else:
                flat.append(float(value))
        return ndarray(flat)
    return ndarray([float(values)])


def _product(shape: tuple[int, ...]) -> int:
    total = 1
    for item in shape:
        total *= item
    return total
