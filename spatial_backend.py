"""Real CPU ovspatialquery integration; no grid collision fallback."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import time

REPO = Path(os.environ.get("OVSPATIALQUERY_REPO", Path(__file__).resolve().parent.parent / "ovspatialquery-prototype"))
sys.path.insert(0, str(REPO / "python" / "src"))

import numpy as np
from ovspatialquery import Library, ContextConfig, PopulationConfig, DLPackLease, OverlapQuery, OrientedBox, Device, raw
from ovspatialquery.explicit import BoxDefinitions, ExplicitInstances, GeometryDefinitionRef


def lease(values, dtype, shape=None):
    array = np.asarray(values, dtype=dtype)
    if shape is not None:
        array = array.reshape(shape)
    return DLPackLease.from_dlpack(np.ascontiguousarray(array))


class SpatialBoard:
    """One shared box definition, one population of settled blocks."""

    def __init__(self):
        default = REPO / "_build/bootstrap/native-stable/install/bin/ovspatialquery.dll"
        if sys.platform != "win32":
            default = REPO / "_build/bootstrap/native-stable/install/lib/libovspatialquery.so"
        self.library_path = Path(os.environ.get("OVSPATIALQUERY_LIBRARY", default))
        self.library = Library.open(self.library_path, require_explicit=True)
        self.context = self.library.context(ContextConfig(operation_capacity=8, max_cpu_concurrency=1, host_byte_budget=64 << 20))
        self.adapter = self.context.explicit()
        self.definition = GeometryDefinitionRef(raw.GeometryType.BOX, 1)
        self.population = None
        self.published = {}
        self.ordinal = 0
        self.queries = 0
        self.query_ms = 0.0
        self.last_result = "Ready"
        self.last_hit = None
        self.publication_ms = 0.0
        self.closed = False
        try:
            self.finish(self.adapter.register_boxes(BoxDefinitions(lease([1], np.uint64), lease([[0.5, 0.5, 0.15]], np.float64))))
            self.population = self.adapter.create_population(PopulationConfig(retained_ordinal_capacity=1))
            self.publish({})
        except Exception:
            if self.population is not None:
                self.population.close()
            self.context.close()
            self.library.close()
            raise

    @staticmethod
    def finish(operation, publication=False):
        try:
            if operation.wait() is not raw.OpState.COMPLETED:
                raise RuntimeError(f"Spatial operation failed: {operation.status()}")
            return operation.fetch_population_update() if publication else None
        finally:
            operation.close()

    @staticmethod
    def instances(rows):
        rows = list(rows)
        count = len(rows)
        return ExplicitInstances(
            object_values=lease([row[0] for row in rows], np.uint64),
            geometry_types=lease([int(raw.GeometryType.BOX)] * count, np.int32),
            geometry_values=lease([1] * count, np.uint64),
            translations=lease([[x + 0.5, 19.5 - y, 0.0] for _, x, y in rows], np.float64, (count, 3)),
            rotations_xyzw=lease([[0.0, 0.0, 0.0, 1.0]] * count, np.float64, (count, 4)),
        )

    def publish(self, board):
        current = {block[0]: position for position, block in board.items()}
        changed = [(identity, *position) for identity, position in current.items() if self.published.get(identity) != position]
        removed = [identity for identity in self.published if identity not in current]
        if self.ordinal and not changed and not removed:
            return
        start = time.perf_counter()
        next_ordinal = self.ordinal + 1
        if self.ordinal == 0:
            operation = self.population.enqueue_set(next_ordinal, self.instances(changed))
        else:
            operation = self.population.enqueue_update(self.ordinal, next_ordinal, self.instances(changed), lease(removed, np.uint64))
        result = self.finish(operation, publication=True)
        if result.published_ordinal != next_ordinal or result.object_count != len(current):
            raise RuntimeError("Published board does not match the requested scene.")
        self.ordinal = next_ordinal
        self.published = current
        self.publication_ms = (time.perf_counter() - start) * 1000

    def occupied(self, x, y):
        start = time.perf_counter()
        # Stored blocks meet at cell boundaries. The inset makes face-touching
        # neighbours legal while a query in an occupied cell still intersects.
        result = self.population.target.overlap_any(OverlapQuery(
            OrientedBox(center=(x + 0.5, 19.5 - y, 0.0), rotation_xyzw=(0.0, 0.0, 0.0, 1.0), half_extents=(0.49, 0.49, 0.14)),
            precision=raw.QueryPrecision.EXACT,
        ))
        self.query_ms = (time.perf_counter() - start) * 1000
        self.queries += 1
        if result.source_ordinal != self.ordinal:
            raise RuntimeError("Query read an unexpected scene version.")
        self.last_hit = result.hit.object_id if result.hit else None
        self.last_result = "Occupied" if result.hit else "Clear"
        return result.hit is not None

    def stats(self):
        return dict(engine="ovspatialquery", version=".".join(map(str, self.library.version)), device="CPU",
                    ordinal=self.ordinal, objects=len(self.published), queries=self.queries,
                    query_ms=round(self.query_ms, 3), publication_ms=round(self.publication_ms, 3),
                    memory_bytes=self.context.memory_usage(Device()), last_result=self.last_result,
                    last_hit=self.last_hit)

    def close(self):
        if self.closed:
            return
        self.population.close()
        self.adapter.destroy_definition(self.definition)
        self.context.close()
        self.library.close()
        self.closed = True
