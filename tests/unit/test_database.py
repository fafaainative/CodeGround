"""
Unit tests for database initialization, WAL configuration, foreign key enforcement, and DAO transactions.
"""
import pytest
import sqlite3
from pathlib import Path
from codeground.database.connection import get_db_connection, initialize_database, transaction
from codeground.database.repositories.projects import ProjectsRepository


@pytest.fixture
def test_db(tmp_path: Path):
    db_file = tmp_path / "test_codeground.db"
    schema_path = Path(__file__).resolve().parent.parent.parent / "codeground" / "database" / "schema.sql"
    initialize_database(str(db_file), schema_file=schema_path)
    return str(db_file)


def test_sqlite_pragmas_enabled(test_db: str):
    conn = get_db_connection(test_db)
    
    # Assert WAL Mode
    journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    assert journal_mode.lower() == "wal"
    
    # Assert Foreign Keys ON
    fk_status = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
    assert fk_status == 1
    conn.close()


def test_foreign_key_constraint_enforcement(test_db: str):
    conn = get_db_connection(test_db)
    
    # Inserting a project with a nonexistent user_id must raise IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO projects (user_id, repo_url, repo_name)
            VALUES (?, ?, ?)
            """,
            (9999, "https://github.com/foo/bar", "bar")
        )
    conn.close()


def test_projects_repository_crud(test_db: str):
    repo = ProjectsRepository(test_db)
    
    # Create user
    user_id = repo.create_user_if_not_exists("testuser", "test@test.org")
    assert user_id > 0
    
    # Re-calling with identical username returns existing user_id
    duplicate_user_id = repo.create_user_if_not_exists("testuser", "test@test.org")
    assert duplicate_user_id == user_id
    
    # Create project
    project_id = repo.create_project(
        user_id=user_id,
        repo_url="https://github.com/test/repo",
        repo_name="repo",
        branch="develop",
        language="Python"
    )
    assert project_id > 0
    
    # List projects
    projects = repo.list_projects_by_user(user_id)
    assert len(projects) == 1
    assert projects[0]["repo_name"] == "repo"
    assert projects[0]["status"] == "pending"
    assert projects[0]["branch"] == "develop"
    
    # Project stats
    stats = repo.get_project_stats(project_id)
    assert stats == {"files": 0, "symbols": 0, "drills": 0}


def test_transaction_rollback_on_error(test_db: str):
    repo = ProjectsRepository(test_db)
    user_id = repo.create_user_if_not_exists("atomic_user", "atomic@test.org")
    
    with pytest.raises(ValueError):
        with transaction(test_db) as conn:
            conn.execute(
                "INSERT INTO projects (user_id, repo_url, repo_name) VALUES (?, ?, ?)",
                (user_id, "https://github.com/a/b", "b")
            )
            # Deliberate failure inside transaction block
            raise ValueError("Simulated pipeline failure")
            
    # Verify rollback succeeded
    projects = repo.list_projects_by_user(user_id)
    assert len(projects) == 0
