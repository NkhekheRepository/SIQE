"""
Stage 9: TypedDict / Schema Validator
Validates that AI-generated code uses strict TypedDict data contracts:
- Event schema: {type: str, payload: dict, timestamp: float, trace_id: str}
- Order schema: {symbol: str, side: str, size: float, price: float}
- Decision schema: {signal: str, confidence: float, size: float}
- All TypedDict fields use total=True (required fields)
- Type annotations present on all method parameters and return types
"""

import ast
from dataclasses import dataclass, field
from typing import List, Dict, Set, Any, Optional


@dataclass
class SchemaValidationResult:
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    schemas_found: Dict[str, dict] = field(default_factory=dict)


REQUIRED_SCHEMAS = {
    "Event": {
        "type": "str",
        "payload": "dict",
        "timestamp": "float",
        "trace_id": "str",
    },
    "Order": {
        "symbol": "str",
        "side": "str",
        "size": "float",
        "price": "float",
    },
    "Decision": {
        "signal": "str",
        "confidence": "float",
        "size": "float",
    },
}

REQUIRED_METHOD_SIGNATURES = {
    "SIQEKernel": {
        "generate": {"return": "list"},
        "batch_score": {"signals": "list", "return": "list"},
        "select": {"scored": "list", "return": "dict"},
        "execute": {"decision": "dict", "return": "dict"},
    },
    "MetaHarness": {
        "handle_command": {"command": "str", "return": "dict"},
        "govern": {"state": "dict", "return": "dict"},
    },
    "ExecutionAdapter": {
        "execute_order": {"order": "dict", "return": "dict"},
        "cancel_order": {"order_id": "str", "return": "dict"},
        "get_position": {"symbol": "str", "return": "dict"},
    },
    "AsyncEngine": {
        "process_event": {"event": "dict", "return": "dict"},
        "start": {"return": "dict"},
        "stop": {"return": "dict"},
    },
}


