import ast
import re
from typing import Dict, List, Any, Optional


class CodeScope:
    def __init__(self, name: str, scope_type: str, start_line: int, end_line: int):
        self.name = name
        self.scope_type = scope_type  # function, class, method, module
        self.start_line = start_line
        self.end_line = end_line

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.scope_type,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


class ASTAnalyzer:
    """Extracts structural context (classes, functions, imports) for code changes."""

    @staticmethod
    def analyze_file_content(file_path: str, content: str) -> Dict[str, Any]:
        if file_path.endswith(".py"):
            return ASTAnalyzer._analyze_python(content)
        elif any(file_path.endswith(ext) for ext in [".js", ".ts", ".jsx", ".tsx"]):
            return ASTAnalyzer._analyze_javascript_typescript(content)
        else:
            return ASTAnalyzer._analyze_generic(content)

    @staticmethod
    def _analyze_python(content: str) -> Dict[str, Any]:
        scopes: List[CodeScope] = []
        imports: List[str] = []

        try:
            tree = ast.parse(content)
        except Exception:
            return {"scopes": [], "imports": [], "error": "Syntax parse failed"}

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end_lineno = getattr(node, "end_lineno", node.lineno)
                scopes.append(CodeScope(node.name, "function", node.lineno, end_lineno))
            elif isinstance(node, ast.ClassDef):
                end_lineno = getattr(node, "end_lineno", node.lineno)
                scopes.append(CodeScope(node.name, "class", node.lineno, end_lineno))

        return {
            "language": "python",
            "imports": list(set(imports)),
            "scopes": [s.to_dict() for s in scopes],
        }

    @staticmethod
    def _analyze_javascript_typescript(content: str) -> Dict[str, Any]:
        imports = re.findall(r"(?:import|require)\s*\(?['\"]([^'\"]+)['\"]", content)
        functions = re.findall(r"(?:function\s+([a-zA-Z0-9_$]+)|const\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?\()", content)
        classes = re.findall(r"class\s+([a-zA-Z0-9_$]+)", content)

        extracted_funcs = [f[0] or f[1] for f in functions if f[0] or f[1]]
        return {
            "language": "javascript/typescript",
            "imports": list(set(imports)),
            "functions": extracted_funcs,
            "classes": classes,
        }

    @staticmethod
    def _analyze_generic(content: str) -> Dict[str, Any]:
        return {
            "language": "generic",
            "line_count": len(content.splitlines()),
        }

    @staticmethod
    def find_enclosing_scope(scopes: List[Dict[str, Any]], line_number: int) -> Optional[str]:
        matching_scopes = [
            s for s in scopes
            if s.get("start_line", 0) <= line_number <= s.get("end_line", 0)
        ]
        if not matching_scopes:
            return None

        # Sort by smallest span (end_line - start_line) to get the innermost scope
        innermost = min(matching_scopes, key=lambda s: s.get("end_line", 0) - s.get("start_line", 0))
        return f"{innermost.get('type')}: {innermost.get('name')}"
