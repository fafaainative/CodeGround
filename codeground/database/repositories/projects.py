"""
Data Access Object (DAO) for Projects, Users, and Repository Files.
"""
from typing import Optional, List, Dict, Any
from codeground.database.connection import transaction, get_db_connection
from config.settings import DATABASE_URL


class ProjectsRepository:
    def __init__(self, db_path: str = DATABASE_URL):
        self.db_path = db_path

    def create_user_if_not_exists(self, username: str, email: str, password_hash: str = "local_dev") -> int:
        with transaction(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            )
            row = cursor.fetchone()
            if row:
                return int(row["id"])
            
            cursor = conn.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, password_hash)
            )
            return int(cursor.lastrowid)

    def get_or_create_project(self, user_id: int, repo_url: str, repo_name: str, branch: str = "main", language: Optional[str] = None) -> int:
        """Finds an existing project with the same URL and branch, or creates a new one."""
        with transaction(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id FROM projects 
                WHERE user_id = ? AND repo_url = ? AND branch = ?
                """,
                (user_id, repo_url, branch)
            )
            row = cursor.fetchone()
            if row:
                return int(row["id"])

            cursor = conn.execute(
                """
                INSERT INTO projects (user_id, repo_url, repo_name, branch, language, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
                """,
                (user_id, repo_url, repo_name, branch, language)
            )
            return int(cursor.lastrowid)

    def create_project(self, user_id: int, repo_url: str, repo_name: str, branch: str = "main", language: Optional[str] = None) -> int:
        with transaction(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO projects (user_id, repo_url, repo_name, branch, language, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
                """,
                (user_id, repo_url, repo_name, branch, language)
            )
            return int(cursor.lastrowid)

    def update_project_status(self, project_id: int, status: str) -> None:
        with transaction(self.db_path) as conn:
            conn.execute(
                "UPDATE projects SET status = ? WHERE id = ?",
                (status, project_id)
            )

    def delete_project(self, project_id: int) -> None:
        """Deletes project from database. Foreign key cascades remove linked files and symbols."""
        with transaction(self.db_path) as conn:
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def list_projects_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        conn = get_db_connection(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT id, user_id, repo_url, repo_name, branch, language, status, created_at
                FROM projects
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def register_repository_files(self, project_id: int, files: List[Dict[str, Any]]) -> None:
        """Stores detected files and categories into repository_files."""
        with transaction(self.db_path) as conn:
            conn.execute("DELETE FROM repository_files WHERE project_id = ?", (project_id,))

            insert_rows = []
            for item in files:
                path = item["path"]
                ext = item["extension"]

                if ext in [".py", ".js", ".ts", ".java", ".c", ".cpp"]:
                    file_type = "source"
                    language = "Python" if ext == ".py" else ("JavaScript" if ext in [".js", ".ts"] else "Other")
                elif ext in [".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"]:
                    file_type = "config"
                    language = "Config"
                elif ext in [".md", ".txt", ".rst"]:
                    file_type = "documentation"
                    language = "Markdown"
                elif "test" in path.lower():
                    file_type = "test"
                    language = "Python" if ext == ".py" else "Other"
                else:
                    file_type = "other"
                    language = "Other"

                insert_rows.append((project_id, path, language, file_type, None))

            conn.executemany(
                """
                INSERT INTO repository_files (project_id, file_path, language, file_type, content_hash)
                VALUES (?, ?, ?, ?, ?)
                """,
                insert_rows
            )

    def list_project_files(self, project_id: int) -> List[Dict[str, Any]]:
        conn = get_db_connection(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT id, file_path, language, file_type
                FROM repository_files
                WHERE project_id = ?
                ORDER BY file_path ASC
                """,
                (project_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_project_stats(self, project_id: int) -> Dict[str, int]:
        conn = get_db_connection(self.db_path)
        try:
            files_count = conn.execute(
                "SELECT COUNT(*) FROM repository_files WHERE project_id = ?", (project_id,)
            ).fetchone()[0]
            
            symbols_count = conn.execute(
                "SELECT COUNT(*) FROM code_symbols WHERE project_id = ?", (project_id,)
            ).fetchone()[0]
            
            drills_count = conn.execute(
                "SELECT COUNT(*) FROM drills WHERE project_id = ?", (project_id,)
            ).fetchone()[0]

            return {
                "files": files_count,
                "symbols": symbols_count,
                "drills": drills_count
            }
        finally:
            conn.close()

    def register_code_symbols(self, project_id: int, file_id: int, symbols: List[Dict[str, Any]]) -> None:
        """Persists extracted AST symbols for a specific file."""
        with transaction(self.db_path) as conn:
            conn.execute(
                "DELETE FROM code_symbols WHERE project_id = ? AND file_id = ?",
                (project_id, file_id)
            )

            insert_rows = [
                (
                    project_id,
                    file_id,
                    sym["name"],
                    sym["type"],
                    sym["start_line"],
                    sym["end_line"],
                    sym["reference"]
                )
                for sym in symbols
            ]

            conn.executemany(
                """
                INSERT INTO code_symbols (
                    project_id, file_id, symbol_name, symbol_type,
                    start_line, end_line, source_reference
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                insert_rows
            )

    def list_symbols_by_file(self, file_id: int) -> List[Dict[str, Any]]:
        """Lists symbols extracted from a specific file."""
        conn = get_db_connection(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT id, symbol_name, symbol_type, start_line, end_line, source_reference
                FROM code_symbols
                WHERE file_id = ?
                ORDER BY start_line ASC
                """,
                (file_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    def list_project_symbols(self, project_id: int) -> List[Dict[str, Any]]:
        """Lists all symbols across all files in the project."""
        conn = get_db_connection(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT s.id, s.file_id, f.file_path, s.symbol_name, s.symbol_type, s.start_line, s.end_line
                FROM code_symbols s
                JOIN repository_files f ON s.file_id = f.id
                WHERE s.project_id = ?
                ORDER BY f.file_path ASC, s.start_line ASC
                """,
                (project_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
