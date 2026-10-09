"""Affiliate platform export (conversions by platform id or code). Record facts only: conversions, last conversion."""
from __future__ import annotations

from pathlib import Path

from . import Batch
from .csv_source import _rows


def read(path) -> Batch:
    return Batch(system="platform", conversions=_rows(Path(path)))
