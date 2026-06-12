#!/usr/bin/env python3
import json
import csv
import re
import argparse
from datetime import datetime
from pathlib import Path

# Target current year of the dataset
CURRENT_YEAR = 2026

def is_honeypot(candidate):
    # 1. Zero duration expert/advanced skills check
    zero_dur_expert_count = 0
    skills = candidate.get("skills", [])
    for skill in skills:
        dur = skill.get("duration_months")
        prof = skill.get("proficiency", "").lower()
        if (dur == 0 or dur is None) and prof in ["expert", "advanced"]:
            zero_dur_expert_count += 1
            
    if zero_dur_expert_count >= 3:
        return True, "zero_duration_expert_skills"

    # 2. Career history date contradictions & impossible timelines
    career = candidate.get("career_history", [])
    for job in career:
        desc = job.get("description", "")
        start_date_str = job.get("start_date")
        if not start_date_str:
            continue
        try:
            start_year = datetime.strptime(start_date_str, "%Y-%m-%d").year
        except ValueError:
            continue
        
        duration_months = job.get("duration_months", 0)
        
        # Match foundation patterns (e.g. "founded in 2023", "established 3 years ago")
        found_year = None
        match_in = re.search(r'(?:founded|established|started|created|began)\s+(?:in\s+)?(\d{4})', desc, re.IGNORECASE)
        if match_in:
            found_year = int(match_in.group(1))
        else:
            match_ago = re.search(r'(?:founded|established|started|created|began)\s+(\d+)\s+years?\s+ago', desc, re.IGNORECASE)
            if match_ago:
                years_ago = int(match_ago.group(1))
                found_year = CURRENT_YEAR - years_ago
                
        if found_year:
            # Anomaly A: Candidate started working before the company was founded
            if start_year < found_year:
                return True, f"start_year_before_founded_{found_year}"
            
            # Anomaly B: Candidate claims experience duration longer than the company's age
            max_possible_duration_months = (CURRENT_YEAR - found_year) * 12 + 12
            if duration_months > max_possible_duration_months:
                return True, f"duration_longer_than_company_age"

    return False, ""


def get_title_score(candidate):
    current_title = candidate.get("profile", {}).get("current_title", "").lower()
    
    # Non-tech roles are flat out penalized (keyword stuffers)
    non_tech_keywords = [
        "marketing", "hr ", "human resources", "accountant", "civil", "mechanical", 
        "graphic designer", "customer support", "operations manager", "operations analyst", 
        "sales executive", "qa engineer", "financial", "brand designer", "recruiter"
    ]
    for keyword in non_tech_keywords:
        if keyword in current_title:
            return 0.0
            
    # Core target roles for Senior AI Engineer
    target_ai_keywords = [
        "ai engineer", "machine learning", "ml engineer", "nlp", "natural language", 
        "search engineer", "information retrieval", "recommendation", "data scientist", 
        "research engineer", "retrieval engineer"
    ]
    for kw in target_ai_keywords:
        if kw in current_title:
            return 1.0
            
    # Technical adjacent roles
    tech_adjacent_keywords = [
        "backend", "software engineer", "data engineer", "systems engineer", 
        "full stack", "developer", "tech lead", "engineering lead"
    ]
    for kw in tech_adjacent_keywords:
        if kw in current_title:
            return 0.6
            
    return 0.1


def get_yoe_score(yoe):
    # Target: 5-9 years (optimal: 6-8 years)
    if yoe < 3:
        return 0.0
    elif 3 <= yoe < 5:
        # linear scale from 0.2 to 0.9
        return 0.2 + 0.7 * (yoe - 3) / 2
    elif 5 <= yoe <= 9:
        if 6 <= yoe <= 8:
            return 1.0
        else:
            return 0.95
    elif 9 < yoe <= 12:
        # linear scale from 0.95 to 0.5
        return 0.95 - 0.45 * (yoe - 9) / 3
    elif 12 < yoe <= 15:
        # linear scale from 0.5 to 0.1
        return 0.5 - 0.4 * (yoe - 12) / 3
    else:
        return 0.05


def get_company_score(candidate):
    career = candidate.get("career_history", [])
    if not career:
        return 0.5
        
    service_companies = [
        "tcs", "infosys", "wipro", "accenture", "cognizant", "capgemini", 
        "tata consultancy", "mindtree", "l&t", "tech mahindra", "hcl"
    ]
    
    total_jobs = len(career)
    service_jobs = 0
    product_jobs = 0
    
    for job in career:
        company = job.get("company", "").lower()
        is_service = False
        for sc in service_companies:
            if sc in company:
                is_service = True
                break
        if is_service:
            service_jobs += 1
        else:
            desc = job.get("description", "").lower()
            if any(term in desc for term in ["product", "saas", "scale", "users", "platform"]):
                product_jobs += 1
                
    if service_jobs == total_jobs:
        return 0.1  # Pure service company career is heavily down-weighted
        
    non_service_ratio = (total_jobs - service_jobs) / total_jobs
    product_boost = min(1.0, product_jobs / total_jobs) * 0.2
    
    return min(1.0, non_service_ratio * 0.8 + product_boost + 0.2)


