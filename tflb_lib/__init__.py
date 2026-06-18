"""
tflb_lib — programmatic builder for Tableau Prep .tfl flow files.

A .tfl is a ZIP archive whose load-bearing member is `flow` (JSON). This
package exposes domain-agnostic primitives for reading, mutating, and
re-emitting that JSON without opening Tableau Prep Builder.

Public surface:
  build()                           — top-level: read .tfl, mutate, write .tfl
  make_script_node()                — Python-script step
  make_join_node()                  — inner-join step
  make_hyper_node()                 — .hyper output writer
  add_edge()                        — wire one node to another
  rewire_input_to_local_excel()     — swap a Google-Drive Excel input for a local one
  prune_nodes_by_name()             — drop named nodes + clean up dangling edges
  rewrite_script_paths()            — repoint Script nodes per a slot→agent map
  add_branch()                      — generic "tap an anchor node, attach a chain ending in a hyper writer"

The package is deliberately free of any domain assumptions (no SF1034
fields, no invoice schema, no slot vocabulary). Concrete domain logic
(e.g. "invoice flow's QA branch") is built on top of these primitives
in callers like the auto_refine package.
"""
from tflb_lib.builder import build  # noqa: F401
from tflb_lib import publishing  # noqa: F401
from tflb_lib.nodes import (  # noqa: F401
    add_edge,
    make_change_column_type_node,
    make_change_semantic_role_node,
    make_hyper_node,
    make_join_node,
    make_script_node,
    new_id,
)
from tflb_lib.inputs import rewire_input_to_local_excel  # noqa: F401
from tflb_lib.topology import (  # noqa: F401
    add_branch,
    prune_nodes_by_name,
    prune_to_keep_set,
    rewrite_script_paths,
)

__all__ = [
    "build",
    "make_script_node",
    "make_join_node",
    "make_hyper_node",
    "make_change_column_type_node",
    "make_change_semantic_role_node",
    "add_edge",
    "new_id",
    "rewire_input_to_local_excel",
    "prune_nodes_by_name",
    "prune_to_keep_set",
    "rewrite_script_paths",
    "add_branch",
    "publishing",
]
