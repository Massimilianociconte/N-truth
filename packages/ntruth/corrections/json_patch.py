"""Applicatore atomico RFC 6902 con JSON Pointer RFC 6901.

Il modulo e deliberatamente indipendente dagli schemi scientifici: applica una
patch a un documento JSON e non interpreta il significato biologico dei campi.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

type PatchOp = Literal["add", "remove", "replace", "move", "copy", "test"]

_OPS: frozenset[str] = frozenset({"add", "remove", "replace", "move", "copy", "test"})
_VALUE_OPS: frozenset[str] = frozenset({"add", "replace", "test"})
_FROM_OPS: frozenset[str] = frozenset({"move", "copy"})


class JsonPatchError(ValueError):
    """Patch malformata o non applicabile al documento corrente."""


class JsonPatchTestFailed(JsonPatchError):
    """Una operazione ``test`` non corrisponde al valore corrente."""


@dataclass(frozen=True, slots=True)
class JsonPatchOperation:
    """Operazione RFC 6902 immutabile e JSON-safe."""

    op: PatchOp
    path: str
    from_path: str | None
    _value_json: str | None
    has_value: bool

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> JsonPatchOperation:
        op = payload.get("op")
        path = payload.get("path")
        if not isinstance(op, str) or op not in _OPS:
            raise JsonPatchError(f"operazione JSON Patch sconosciuta: {op!r}")
        if not isinstance(path, str):
            raise JsonPatchError(f"{op}: 'path' deve essere una stringa")
        parse_pointer(path)

        from_path = payload.get("from")
        if op in _FROM_OPS:
            if not isinstance(from_path, str):
                raise JsonPatchError(f"{op}: campo 'from' obbligatorio")
            parse_pointer(from_path)
        elif from_path is not None and not isinstance(from_path, str):
            raise JsonPatchError(f"{op}: 'from' deve essere una stringa")

        has_value = "value" in payload
        if op in _VALUE_OPS and not has_value:
            raise JsonPatchError(f"{op}: campo 'value' obbligatorio")
        value_json = _canonical_json(payload.get("value")) if has_value else None

        return cls(
            op=op,  # type: ignore[arg-type]
            path=path,
            from_path=from_path if isinstance(from_path, str) else None,
            _value_json=value_json,
            has_value=has_value,
        )

    @property
    def value(self) -> Any:
        if not self.has_value:
            raise JsonPatchError(f"{self.op}: operazione priva di value")
        return json.loads(self._value_json or "null")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"op": self.op, "path": self.path}
        if self.from_path is not None:
            payload["from"] = self.from_path
        if self.has_value:
            payload["value"] = self.value
        return payload


def parse_json_patch(
    patch: Iterable[Mapping[str, Any] | JsonPatchOperation],
) -> tuple[JsonPatchOperation, ...]:
    """Valida e congela una sequenza di operazioni RFC 6902."""

    operations: list[JsonPatchOperation] = []
    for index, payload in enumerate(patch):
        try:
            if isinstance(payload, JsonPatchOperation):
                operation = payload
            elif isinstance(payload, Mapping):
                operation = JsonPatchOperation.from_mapping(payload)
            else:
                raise JsonPatchError("ogni operazione deve essere un oggetto JSON")
        except (JsonPatchError, TypeError) as exc:
            raise JsonPatchError(f"operazione {index}: {exc}") from exc
        operations.append(operation)
    return tuple(operations)


def apply_json_patch(
    document: Any,
    patch: Iterable[Mapping[str, Any] | JsonPatchOperation],
) -> Any:
    """Applica l'intera patch in modo atomico, senza mutare ``document``.

    Se una singola operazione fallisce viene sollevato ``JsonPatchError`` e il
    chiamante conserva il documento originale intatto.
    """

    current = _json_clone(document)
    operations = parse_json_patch(patch)
    for index, operation in enumerate(operations):
        try:
            current = _apply_operation(current, operation)
        except JsonPatchError as exc:
            raise JsonPatchError(
                f"operazione {index} ({operation.op} {operation.path!r}): {exc}"
            ) from exc
    return current


def parse_pointer(pointer: str) -> tuple[str, ...]:
    """Decodifica un JSON Pointer RFC 6901 e rifiuta escape non validi."""

    if pointer == "":
        return ()
    if not pointer.startswith("/"):
        raise JsonPatchError(f"JSON Pointer deve essere vuoto o iniziare con '/': {pointer!r}")
    return tuple(_decode_token(token) for token in pointer[1:].split("/"))


def _decode_token(token: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(token):
        char = token[index]
        if char != "~":
            out.append(char)
            index += 1
            continue
        if index + 1 >= len(token) or token[index + 1] not in {"0", "1"}:
            raise JsonPatchError(f"escape JSON Pointer non valido in {token!r}")
        out.append("~" if token[index + 1] == "0" else "/")
        index += 2
    return "".join(out)


def _apply_operation(document: Any, operation: JsonPatchOperation) -> Any:
    path = parse_pointer(operation.path)

    if operation.op == "test":
        current = _get(document, path)
        if not _json_equal(current, operation.value):
            raise JsonPatchTestFailed(
                f"test fallito: atteso {operation.value!r}, trovato {current!r}"
            )
        return document

    if operation.op == "add":
        return _add(document, path, operation.value)
    if operation.op == "remove":
        return _remove(document, path)[0]
    if operation.op == "replace":
        _get(document, path)
        return _replace(document, path, operation.value)

    if operation.from_path is None:  # pragma: no cover - impedito dal parser
        raise JsonPatchError(f"{operation.op}: campo 'from' assente")
    source = parse_pointer(operation.from_path)

    if operation.op == "copy":
        return _add(document, path, _json_clone(_get(document, source)))

    if operation.op == "move":
        if source == path:
            _get(document, source)
            return document
        if len(path) > len(source) and path[: len(source)] == source:
            raise JsonPatchError("move non puo spostare un valore dentro un proprio discendente")
        value = _json_clone(_get(document, source))
        without_source, _ = _remove(document, source)
        return _add(without_source, path, value)

    raise JsonPatchError(f"operazione sconosciuta: {operation.op}")  # pragma: no cover


def _get(document: Any, tokens: tuple[str, ...]) -> Any:
    current = document
    for token in tokens:
        if isinstance(current, dict):
            if token not in current:
                raise JsonPatchError(f"chiave inesistente: {token!r}")
            current = current[token]
        elif isinstance(current, list):
            current = current[_array_index(token, len(current))]
        else:
            raise JsonPatchError(f"impossibile attraversare un valore scalare a {token!r}")
    return current


def _parent(document: Any, tokens: tuple[str, ...]) -> tuple[Any, str]:
    if not tokens:
        raise JsonPatchError("la radice non ha un contenitore padre")
    return _get(document, tokens[:-1]), tokens[-1]


def _add(document: Any, tokens: tuple[str, ...], value: Any) -> Any:
    value = _json_clone(value)
    if not tokens:
        return value
    parent, token = _parent(document, tokens)
    if isinstance(parent, dict):
        parent[token] = value
        return document
    if isinstance(parent, list):
        index = _array_index(token, len(parent), allow_end=True, allow_dash=True)
        parent.insert(index, value)
        return document
    raise JsonPatchError("add richiede come padre un oggetto o un array")


def _remove(document: Any, tokens: tuple[str, ...]) -> tuple[Any, Any]:
    if not tokens:
        return None, document
    parent, token = _parent(document, tokens)
    if isinstance(parent, dict):
        if token not in parent:
            raise JsonPatchError(f"chiave inesistente: {token!r}")
        return document, parent.pop(token)
    if isinstance(parent, list):
        index = _array_index(token, len(parent))
        return document, parent.pop(index)
    raise JsonPatchError("remove richiede come padre un oggetto o un array")


def _replace(document: Any, tokens: tuple[str, ...], value: Any) -> Any:
    value = _json_clone(value)
    if not tokens:
        return value
    parent, token = _parent(document, tokens)
    if isinstance(parent, dict):
        if token not in parent:
            raise JsonPatchError(f"chiave inesistente: {token!r}")
        parent[token] = value
        return document
    if isinstance(parent, list):
        parent[_array_index(token, len(parent))] = value
        return document
    raise JsonPatchError("replace richiede come padre un oggetto o un array")


def _array_index(
    token: str,
    length: int,
    *,
    allow_end: bool = False,
    allow_dash: bool = False,
) -> int:
    if token == "-":
        if allow_dash:
            return length
        raise JsonPatchError("'-' e valido soltanto come destinazione di add")
    if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
        raise JsonPatchError(f"indice array non valido: {token!r}")
    index = int(token)
    upper = length if allow_end else length - 1
    if index < 0 or index > upper:
        raise JsonPatchError(f"indice array fuori intervallo: {index}")
    return index


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise JsonPatchError(f"valore non serializzabile come JSON: {exc}") from exc


def _json_clone(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _json_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _json_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right