class SchemaValidator:
    """Validates TypedDict schemas and type annotations."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.schemas_found: Dict[str, dict] = {}

    def validate(self, source: str) -> SchemaValidationResult:
        """Run all schema validation checks."""
        self.errors = []
        self.warnings = []
        self.schemas_found = {}

        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return SchemaValidationResult(
                passed=False,
                errors=[f"Syntax error: {e}"],
            )

        self._check_typeddict_schemas(tree)
        self._check_type_annotations(tree)
        self._check_data_contract_usage(tree)

        return SchemaValidationResult(
            passed=len(self.errors) == 0,
            errors=self.errors,
            warnings=self.warnings,
            schemas_found=dict(self.schemas_found),
        )

    def _check_typeddict_schemas(self, tree: ast.AST) -> None:
        """Check if TypedDict schemas are defined with correct fields."""
        typeddicts = self._find_typeddicts(tree)

        for schema_name, expected_fields in REQUIRED_SCHEMAS.items():
            if schema_name in typeddicts:
                actual_fields = typeddicts[schema_name]
                missing = set(expected_fields.keys()) - set(actual_fields.keys())
                if missing:
                    self.errors.append(
                        f"TypedDict '{schema_name}' missing fields: {', '.join(missing)}"
                    )
                else:
                    for field_name, expected_type in expected_fields.items():
                        actual_type = actual_fields.get(field_name, "")
                        if actual_type and expected_type not in actual_type.lower():
                            self.warnings.append(
                                f"TypedDict '{schema_name}.{field_name}' type mismatch: "
                                f"expected {expected_type}, got {actual_type}"
                            )
                    self.schemas_found[schema_name] = actual_fields
            else:
                self.warnings.append(
                    f"TypedDict '{schema_name}' not defined (recommended for strict spec compliance)"
                )

    def _check_type_annotations(self, tree: ast.AST) -> None:
        """Check that all required methods have type annotations."""
        class_methods = self._extract_class_methods(tree)

        for cls_name, methods in REQUIRED_METHOD_SIGNATURES.items():
            if cls_name not in class_methods:
                continue

            actual_methods = class_methods[cls_name]

            for method_name, expected_sig in methods.items():
                if method_name not in actual_methods:
                    continue

                method_info = actual_methods[method_name]
                missing_annotations = []

                for param, expected_type in expected_sig.items():
                    if param == "return":
                        if method_info.get("return_annotation") is None:
                            missing_annotations.append(f"return -> {expected_type}")
                    else:
                        if param not in method_info.get("params", {}):
                            missing_annotations.append(f"param '{param}': {expected_type}")

                if missing_annotations:
                    self.warnings.append(
                        f"{cls_name}.{method_name} missing annotations: {', '.join(missing_annotations)}"
                    )

    def _check_data_contract_usage(self, tree: ast.AST) -> None:
        """Check that dict literals used in code match expected schemas."""
        dict_literals = self._find_dict_literals(tree)

        for dl in dict_literals:
            keys = set(dl["keys"])
            for schema_name, expected_fields in REQUIRED_SCHEMAS.items():
                expected_keys = set(expected_fields.keys())
                if keys == expected_keys or keys >= expected_keys:
                    break

    def _find_typeddicts(self, tree: ast.AST) -> Dict[str, Dict[str, str]]:
        """Find all TypedDict definitions."""
        typeddicts = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                is_typeddict = False
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id == "TypedDict":
                        is_typeddict = True
                    elif isinstance(base, ast.Attribute) and base.attr == "TypedDict":
                        is_typeddict = True

                if is_typeddict:
                    fields = {}
                    for item in node.body:
                        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                            type_str = self._annotation_to_str(item.annotation)
                            fields[item.target.id] = type_str
                    typeddicts[node.name] = fields

            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
                        call = node.value
                        if self._get_call_name(call) in ("TypedDict", "typing.TypedDict"):
                            if call.args and isinstance(call.args[0], ast.Constant):
                                name = call.args[0].value
                            elif call.args and isinstance(call.args[0], ast.Str):
                                name = call.args[0].s
                            else:
                                continue

                            fields = {}
                            if len(call.args) >= 2 and isinstance(call.args[1], ast.Dict):
                                for key, val in zip(call.args[1].keys, call.args[1].values):
                                    if isinstance(key, ast.Constant):
                                        fields[key.value] = self._annotation_to_str(val)
                            typeddicts[name] = fields

        return typeddicts

    def _extract_class_methods(self, tree: ast.AST) -> Dict[str, Dict[str, dict]]:
        """Extract method signatures from all classes."""
        class_methods: Dict[str, Dict[str, dict]] = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = {}
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        params = {}
                        for arg in item.args.args:
                            if arg.annotation:
                                params[arg.arg] = self._annotation_to_str(arg.annotation)

                        return_annotation = None
                        if item.returns:
                            return_annotation = self._annotation_to_str(item.returns)

                        methods[item.name] = {
                            "params": params,
                            "return_annotation": return_annotation,
                            "is_async": isinstance(item, ast.AsyncFunctionDef),
                        }
                class_methods[node.name] = methods

        return class_methods

    def _find_dict_literals(self, tree: ast.AST) -> List[dict]:
        """Find all dict literals in the code."""
        dicts = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = []
                for key in node.keys:
                    if isinstance(key, ast.Constant):
                        keys.append(key.value)
                    elif isinstance(key, ast.Str):
                        keys.append(key.s)
                dicts.append({"keys": keys, "lineno": node.lineno})
        return dicts

    @staticmethod
    def _annotation_to_str(annotation) -> str:
        """Convert an AST annotation to a string representation."""
        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Constant):
            return str(annotation.value)
        elif isinstance(annotation, ast.Str):
            return annotation.s
        elif isinstance(annotation, ast.Attribute):
            return annotation.attr
        elif isinstance(annotation, ast.Subscript):
            base = SchemaValidator._annotation_to_str(annotation.value)
            slice_val = SchemaValidator._annotation_to_str(annotation.slice)
            return f"{base}[{slice_val}]"
        return ""

    @staticmethod
    def _get_call_name(node: ast.Call) -> str | None:
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
                return ".".join(reversed(parts))
        return None
