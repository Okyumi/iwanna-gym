"""Discovery benchmark suites: registry, evaluator, diagnostics.

See docs/discovery_benchmark_contract.md and
docs/discovery_suite_report.md. Suite version: registry.SUITE_VERSION.
"""
from .registry import (SUITES, SUITE_VERSION, TaskSpec,  # noqa: F401
                       apply_task_anchors, binding_kwargs, load_registry,
                       load_witness, make_env, pending_ood, registry_hash,
                       suite_tasks, task_env_kwargs)
