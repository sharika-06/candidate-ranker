import streamlit as st
import json
import csv
import io
import pandas as pd
from pathlib import Path

# Import ranking functions from rank.py
import sys
sys.path.append(str(Path(__file__).parent))
from rank import is_honeypot, get_title_score, get_yoe_score, get_company_score, get_skills_score, get_location_score, get_behavioral_multiplier, generate_reasoning

st.set_page_config(
    page_title="Zeroth Error | Candidate Discovery & Ranker",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Styling (Harmonious dark slate / vibrant purple accent palette)
st.markdown("""
<style>
    .main {
        background-color: #0f172a;
        color: #f1f5f9;
    }
    .stButton>button {
        background: linear-gradient(135deg, #a855f7 0%, #6366f1 100%);
        color: white;
        border: none;
        padding: 0.5rem 1.5rem;
        border-radius: 0.375rem;
        font-weight: 600;
        transition: all 0.2s ease-in-out;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(168, 85, 247, 0.4);
    }
    h1, h2, h3 {
        font-family: 'Outfit', 'Inter', sans-serif;
        font-weight: 700;
    }
    .card {
        background-color: #1e293b;
        padding: 1.5rem;
        border-radius: 0.5rem;
        border: 1px solid #334155;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_style_html=True)

st.title("🤖 Zeroth Error - Candidate Discovery & Ranker")
st.subheader("Sandbox App for the Senior AI Engineer — Founding Team role")

st.markdown("""
This sandbox demonstrates our rule-based candidate discovery and ranking system. Upload a candidate profile file 
(`.json` or `.jsonl` containing up to 100 records) to test the filtering, scoring, and reasoning pipeline.
""")

# Sidebar settings
st.sidebar.header("Challenge Settings")
st.sidebar.info("""
**Role:** Senior AI Engineer
**Optimal Experience:** 6 - 8 Years
**Honeypot Tolerance:** < 10%
**Notice Period Bias:** Shorter is favored
**Target Location:** Noida / Pune
""")

# File Uploader
uploaded_file = st.file_uploader("Upload Candidates dataset (.json or .jsonl)", type=["json", "jsonl"])

if uploaded_file is not None:
    # Read file content
    content = uploaded_file.getvalue().decode("utf-8")
    candidates_list = []
    
    # Check if JSON array or JSONL
    if uploaded_file.name.endswith(".json"):
        try:
            candidates_list = json.loads(content)
        except json.JSONDecodeError as e:
            st.error(f"Error parsing JSON file: {e}")
    else:
        for idx, line in enumerate(content.splitlines()):
            if not line.strip():
                continue
            try:
                candidates_list.append(json.loads(line))
            except json.JSONDecodeError as e:
                st.warning(f"Skipping line {idx+1} due to JSON decode error.")
                
    st.success(f"Loaded {len(candidates_list)} candidates successfully!")
    
    if st.button("Rank Candidates"):
        with st.spinner("Processing candidate profiles & behavioral signals..."):
            ranked_candidates = []
            filtered_honeypots = 0
            filtered_non_tech = 0
            filtered_yoe = 0
            
            for candidate in candidates_list:
                cid = candidate.get("candidate_id")
                
                # Anomaly / Honeypot filtering
                honeypot, reason = is_honeypot(candidate)
                if honeypot:
                    filtered_honeypots += 1
                    continue
                    
                # Score features
                title_score = get_title_score(candidate)
                if title_score == 0.0:
                    filtered_non_tech += 1
                    continue
                    
                yoe = candidate.get("profile", {}).get("years_of_experience", 0.0)
                yoe_score = get_yoe_score(yoe)
                if yoe_score == 0.0:
                    filtered_yoe += 1
                    continue
                    
                company_score = get_company_score(candidate)
                skills_score = get_skills_score(candidate)
                location_score = get_location_score(candidate)
                
                # Base score (weighted sum)
                base_score = (
                    0.40 * title_score +
                    0.20 * yoe_score +
                    0.15 * company_score +
                    0.15 * skills_score +
                    0.10 * location_score
                )
                
                # Multiply by behavioral signals
                behavior_mult = get_behavioral_multiplier(candidate)
                final_score = round(base_score * behavior_mult, 4)
                
                ranked_candidates.append({
                    "candidate_id": cid,
                    "name": candidate.get("profile", {}).get("anonymized_name", "Anonymous"),
                    "title": candidate.get("profile", {}).get("current_title", "Engineer"),
                    "yoe": yoe,
                    "location": candidate.get("profile", {}).get("location", "India"),
                    "score": final_score,
                    "reasoning": generate_reasoning(candidate, final_score)
                })
                
            # Sort by score descending, then by candidate_id ascending
            ranked_candidates.sort(key=lambda x: (-x["score"], x["candidate_id"]))
            top_100 = ranked_candidates[:100]
            
            st.write("### 📊 Ranking Diagnostics")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Processed Candidates", len(candidates_list))
            col2.metric("Filtered Honeypots", filtered_honeypots)
            col3.metric("Filtered Non-Tech Roles", filtered_non_tech)
            col4.metric("Qualified / Scored", len(ranked_candidates))
            
            # Display results in table
            st.write("### 🏆 Top Scored Candidates")
            df = pd.DataFrame(top_100)
            if not df.empty:
                df["rank"] = df.index + 1
                df_display = df[["rank", "candidate_id", "name", "title", "yoe", "location", "score", "reasoning"]]
                st.dataframe(df_display, use_container_width=True)
                
                # Create CSV download buffer
                csv_buffer = io.StringIO()
                csv_writer = csv.writer(csv_buffer)
                csv_writer.writerow(["candidate_id", "rank", "score", "reasoning"])
                for idx, entry in enumerate(top_100, 1):
                    csv_writer.writerow([entry["candidate_id"], idx, f"{entry['score']:.4f}", entry["reasoning"]])
                    
                st.download_button(
                    label="Download Submission CSV",
                    data=csv_buffer.getvalue(),
                    file_name="submission.csv",
                    mime="text/csv"
                )
            else:
                st.warning("No candidates qualified after filtering!")
