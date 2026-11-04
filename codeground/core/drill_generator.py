"""
Deterministic drill generation engine.
Synthesizes drills grounded directly in concrete AST symbols.
"""
from typing import List, Dict, Any
from codeground.database.connection import transaction, get_db_connection
from config.settings import DATABASE_URL


class DrillGenerator:
    def __init__(self, db_path: str = DATABASE_URL):
        self.db_path = db_path

    def generate_drills_for_project(self, project_id: int) -> int:
        """
        Creates traceable drills for all detected symbols and concepts in a project.
        Avoids generic filler; binds directly to code_symbols.
        """
        conn = get_db_connection(self.db_path)
        try:
            query = """
            SELECT DISTINCT 
                s.id as symbol_id,
                s.symbol_name,
                s.symbol_type,
                s.start_line,
                s.end_line,
                f.id as file_id,
                f.file_path,
                c.id as concept_id,
                c.name as concept_name,
                c.category,
                c.definition,
                c.difficulty
            FROM code_symbols s
            JOIN repository_files f ON s.file_id = f.id
            JOIN project_concepts pc ON pc.project_id = s.project_id AND pc.evidence_file_id = f.id
            JOIN learning_concepts c ON pc.concept_id = c.id
            WHERE s.project_id = ?
            """
            cursor = conn.execute(query, (project_id,))
            candidates = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

        if not candidates:
            return 0

        generated_drills = []
        seen_targets = set()

        for cand in candidates:
            sym_name = cand["symbol_name"]
            sym_type = cand["symbol_type"]
            file_path = cand["file_path"]
            concept = cand["concept_name"]
            key = (cand["file_id"], sym_name, concept)

            if key in seen_targets:
                continue
            seen_targets.add(key)

            # Generate drill template based on concept type
            if concept == "Function Parameters & Arguments" and sym_type in ("function", "method"):
                drill = {
                    "project_id": project_id,
                    "concept_id": cand["concept_id"],
                    "source_file_id": cand["file_id"],
                    "source_symbol_id": cand["symbol_id"],
                    "title": f"Interface Audit: `{sym_name}`",
                    "instructions": (
                        f"Inspect `{sym_name}` in `{file_path}` (lines {cand['start_line']}–{cand['end_line']}). "
                        f"Document all required positional and keyword arguments. "
                        f"Explain how passing invalid types to these parameters affects downstream logic."
                    ),
                    "tutorial": (
                        f"In Python, parameters declare the interface of a subroutine. In `{sym_name}`, "
                        f"clean parameter design establishes an explicit contract between caller and callee."
                    ),
                    "hint": f"Look at line {cand['start_line']} in `{file_path}` to inspect the signature declaration.",
                    "difficulty": "Beginner",
                    "assessment_type": "code_reading"
                }
                generated_drills.append(drill)

            elif concept == "State Mutation & Return Values" and sym_type in ("function", "method"):
                drill = {
                    "project_id": project_id,
                    "concept_id": cand["concept_id"],
                    "source_file_id": cand["file_id"],
                    "source_symbol_id": cand["symbol_id"],
                    "title": f"State Flow Analysis: `{sym_name}`",
                    "instructions": (
                        f"Analyze the exit points of `{sym_name}` in `{file_path}`. "
                        f"Identify what value is returned on successful execution versus error conditions. "
                        f"Does this function mutate external state or return a pure transformed value?"
                    ),
                    "tutorial": (
                        f"Pure functions return deterministic outputs without side effects. Functions that update "
                        f"dictionaries, append to lists, or write to disk are state-mutating procedures."
                    ),
                    "hint": f"Scan through lines {cand['start_line']} to {cand['end_line']} for `return` statements or global alterations.",
                    "difficulty": "Beginner",
                    "assessment_type": "code_reading"
                }
                generated_drills.append(drill)

            elif concept in ("Object-Oriented Modeling & Methods", "Class Composition & Constructors") and sym_type == "class":
                drill = {
                    "project_id": project_id,
                    "concept_id": cand["concept_id"],
                    "source_file_id": cand["file_id"],
                    "source_symbol_id": cand["symbol_id"],
                    "title": f"Domain Model Architecture: `{sym_name}`",
                    "instructions": (
                        f"Inspect the class definition for `{sym_name}` in `{file_path}`. "
                        f"Identify its instance attributes, default states, and explain whether composition "
                        f"or inheritance is used to organize its domain duties."
                    ),
                    "tutorial": (
                        f"Classes encapsulate state and cohesive behavior. The `__init__` constructor sets the "
                        f"baseline invariant for each instance before any method invocations occur."
                    ),
                    "hint": f"Review `{file_path}` starting at line {cand['start_line']}.",
                    "difficulty": "Intermediate",
                    "assessment_type": "audit"
                }
                generated_drills.append(drill)

            elif concept == "Defensive Exception Handling" and sym_type in ("function", "method"):
                drill = {
                    "project_id": project_id,
                    "concept_id": cand["concept_id"],
                    "source_file_id": cand["file_id"],
                    "source_symbol_id": cand["symbol_id"],
                    "title": f"Fault Tolerance Review: `{sym_name}`",
                    "instructions": (
                        f"Examine error handling inside `{sym_name}` in `{file_path}`. "
                        f"Identify which specific exceptions are caught. Are broad `except Exception:` blocks "
                        f"used, and what recovery path is provided when an error strikes?"
                    ),
                    "tutorial": (
                        f"Defensive engineering requires catching precise exception types rather than blanket masks. "
                        f"Unchecked exceptions crash processes, but suppressed exceptions create silent bugs."
                    ),
                    "hint": f"Look inside lines {cand['start_line']}–{cand['end_line']} for `try:` and `except:` blocks.",
                    "difficulty": "Intermediate",
                    "assessment_type": "debugging"
                }
                generated_drills.append(drill)

        # Atomic insert of grounded drills
        with transaction(self.db_path) as conn:
            conn.execute("DELETE FROM drills WHERE project_id = ?", (project_id,))
            insert_rows = [
                (
                    d["project_id"],
                    d["concept_id"],
                    d["source_file_id"],
                    d["source_symbol_id"],
                    d["title"],
                    d["instructions"],
                    d["tutorial"],
                    d["hint"],
                    d["difficulty"],
                    d["assessment_type"]
                )
                for d in generated_drills
            ]
            conn.executemany(
                """
                INSERT INTO drills (
                    project_id, concept_id, source_file_id, source_symbol_id,
                    title, instructions, tutorial, hint, difficulty, assessment_type
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                insert_rows
            )

        return len(generated_drills)

    def list_drills(self, project_id: int) -> List[Dict[str, Any]]:
        conn = get_db_connection(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT 
                    d.id, d.title, d.instructions, d.tutorial, d.hint,
                    d.difficulty, d.assessment_type,
                    f.file_path,
                    s.symbol_name, s.start_line, s.end_line,
                    c.name as concept_name, c.category as concept_category
                FROM drills d
                JOIN repository_files f ON d.source_file_id = f.id
                LEFT JOIN code_symbols s ON d.source_symbol_id = s.id
                JOIN learning_concepts c ON d.concept_id = c.id
                WHERE d.project_id = ?
                ORDER BY d.id ASC
                """,
                (project_id,)
            )
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def record_attempt(self, user_id: int, drill_id: int, answer: str) -> int:
        """Stores a learner's answer attempt for a drill."""
        with transaction(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO learner_attempts (user_id, drill_id, answer, score, feedback, status)
                VALUES (?, ?, ?, 1.0, 'Response recorded and grounded to source symbol.', 'submitted')
                """,
                (user_id, drill_id, answer)
            )
            return int(cursor.lastrowid)

    def get_learner_attempt(self, user_id: int, drill_id: int) -> Dict[str, Any]:
        conn = get_db_connection(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT answer, score, feedback, status, submitted_at
                FROM learner_attempts
                WHERE user_id = ? AND drill_id = ?
                ORDER BY submitted_at DESC
                LIMIT 1
                """,
                (user_id, drill_id)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
