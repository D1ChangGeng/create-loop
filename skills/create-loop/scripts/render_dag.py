#!/usr/bin/env python3
"""Render a loop.plan as a Mermaid graph and a Graphviz DOT digraph.

Prints two copy-pasteable blocks to stdout:
  1. A fenced ```mermaid graph TD ... ``` block (subgraphs as Mermaid
     `subgraph` blocks; approval nodes get a distinct shape).
  2. A `digraph loop_plan { ... }` Graphviz DOT block.

Nodes are labelled id + short title + status; edges run from each requires
dependency to the node. Exit 0 always (rendering, not validation).
"""
from __future__ import annotations

import argparse
import sys
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - environment guard
    print(
        "error: PyYAML is required but not importable. Install with: pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(2)


def load_yaml(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except FileNotFoundError:
        print(f"error: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    except (yaml.YAMLError, OSError) as exc:
        print(f"error: could not parse YAML {path}: {exc}", file=sys.stderr)
        sys.exit(2)


def sanitize(node_id: str) -> str:
    """Make an id safe for Mermaid/DOT node identifiers."""
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in node_id)


def short(text: Any, limit: int = 40) -> str:
    """Trim a title to a short, punctuation-safe label fragment."""
    s = str(text or "").replace('"', "'").replace("[", "(").replace("]", ")")
    s = s.replace("\n", " ").replace("|", "/").replace("{", "(").replace("}", ")")
    return s if len(s) <= limit else s[: limit - 1] + "\u2026"


def mermaid_label(node: dict[str, Any]) -> str:
    return f"{node.get('id')}: {short(node.get('title'))} [{node.get('status')}]"


def emit_mermaid_nodes(nodes: list[Any], out: list[str], indent: str) -> None:
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        if not isinstance(nid, str):
            continue
        sid = sanitize(nid)
        label = mermaid_label(node)
        kind = node.get("kind")
        # Distinguish node kinds by shape: approval as stadium, others as boxes.
        if kind == "approval":
            out.append(f'{indent}{sid}(["{label}"])')
        elif kind in ("branch", "join"):
            out.append(f'{indent}{sid}{{{{"{label}"}}}}')
        else:
            out.append(f'{indent}{sid}["{label}"]')
        sub = node.get("subgraph")
        if isinstance(sub, dict) and isinstance(sub.get("nodes"), list) and sub["nodes"]:
            out.append(f'{indent}subgraph sg_{sid}["subgraph: {sid}"]')
            emit_mermaid_nodes(sub["nodes"], out, indent + "  ")
            out.append(f"{indent}end")
        for cid, ref in child_loop_refs(node):
            out.append(f'{indent}{cid}[/"child_loop {short(ref.get("loop_id"))}"/]')


def child_loop_refs(node: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Yield (sanitized_id, ref) for each child_loop reference on a node."""
    refs: list[tuple[str, dict[str, Any]]] = []
    node_sid = sanitize(str(node.get("id")))
    for idx, ref in enumerate(node.get("child_loops") or []):
        if isinstance(ref, dict):
            refs.append((f"{node_sid}__cl{idx}", ref))
    return refs


def emit_mermaid_edges(nodes: list[Any], out: list[str]) -> None:
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        if not isinstance(nid, str):
            continue
        for dep in node.get("requires") or []:
            if isinstance(dep, str):
                out.append(f"  {sanitize(dep)} --> {sanitize(nid)}")
        sub = node.get("subgraph")
        if isinstance(sub, dict) and isinstance(sub.get("nodes"), list):
            emit_mermaid_edges(sub["nodes"], out)
        for cid, _ref in child_loop_refs(node):
            out.append(f"  {sanitize(nid)} -.-> {cid}")


def render_mermaid(plan: dict[str, Any]) -> str:
    nodes = plan.get("nodes") or []
    out: list[str] = ["```mermaid", "graph TD"]
    emit_mermaid_nodes(nodes, out, "  ")
    emit_mermaid_edges(nodes, out)
    out.append("```")
    return "\n".join(out)


def emit_dot_nodes(nodes: list[Any], out: list[str], cluster_prefix: str = "") -> None:
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        if not isinstance(nid, str):
            continue
        sid = sanitize(nid)
        label = f"{nid}\\n{short(node.get('title'))}\\n[{node.get('status')}]"
        kind = node.get("kind")
        if kind == "approval":
            shape = "shape=ellipse, style=filled, fillcolor=lightyellow"
        elif kind in ("branch", "join"):
            shape = "shape=diamond"
        else:
            shape = "shape=box"
        out.append(f'  "{sid}" [label="{label}", {shape}];')
        sub = node.get("subgraph")
        if isinstance(sub, dict) and isinstance(sub.get("nodes"), list) and sub["nodes"]:
            out.append(f'  subgraph "cluster_{sid}" {{')
            out.append(f'    label="subgraph: {sid}";')
            emit_dot_nodes(sub["nodes"], out, cluster_prefix)
            out.append("  }")
        for cid, ref in child_loop_refs(node):
            cl_label = f"child_loop\\n{short(ref.get('loop_id'))}"
            out.append(
                f'  "{cid}" [label="{cl_label}", shape=note, style=dashed];'
            )


def emit_dot_edges(nodes: list[Any], out: list[str]) -> None:
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        if not isinstance(nid, str):
            continue
        for dep in node.get("requires") or []:
            if isinstance(dep, str):
                out.append(f'  "{sanitize(dep)}" -> "{sanitize(nid)}";')
        sub = node.get("subgraph")
        if isinstance(sub, dict) and isinstance(sub.get("nodes"), list):
            emit_dot_edges(sub["nodes"], out)
        for cid, _ref in child_loop_refs(node):
            out.append(f'  "{sanitize(nid)}" -> "{cid}" [style=dashed];')


def render_dot(plan: dict[str, Any]) -> str:
    nodes = plan.get("nodes") or []
    out: list[str] = ["digraph loop_plan {", "  rankdir=TB;", "  node [fontsize=10];"]
    emit_dot_nodes(nodes, out)
    emit_dot_edges(nodes, out)
    out.append("}")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a loop.plan as Mermaid + DOT.")
    parser.add_argument("file", help="Path to the loop.plan YAML.")
    args = parser.parse_args()

    plan = load_yaml(args.file)
    if not isinstance(plan, dict):
        print("error: loop.plan document is not a mapping", file=sys.stderr)
        return 2

    print(render_mermaid(plan))
    print()
    print(render_dot(plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