def get_skills_score(candidate):
    skills = candidate.get("skills", [])
    if not skills:
        return 0.0
        
    core_keywords = [
        "embedding", "retrieval", "vector", "search", "pinecone", "weaviate", 
        "qdrant", "milvus", "opensearch", "elasticsearch", "faiss", "ndcg", 
        "mrr", "map", "eval", "python", "nlp", "information retrieval", "ir"
    ]
    nice_keywords = [
        "lora", "qlora", "peft", "fine-tuning", "fine tuning", "xgboost", 
        "learning to rank", "distributed", "inference", "rag", "large language model", "llm"
    ]
    
    score = 0.0
    for skill in skills:
        name = skill.get("name", "").lower()
        dur = skill.get("duration_months")
        prof = skill.get("proficiency", "").lower()
        
        prof_weight = 0.1
        if prof == "expert":
            prof_weight = 1.0
        elif prof == "advanced":
            prof_weight = 0.8
        elif prof == "intermediate":
            prof_weight = 0.5
            
        dur_factor = 0.3
        if dur is not None:
            if dur <= 3:
                dur_factor = 0.1
            elif dur <= 12:
                dur_factor = 0.5
            else:
                dur_factor = 1.0
                
        skill_value = prof_weight * dur_factor
        
        is_core = any(ck in name for ck in core_keywords)
        is_nice = any(nk in name for nk in nice_keywords)
        
        if is_core:
            score += 1.5 * skill_value
        elif is_nice:
            score += 1.0 * skill_value
            
    max_expected_score = 6.0
    return min(1.0, score / max_expected_score)


def get_location_score(candidate):
    profile = candidate.get("profile", {})
    loc = profile.get("location", "").lower()
    country = profile.get("country", "").lower()
    willing_to_relocate = candidate.get("redrob_signals", {}).get("willing_to_relocate", False)
    
    if "noida" in loc or "pune" in loc:
        return 1.0
        
    in_india = False
    if "india" in country:
        in_india = True
    else:
        indian_cities = [
            "bangalore", "bengaluru", "hyderabad", "chennai", "mumbai", "gurgaon", 
            "gurugram", "delhi", "ncr", "pune", "noida", "kolkata", "ahmedabad", "jaipur"
        ]
        if any(city in loc for city in indian_cities):
            in_india = True
            
    if in_india:
        if willing_to_relocate:
            return 0.8
        else:
            return 0.2
    else:
        return 0.01  # Heavily down-weight candidates based outside India


def get_behavioral_multiplier(candidate):
    signals = candidate.get("redrob_signals", {})
    
    # 1. Recruiter Response Rate
    rrr = signals.get("recruiter_response_rate", 0.0)
    if rrr >= 0.70:
        rr_mult = 1.2
    elif rrr < 0.20:
        rr_mult = 0.3
    else:
        rr_mult = 0.3 + 1.8 * (rrr - 0.20)
        
    # 2. Last Active Date (June 2026 is current time)
    last_active = signals.get("last_active_date", "")
    active_mult = 0.5
    if last_active:
        try:
            parts = last_active.split("-")
            active_year = int(parts[0])
            active_month = int(parts[1])
            if active_year == 2026:
                active_mult = 1.2
            elif active_year == 2025:
                if active_month >= 6:
                    active_mult = 0.8
                else:
                    active_mult = 0.6
            else:
                active_mult = 0.2
        except (ValueError, IndexError):
            pass
            
    # 3. Open to Work
    otw = signals.get("open_to_work_flag", False)
    otw_mult = 1.1 if otw else 0.9
    
    # 4. Notice Period
    notice = signals.get("notice_period_days", 90)
    if notice <= 30:
        notice_mult = 1.2
    elif notice <= 60:
        notice_mult = 1.0
    elif notice <= 90:
        notice_mult = 0.8
    else:
        notice_mult = 0.4
        
    # 5. Interview Completion
    icr = signals.get("interview_completion_rate", 1.0)
    icr_mult = 1.1 if icr >= 0.8 else (0.5 if icr < 0.5 else 0.8)
    
    mult = rr_mult * active_mult * otw_mult * notice_mult * icr_mult
    return max(0.1, min(1.5, mult))


