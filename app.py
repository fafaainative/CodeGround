"""
CodeGround: Main Streamlit Application Entrypoint.
Milestone 4: Concept mapping, grounded drill generation, and interactive engineering workspace.
"""
import shutil
from pathlib import Path
import streamlit as st
from config.settings import DATABASE_URL
from codeground.database.connection import initialize_database
from codeground.database.repositories.projects import ProjectsRepository
from codeground.github.validator import validate_github_url, validate_branch_name, GitHubValidationError
from codeground.github.fetcher import RepositoryFetcher, FetchError
from codeground.analyzers.python_analyzer import PythonAnalyzer
from codeground.core.concept_mapper import ConceptMapper
from codeground.core.drill_generator import DrillGenerator

st.set_page_config(
    page_title="CodeGround - Learning Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Core initialization
initialize_database(DATABASE_URL)
repo_mgr = ProjectsRepository(DATABASE_URL)
fetcher = RepositoryFetcher()
py_analyzer = PythonAnalyzer()
concept_mapper = ConceptMapper(DATABASE_URL)
drill_gen = DrillGenerator(DATABASE_URL)

DEFAULT_USER = "lead_developer"
user_id = repo_mgr.create_user_if_not_exists(DEFAULT_USER, f"{DEFAULT_USER}@local.dev")

if "active_user_id" not in st.session_state:
    st.session_state.active_user_id = user_id
if "selected_project_id" not in st.session_state:
    st.session_state.selected_project_id = None
if "active_drill_id" not in st.session_state:
    st.session_state.active_drill_id = None


def execute_pipeline(project_id: int):
    """Executes AST analysis, concept mapping, and drill generation."""
    target_dir = fetcher.get_target_path(project_id)
    if not target_dir.exists():
        st.error("Repository folder missing from disk.")
        return

    files = repo_mgr.list_project_files(project_id)
    sym_count = 0

    with st.spinner("Extracting AST symbols..."):
        for f in files:
            if f["language"] == "Python":
                symbols = py_analyzer.analyze_file(target_dir, f["file_path"])
                if symbols:
                    repo_mgr.register_code_symbols(project_id, f["id"], symbols)
                    sym_count += len(symbols)

    with st.spinner("Mapping concepts & generating grounded drills..."):
        concept_mapper.map_project_symbols(project_id, target_dir)
        drill_count = drill_gen.generate_drills_for_project(project_id)
        repo_mgr.update_project_status(project_id, "analyzed")

    st.success(f"Pipeline complete: {sym_count} symbols indexed, {drill_count} traceable drills synthesized.")


st.title("⚡ CODEGROUND")
st.caption("Learn by Building. Understand by Practising. Prove It Through Engineering.")
st.markdown("---")

# --- SIDEBAR: REPOSITORY CONNECTION ---
with st.sidebar:
    st.header("Workspace Controls")
    st.markdown(f"**Learner:** `{DEFAULT_USER}`")
    st.divider()

    st.subheader("Connect New Repository")
    new_repo_url = st.text_input("GitHub URL", placeholder="https://github.com/fafaainative/campus_access_card")
    branch_name = st.text_input("Branch", value="main")

    if st.button("Fetch Repository", type="primary", use_container_width=True):
        if not new_repo_url.strip():
            st.warning("Supply a valid GitHub URL.")
        else:
            try:
                canonical_url, owner, repo_name = validate_github_url(new_repo_url)
                safe_branch = validate_branch_name(branch_name)

                project_id = repo_mgr.get_or_create_project(
                    user_id=st.session_state.active_user_id,
                    repo_url=canonical_url,
                    repo_name=repo_name,
                    branch=safe_branch,
                    language="Python"
                )

                with st.spinner(f"Cloning {owner}/{repo_name}..."):
                    repo_mgr.update_project_status(project_id, "fetching")
                    clone_path = fetcher.clone_repository(project_id, canonical_url, safe_branch)
                    tree = fetcher.build_file_tree(clone_path)
                    repo_mgr.register_repository_files(project_id, tree)
                    repo_mgr.update_project_status(project_id, "cloned")

                execute_pipeline(project_id)
                st.session_state.selected_project_id = project_id
                st.rerun()

            except GitHubValidationError as ve:
                st.error(f"Validation: {str(ve)}")
            except FetchError as fe:
                st.error(f"Fetch Error: {str(fe)}")
            except Exception as e:
                st.error(f"Unexpected: {str(e)}")

# --- MAIN WORKSPACE VIEW ---
projects = repo_mgr.list_projects_by_user(st.session_state.active_user_id)

if not projects:
    st.info("No projects in workspace. Paste a repository URL in the sidebar to begin.")
else:
    st.subheader("Active Projects")
    cols = st.columns(3)
    for idx, proj in enumerate(projects):
        stats = repo_mgr.get_project_stats(proj["id"])
        is_selected = st.session_state.selected_project_id == proj["id"]
        border_color = "#4CAF50" if is_selected else "#333"

        with cols[idx % 3]:
            st.markdown(
                f"""
                <div style="border: 1px solid {border_color}; padding: 14px; border-radius: 8px; margin-bottom: 8px; background-color: #1e1e1e;">
                    <h4 style="margin: 0; color: #61afef;">{proj['repo_name']}</h4>
                    <p style="font-size: 11px; color: #888; margin: 2px 0 8px 0;">{proj['repo_url']}</p>
                    <span style="background: #2a2a2a; padding: 2px 6px; border-radius: 4px; font-size: 11px;">Status: <b>{proj['status']}</b></span>
                    <hr style="border: 0.5px solid #2e2e2e; margin: 8px 0;">
                    <p style="font-size: 12px; margin: 0;">Files: <b>{stats['files']}</b> | Symbols: <b>{stats['symbols']}</b> | Drills: <b>{stats['drills']}</b></p>
                </div>
                """,
                unsafe_allow_html=True
            )

            b1, b2 = st.columns([2, 1])
            with b1:
                if st.button("Open Drills", key=f"open_{proj['id']}", use_container_width=True):
                    st.session_state.selected_project_id = proj["id"]
                    st.rerun()
            with b2:
                if st.button("🗑️ Delete", key=f"del_{proj['id']}", use_container_width=True):
                    clone_dir = fetcher.get_target_path(proj["id"])
                    if clone_dir.exists():
                        shutil.rmtree(clone_dir, ignore_errors=True)
                    repo_mgr.delete_project(proj["id"])
                    if st.session_state.selected_project_id == proj["id"]:
                        st.session_state.selected_project_id = None
                    st.rerun()

    # --- PROJECT DRILL & CODING WORKSPACE ---
    if st.session_state.selected_project_id:
        selected_id = st.session_state.selected_project_id
        active_proj = next((p for p in projects if p["id"] == selected_id), None)

        if active_proj:
            st.markdown("---")
            h_col1, h_col2 = st.columns([3, 1])
            with h_col1:
                st.subheader(f"Engineering Drills: {active_proj['repo_name']}")
            with h_col2:
                if st.button("⚡ Re-generate Drills", use_container_width=True):
                    execute_pipeline(selected_id)
                    st.rerun()

            drills = drill_gen.list_drills(selected_id)

            if not drills:
                st.warning("No drills generated yet. Click 'Re-generate Drills' to map concepts and build learning items.")
            else:
                d_col1, d_col2 = st.columns([1, 2])

                with d_col1:
                    st.markdown(f"**Available Drills ({len(drills)} total):**")
                    drill_titles = [f"{d['id']}. {d['title']}" for d in drills]
                    selected_title = st.selectbox("Choose a drill to solve:", drill_titles)
                    selected_drill_id = int(selected_title.split(".")[0])
                    active_drill = next(d for d in drills if d["id"] == selected_drill_id)

                    st.markdown(f"**Concept:** `{active_drill['concept_name']}`")
                    st.markdown(f"**Category:** `{active_drill['concept_category']}`")
                    st.markdown(f"**Difficulty:** `{active_drill['difficulty']}`")
                    st.markdown(f"**Source File:** `{active_drill['file_path']}`")
                    if active_drill["symbol_name"]:
                        st.markdown(f"**Target Symbol:** `{active_drill['symbol_name']}` (L{active_drill['start_line']}–L{active_drill['end_line']})")

                with d_col2:
                    st.markdown(f"### {active_drill['title']}")
                    st.info(f"**Task Instructions:**\n\n{active_drill['instructions']}")

                    with st.expander("📖 Concept Tutorial & Context", expanded=True):
                        st.write(active_drill["tutorial"])

                    with st.expander("💡 Engineering Hint", expanded=False):
                        st.write(active_drill["hint"])

                    # Code snippet anchor view
                    clone_root = fetcher.get_target_path(selected_id)
                    source_file_path = clone_root / active_drill["file_path"]
                    if source_file_path.exists():
                        raw_code = PythonAnalyzer.read_file_safely(source_file_path)
                        with st.expander(f"🔍 Source Reference: {active_drill['file_path']}", expanded=True):
                            st.code(raw_code, language="python", line_numbers=True)

                    st.markdown("#### Your Engineering Explanation / Solution:")
                    prior_attempt = drill_gen.get_learner_attempt(st.session_state.active_user_id, active_drill["id"])
                    default_answer = prior_attempt["answer"] if prior_attempt else ""

                    user_submission = st.text_area(
                        "Write your technical breakdown or code solution here:",
                        value=default_answer,
                        height=160
                    )

                    if st.button("Submit Assessment", type="primary"):
                        if not user_submission.strip():
                            st.warning("Please enter your analysis before submitting.")
                        else:
                            attempt_id = drill_gen.record_attempt(
                                user_id=st.session_state.active_user_id,
                                drill_id=active_drill["id"],
                                answer=user_submission.strip()
                            )
                            st.success(f"Assessment recorded (Attempt #{attempt_id})! Solution linked to symbol {active_drill['symbol_name']}.")
                            st.rerun()

                    if prior_attempt:
                        st.markdown(
                            f"""
                            <div style="background-color: #142d1b; border: 1px solid #2e7d32; padding: 10px; border-radius: 6px; margin-top: 10px;">
                                <b>Latest Submission Status:</b> {prior_attempt['status'].upper()}<br>
                                <span style="font-size: 12px; color: #aaa;">Submitted at: {prior_attempt['submitted_at']}</span><br>
                                <i>Feedback:</i> {prior_attempt['feedback']}
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
