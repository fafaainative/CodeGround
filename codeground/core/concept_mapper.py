"""
Concept mapping engine for CodeGround.
Matches extracted AST symbols and code features to pedagogical concepts.
"""
from typing import List, Dict, Any, Tuple
from pathlib import Path
import ast
from codeground.database.connection import transaction, get_db_connection
from config.settings import DATABASE_URL
from codeground.analyzers.python_analyzer import PythonAnalyzer


BASE_CONCEPTS = [
    {
        "name": "Function Parameters & Arguments",
        "category": "Functions",
        "definition": "Defining inputs for reusable subroutines and receiving explicit caller values.",
        "difficulty": "Beginner"
    },
    {
        "name": "State Mutation & Return Values",
        "category": "Functions",
        "definition": "Returning explicit results or altering application state via side effects.",
        "difficulty": "Beginner"
    },
    {
        "name": "Object-Oriented Modeling & Methods",
        "category": "Object-Oriented Programming",
        "definition": "Encapsulating data and state-altering behaviors inside classes and instances.",
        "difficulty": "Intermediate"
    },
    {
        "name": "Class Composition & Constructors",
        "category": "Object-Oriented Programming",
        "definition": "Initializing instance state via __init__ and composing domain entities.",
        "difficulty": "Intermediate"
    },
    {
        "name": "Defensive Exception Handling",
        "category": "Software Engineering",
        "definition": "Safeguarding critical runtime operations using try-except blocks.",
        "difficulty": "Intermediate"
    },
    {
        "name": "Dependency Modularization",
        "category": "Project Architecture",
        "definition": "Structuring software across discrete modules and managing package imports.",
        "difficulty": "Beginner"
    }
]


class ConceptMapper:
    def __init__(self, db_path: str = DATABASE_URL):
        self.db_path = db_path
        self._ensure_catalogue_seeded()

    def _ensure_catalogue_seeded(self) -> None:
        """Seeds base concepts if missing."""
        with transaction(self.db_path) as conn:
            for c in BASE_CONCEPTS:
                conn.execute(
                    """
                    INSERT INTO learning_concepts (name, category, definition, difficulty)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        definition = excluded.definition,
                        difficulty = excluded.difficulty
                    """,
                    (c["name"], c["category"], c["definition"], c["difficulty"])
                )

    def get_concept_by_name(self, name: str) -> Dict[str, Any]:
        conn = get_db_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT id, name, category, definition, difficulty FROM learning_concepts WHERE name = ?",
                (name,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def map_project_symbols(self, project_id: int, clone_root: Path) -> List[Dict[str, Any]]:
        """
        Scans symbols in project and identifies conceptual evidence.
        Returns mapped concept links.
        """
        conn = get_db_connection(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT s.id as symbol_id, s.file_id, s.symbol_name, s.symbol_type,
                       s.start_line, s.end_line, f.file_path
                FROM code_symbols s
                JOIN repository_files f ON s.file_id = f.id
                WHERE s.project_id = ?
                """,
                (project_id,)
            )
            symbols = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

        evidence_records = []

        for sym in symbols:
            file_path = clone_root / sym["file_path"]
            if not file_path.exists() or not sym["file_path"].endswith(".py"):
                continue

            source = PythonAnalyzer.read_file_safely(file_path)
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue

            # AST node deep inspection for the symbol
            for node in ast.walk(tree):
                # Class mapping
                if isinstance(node, ast.ClassDef) and sym["symbol_name"] == node.name:
                    has_init = any(isinstance(n, ast.FunctionDef) and n.name == "__init__" for n in node.body)
                    concept_name = "Class Composition & Constructors" if has_init else "Object-Oriented Modeling & Methods"
                    c = self.get_concept_by_name(concept_name)
                    if c:
                        evidence_records.append((project_id, c["id"], sym["file_id"], 1.0, sym["symbol_id"], c["name"]))

                # Function / Method mapping
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    is_match = (
                        sym["symbol_name"] == node.name or 
                        sym["symbol_name"].endswith(f".{node.name}")
                    )
                    if is_match and getattr(node, "lineno", None) == sym["start_line"]:
                        # Detect parameters
                        args_count = len(node.args.args)
                        if args_count > 0:
                            c = self.get_concept_by_name("Function Parameters & Arguments")
                            if c:
                                evidence_records.append((project_id, c["id"], sym["file_id"], 0.95, sym["symbol_id"], c["name"]))

                        # Detect return values or state mutation
                        returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
                        if returns:
                            c = self.get_concept_by_name("State Mutation & Return Values")
                            if c:
                                evidence_records.append((project_id, c["id"], sym["file_id"], 0.95, sym["symbol_id"], c["name"]))

                        # Detect defensive exception handling
                        try_blocks = [n for n in ast.walk(node) if isinstance(n, ast.Try)]
                        if try_blocks:
                            c = self.get_concept_by_name("Defensive Exception Handling")
                            if c:
                                evidence_records.append((project_id, c["id"], sym["file_id"], 1.0, sym["symbol_id"], c["name"]))

                # Module imports
                elif isinstance(node, (ast.Import, ast.ImportFrom)) and sym["symbol_type"] == "import":
                    if getattr(node, "lineno", None) == sym["start_line"]:
                        c = self.get_concept_by_name("Dependency Modularization")
                        if c:
                            evidence_records.append((project_id, c["id"], sym["file_id"], 0.85, sym["symbol_id"], c["name"]))

        # Persist detected evidence into project_concepts
        with transaction(self.db_path) as db:
            db.execute("DELETE FROM project_concepts WHERE project_id = ?", (project_id,))
            for rec in evidence_records:
                proj_id, concept_id, file_id, conf, _, _ = rec
                db.execute(
                    """
                    INSERT INTO project_concepts (project_id, concept_id, evidence_file_id, confidence)
                    VALUES (?, ?, ?, ?)
                    """,
                    (proj_id, concept_id, file_id, conf)
                )

        return evidence_records

        