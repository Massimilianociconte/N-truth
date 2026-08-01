"""Grafo tipizzato: merge delle fonti, conflitti e risoluzione delle unita."""

from ntruth.graph.builder import BuildResult, build_graph
from ntruth.graph.index import GraphIndex
from ntruth.graph.units import resolve_units

__all__ = ["BuildResult", "GraphIndex", "build_graph", "resolve_units"]