def generate_reasoning(candidate, score):
    profile = candidate.get("profile", {})
    title = profile.get("current_title", "Engineer")
    yoe = profile.get("years_of_experience", 0.0)
    loc = profile.get("location", "India")
    
    # Get actual skills matching target keywords
    candidate_skills = [s.get("name") for s in candidate.get("skills", []) if s.get("name")]
    key_skills = ["embeddings", "vector search", "NLP", "RAG", "retrieval", "Milvus", "Pinecone", "Weaviate", "Qdrant", "fine-tuning", "LLMs", "A/B testing", "NDCG", "Python"]
    matching_skills = []
    for ks in key_skills:
        for cs in candidate_skills:
            if ks.lower() in cs.lower() and cs not in matching_skills:
                matching_skills.append(cs)
                break
                
    skill_str = ""
    if matching_skills:
        skill_str = f" with hands-on depth in {', '.join(matching_skills[:3])}"
        
    loc_str = ""
    if "pune" in loc.lower() or "noida" in loc.lower():
        loc_str = f" based in {loc}"
    elif candidate.get("redrob_signals", {}).get("willing_to_relocate", False):
        loc_str = f" based in {loc} and willing to relocate"
    else:
        loc_str = f" based in {loc}"
        
    signals = candidate.get("redrob_signals", {})
    rrr = signals.get("recruiter_response_rate", 0.0)
    notice = signals.get("notice_period_days", 90)
    
    notice_str = f"a short {notice}-day notice period" if notice <= 30 else f"a {notice}-day notice period"
    resp_str = f"high recruiter response rate ({int(rrr*100)}%)"
    
    reasoning = f"{title}{loc_str} with {yoe:.1f} years of experience. Strong technical match{skill_str}, paired with {resp_str} and {notice_str}."
    return reasoning


def main():
    parser = argparse.ArgumentParser(description="Rank candidates for Senior AI Engineer.")
    parser.add_argument("--candidates", required=True, help="Path to candidates.jsonl file.")
    parser.add_argument("--out", required=True, help="Path to save ranked CSV file.")
    args = parser.parse_args()
    
    candidates_path = Path(args.candidates)
    out_path = Path(args.out)
    
    if not candidates_path.exists():
        print(f"Error: {candidates_path} does not exist.")
        return
        
    ranked_candidates = []
    
    # Helper to process a single candidate and update top 100 list
    def process_candidate(candidate):
        cid = candidate.get("candidate_id")
        
        # Anomaly / Honeypot filtering
        honeypot, reason = is_honeypot(candidate)
        if honeypot:
            return
            
        # Score features
        title_score = get_title_score(candidate)
        if title_score == 0.0:
            return
            
        yoe = candidate.get("profile", {}).get("years_of_experience", 0.0)
        yoe_score = get_yoe_score(yoe)
        if yoe_score == 0.0:
            return
            
        company_score = get_company_score(candidate)
        skills_score = get_skills_score(candidate)
        location_score = get_location_score(candidate)
        
        # Calculate base score (weighted sum)
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
        
        # We only keep candidate in memory if it makes it to top 100
        # Check if list has < 100 elements or score is better than the 100th element
        nonlocal ranked_candidates
        if len(ranked_candidates) < 100 or final_score > ranked_candidates[-1]["score"] or (final_score == ranked_candidates[-1]["score"] and cid < ranked_candidates[-1]["candidate_id"]):
            ranked_candidates.append({
                "candidate_id": cid,
                "score": final_score,
                "candidate_obj": candidate
            })
            # Sort by score descending, then by candidate_id ascending
            ranked_candidates.sort(key=lambda x: (-x["score"], x["candidate_id"]))
            # Keep only top 100
            ranked_candidates = ranked_candidates[:100]

    # Load candidates (support both JSON array and JSONL)
    if candidates_path.suffix.lower() == ".json":
        with open(candidates_path, "r", encoding="utf-8") as f:
            try:
                candidates_list = json.load(f)
                for candidate in candidates_list:
                    process_candidate(candidate)
            except json.JSONDecodeError as e:
                print(f"Error reading JSON array: {e}")
                return
    else:
        with open(candidates_path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                if not line.strip():
                    continue
                try:
                    candidate = json.loads(line)
                    process_candidate(candidate)
                except json.JSONDecodeError as e:
                    print(f"Skipping line {idx} due to JSON decode error: {e}")
                    continue
            
    # Take top 100
    top_100 = ranked_candidates
    
    # Generate CSV output
    with open(out_path, "w", encoding="utf-8", newline="") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(["candidate_id", "rank", "score", "reasoning"])
        
        for rank_idx, entry in enumerate(top_100, 1):
            cid = entry["candidate_id"]
            score = entry["score"]
            candidate_obj = entry["candidate_obj"]
            
            reasoning = generate_reasoning(candidate_obj, score)
            writer.writerow([cid, rank_idx, f"{score:.4f}", reasoning])
            
    print(f"Successfully ranked candidates and wrote top 100 to {out_path}.")

if __name__ == "__main__":
    main()
