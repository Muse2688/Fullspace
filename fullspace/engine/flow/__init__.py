"""Pluggable flow policies.

A flow policy decides *which* capabilities activate at each step given a query
vector over the manifold.

* ``DiscreteFlow`` — one capability per step (the LangGraph equivalent).
* ``FieldFlow``    — a neighbourhood per step (barrier-free parallelism).
"""

from fullspace.engine.flow.base import FlowPolicy
from fullspace.engine.flow.discrete import DiscreteFlow
from fullspace.engine.flow.field import FieldFlow
from fullspace.engine.flow.wavefront import WavefrontFlow

__all__ = ["FlowPolicy", "DiscreteFlow", "FieldFlow", "WavefrontFlow"]
