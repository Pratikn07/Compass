"""Compatibility imports for the owner-scoped Compass warehouse."""

from compass.storage.warehouse import Warehouse as Store
from compass.storage.warehouse import make_client, make_warehouse

__all__ = ["Store", "make_client", "make_warehouse"]
