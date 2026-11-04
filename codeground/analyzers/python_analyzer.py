"""
Static AST analyzer for Python source files.
Extracts classes, functions, async functions, methods, imports,
and module-level constants/variables with exact line numbers.
"""
import ast
from pathlib import Path
from typing import List, Dict, Any, Optional


class PythonASTVisitor(ast.NodeVisitor):
    def __init__(self, relative_file_path: str):
        self.relative_file_path = relative_file_path
        self.symbols: List[Dict[str, Any]] = []
        self._current_class: Optional[str] = None

    def visit_ClassDef(self, node: ast.ClassDef):
        # Record class definition
        self.symbols.append({
            "name": node.name,
            "type": "class",
            "start_line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "reference": f"{self.relative_file_path}:{node.lineno}"
        })

        # Track class context for methods
        previous_class = self._current_class
        self._current_class = node.name
        self.generic_visit(node)
        self._current_class = previous_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._record_callable(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._record_callable(node, is_async=True)

    def _record_callable(self, node: Any, is_async: bool = False):
        if self._current_class:
            symbol_type = "method"
            qualified_name = f"{self._current_class}.{node.name}"
        else:
            symbol_type = "function"
            qualified_name = node.name

        self.symbols.append({
            "name": qualified_name,
            "type": symbol_type,
            "start_line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "reference": f"{self.relative_file_path}:{node.lineno}"
        })
        # Visit inner nodes (e.g. inner functions)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.symbols.append({
                "name": f"import {name}",
                "type": "import",
                "start_line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
                "reference": f"{self.relative_file_path}:{node.lineno}"
            })
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            imported = alias.asname if alias.asname else alias.name
            self.symbols.append({
                "name": f"from {module} import {imported}",
                "type": "import",
                "start_line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
                "reference": f"{self.relative_file_path}:{node.lineno}"
            })
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        # Only capture module-level assignments (constants/globals)
        if self._current_class is None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.symbols.append({
                        "name": target.id,
                        "type": "variable",
                        "start_line": node.lineno,
                        "end_line": getattr(node, "end_lineno", node.lineno),
                        "reference": f"{self.relative_file_path}:{node.lineno}"
                    })
        self.generic_visit(node)


class PythonAnalyzer:
    @staticmethod
    def read_file_safely(file_path: Path) -> str:
        """Reads file source defensively trying utf-8, then fallback encoding."""
        try:
            return file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return file_path.read_text(encoding="latin-1", errors="replace")

    def analyze_file(self, root_dir: Path, relative_file_path: str) -> List[Dict[str, Any]]:
        """Parses a Python file into AST symbols without executing it."""
        abs_path = (root_dir / relative_file_path).resolve()
        if not abs_path.exists() or abs_path.suffix.lower() != ".py":
            return []

        source_code = self.read_file_safely(abs_path)
        try:
            tree = ast.parse(source_code, filename=str(abs_path))
        except SyntaxError:
            # File contains invalid Python syntax; skip or record error safely
            return []

        visitor = PythonASTVisitor(relative_file_path)
        visitor.visit(tree)
        return visitor.symbols