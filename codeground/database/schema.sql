PRAGMA foreign_keys = ON;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Projects table
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    repo_url TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    branch TEXT DEFAULT 'main',
    commit_sha TEXT,
    language TEXT,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'fetching', 'cloned', 'analyzed', 'failed')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_projects_repo_url ON projects(repo_url);

-- Repository Files table
CREATE TABLE IF NOT EXISTS repository_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    language TEXT,
    file_type TEXT CHECK(file_type IN ('source', 'config', 'test', 'documentation', 'asset', 'other')),
    content_hash TEXT,
    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
    UNIQUE(project_id, file_path)
);

CREATE INDEX IF NOT EXISTS idx_repo_files_project ON repository_files(project_id);

-- Code Symbols table (AST output)
CREATE TABLE IF NOT EXISTS code_symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    file_id INTEGER NOT NULL,
    symbol_name TEXT NOT NULL,
    symbol_type TEXT NOT NULL CHECK(symbol_type IN ('function', 'class', 'method', 'variable', 'import')),
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    source_reference TEXT,
    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
    FOREIGN KEY (file_id) REFERENCES repository_files (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_symbols_file ON code_symbols(file_id);
CREATE INDEX IF NOT EXISTS idx_symbols_project ON code_symbols(project_id);

-- Learning Concepts Catalog
CREATE TABLE IF NOT EXISTS learning_concepts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    definition TEXT NOT NULL,
    difficulty TEXT CHECK(difficulty IN ('Beginner', 'Intermediate', 'Advanced'))
);

-- Project to Concept mapping (Evidence table)
CREATE TABLE IF NOT EXISTS project_concepts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    concept_id INTEGER NOT NULL,
    evidence_file_id INTEGER NOT NULL,
    confidence REAL DEFAULT 1.0,
    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
    FOREIGN KEY (concept_id) REFERENCES learning_concepts (id) ON DELETE CASCADE,
    FOREIGN KEY (evidence_file_id) REFERENCES repository_files (id) ON DELETE CASCADE
);

-- Grounded Drills table
CREATE TABLE IF NOT EXISTS drills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    concept_id INTEGER NOT NULL,
    source_file_id INTEGER NOT NULL,
    source_symbol_id INTEGER,
    title TEXT NOT NULL,
    instructions TEXT NOT NULL,
    tutorial TEXT NOT NULL,
    hint TEXT,
    difficulty TEXT CHECK(difficulty IN ('Beginner', 'Intermediate', 'Advanced')),
    assessment_type TEXT CHECK(assessment_type IN ('mcq', 'code_reading', 'debugging', 'implementation', 'audit')),
    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
    FOREIGN KEY (concept_id) REFERENCES learning_concepts (id) ON DELETE CASCADE,
    FOREIGN KEY (source_file_id) REFERENCES repository_files (id) ON DELETE CASCADE,
    FOREIGN KEY (source_symbol_id) REFERENCES code_symbols (id) ON DELETE SET NULL
);

-- Learner Attempts table
CREATE TABLE IF NOT EXISTS learner_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    drill_id INTEGER NOT NULL,
    answer TEXT NOT NULL,
    score REAL DEFAULT 0.0,
    feedback TEXT,
    status TEXT CHECK(status IN ('submitted', 'evaluated', 'passed', 'failed')),
    submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (drill_id) REFERENCES drills (id) ON DELETE CASCADE
);
