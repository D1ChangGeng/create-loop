#!/usr/bin/env python3
"""Small fail-closed JSON Schema 2020-12 subset used by create-loop v2.

The runtime intentionally implements only keywords present in the bundled v2
schemas. CI may additionally compare results with the full jsonschema package.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

SUPPORTED = {
    "$schema", "$id", "$defs", "$ref", "title", "description", "type",
    "const", "enum", "required", "properties", "additionalProperties",
    "items", "minItems", "maxItems", "uniqueItems", "minLength", "minimum", "pattern",
    "format", "if", "then", "else", "allOf",
}
SCHEMA_CONTAINER_KEYWORDS = {"$defs", "properties"}
SCHEMA_SINGLE_KEYWORDS = {"additionalProperties", "items", "if", "then", "else"}
SCHEMA_ARRAY_KEYWORDS = {"allOf"}

RFC3339_DATE_TIME = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]+)?"
    r"(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])$"
)


class SchemaError(ValueError):
    pass


_CHECKED_SCHEMA_FILES: dict[Path, tuple[bytes, dict[str, Any]]] = {}


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant {value!r}")


def check_schema(
    schema: dict[str, Any],
    *,
    root: dict[str, Any] | None = None,
    path: str = "$schema",
) -> None:
    """Validate every reachable subschema, including definitions unused by an instance."""
    if not isinstance(schema, dict):
        raise SchemaError(f"schema must be an object at {path}")
    root = schema if root is None else root
    unknown = set(schema) - SUPPORTED
    if unknown:
        raise SchemaError(f"unsupported schema keyword(s) at {path}: {sorted(unknown)}")
    if "$ref" in schema:
        if not isinstance(schema["$ref"], str):
            raise SchemaError(f"$ref must be a string at {path}")
        _resolve_ref(root, schema["$ref"])
    for keyword in SCHEMA_CONTAINER_KEYWORDS:
        if keyword not in schema:
            continue
        children = schema[keyword]
        if not isinstance(children, dict):
            raise SchemaError(f"{keyword} must be an object at {path}")
        for name, child in children.items():
            check_schema(child, root=root, path=f"{path}.{keyword}.{name}")
    for keyword in SCHEMA_SINGLE_KEYWORDS:
        child = schema.get(keyword)
        if isinstance(child, dict):
            check_schema(child, root=root, path=f"{path}.{keyword}")
        elif child is not None and keyword not in {"additionalProperties"}:
            raise SchemaError(f"{keyword} must be a schema at {path}")
        elif keyword == "additionalProperties" and child not in {None, True, False}:
            raise SchemaError(f"additionalProperties must be a boolean or schema at {path}")
    for keyword in SCHEMA_ARRAY_KEYWORDS:
        if keyword not in schema:
            continue
        children = schema[keyword]
        if not isinstance(children, list):
            raise SchemaError(f"{keyword} must be an array at {path}")
        for index, child in enumerate(children):
            check_schema(child, root=root, path=f"{path}.{keyword}[{index}]")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle, parse_constant=_reject_json_constant)


def _resolve_ref(root: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise SchemaError(f"unsupported external $ref: {ref}")
    value: Any = root
    for token in ref[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or token not in value:
            raise SchemaError(f"unresolved $ref: {ref}")
        value = value[token]
    if not isinstance(value, dict):
        raise SchemaError(f"$ref does not resolve to a schema: {ref}")
    return value


def _type_ok(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and (not isinstance(value, float) or math.isfinite(value))
        ),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, False)


def _validate(
    instance: Any,
    schema: dict[str, Any],
    *,
    root: dict[str, Any],
    path: str,
) -> list[str]:
    if "$ref" in schema:
        return _validate(instance, _resolve_ref(root, schema["$ref"]), root=root, path=path)

    errors: list[str] = []
    for subschema in schema.get("allOf", []):
        if not isinstance(subschema, dict):
            raise SchemaError(f"allOf entries must be schemas at {path}")
        errors.extend(_validate(instance, subschema, root=root, path=path))
    if "if" in schema:
        condition = schema["if"]
        if not isinstance(condition, dict):
            raise SchemaError(f"if must be a schema at {path}")
        branch = schema.get("then") if not _validate(instance, condition, root=root, path=path) else schema.get("else")
        if branch is not None:
            if not isinstance(branch, dict):
                raise SchemaError(f"conditional branch must be a schema at {path}")
            errors.extend(_validate(instance, branch, root=root, path=path))
    expected = schema.get("type")
    if expected is not None:
        expected_types = expected if isinstance(expected, list) else [expected]
        if not all(isinstance(item, str) for item in expected_types):
            raise SchemaError(f"invalid type declaration at {path}")
        if not any(_type_ok(instance, item) for item in expected_types):
            return [f"{path}: expected type {expected!r}"]
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected constant {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} is not one of {schema['enum']!r}")

    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise SchemaError(f"properties must be an object at {path}")
        for name in schema.get("required", []):
            if name not in instance:
                errors.append(f"{path}: missing required property {name!r}")
        additional = schema.get("additionalProperties", True)
        for name, value in instance.items():
            if name in properties:
                errors.extend(_validate(value, properties[name], root=root, path=f"{path}.{name}"))
            elif additional is False:
                errors.append(f"{path}: unexpected property {name!r}")
            elif isinstance(additional, dict):
                errors.extend(_validate(value, additional, root=root, path=f"{path}.{name}"))

    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            errors.append(f"{path}: expected at least {schema['minItems']} item(s)")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: expected at most {schema['maxItems']} item(s)")
        if schema.get("uniqueItems"):
            encoded = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in instance]
            if len(encoded) != len(set(encoded)):
                errors.append(f"{path}: items must be unique")
        if "items" in schema:
            for index, item in enumerate(instance):
                errors.extend(_validate(item, schema["items"], root=root, path=f"{path}[{index}]"))

    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            errors.append(f"{path}: string is shorter than {schema['minLength']}")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            errors.append(f"{path}: string does not match {schema['pattern']!r}")
        if schema.get("format") == "date-time":
            try:
                if RFC3339_DATE_TIME.fullmatch(instance) is None:
                    raise ValueError
                parsed = datetime.fromisoformat(instance.replace("Z", "+00:00"))
                if parsed.utcoffset() is None:
                    raise ValueError
            except ValueError:
                errors.append(f"{path}: invalid RFC 3339 date-time")
        elif "format" in schema and schema["format"] != "date-time":
            raise SchemaError(f"unsupported format {schema['format']!r} at {path}")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: value is below minimum {schema['minimum']}")
    return errors


def validate(
    instance: Any,
    schema: dict[str, Any],
    *,
    root: dict[str, Any] | None = None,
    path: str = "$",
) -> list[str]:
    root = schema if root is None else root
    if root is schema:
        check_schema(schema)
    return _validate(instance, schema, root=root, path=path)


def validate_schema_file(instance: Any, schema_path: Path, *, path: str = "$") -> list[str]:
    """Validate against a checked schema snapshot, reloading on any byte change."""
    absolute = schema_path.absolute()
    try:
        raw = schema_path.read_bytes()
    except OSError as exc:
        raise SchemaError(f"cannot read schema {schema_path}: {exc}") from exc
    fingerprint = hashlib.sha256(raw).digest()
    cached = _CHECKED_SCHEMA_FILES.get(absolute)
    if cached is None or cached[0] != fingerprint:
        try:
            schema = json.loads(raw.decode("utf-8"), parse_constant=_reject_json_constant)
        except (UnicodeError, ValueError) as exc:
            raise SchemaError(f"cannot parse schema {schema_path}: {exc}") from exc
        if not isinstance(schema, dict):
            raise SchemaError(f"schema must be an object at {schema_path}")
        check_schema(schema)
        _CHECKED_SCHEMA_FILES[absolute] = (fingerprint, schema)
    else:
        schema = cached[1]
    return _validate(instance, schema, root=schema, path=path)


def validate_file(instance_path: Path, schema_path: Path) -> list[str]:
    return validate_schema_file(load_json(instance_path), schema_path)
