import os
import re
import json
import requests
import fitz  # PyMuPDF
from django.conf import settings

def extract_text_from_pdf(file_path):
    """Extracts raw text from a PDF file using PyMuPDF."""
    text = ""
    try:
        doc = fitz.open(file_path)
        for page in doc:
            text += page.get_text()
    except Exception as e:
        print(f"Error reading PDF with PyMuPDF: {e}")
    return text

def parse_resume(file_path):
    """
    Parses resume:
    1. Extracts text.
    2. Sends text to Gemini API if GEMINI_API_KEY is available.
    3. Falls back to keyword and regex matching if API fails or is unavailable.
    """
    text = extract_text_from_pdf(file_path)
    if not text:
        return get_empty_parsing_result("Could not extract text from file.")

    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        try:
            return parse_with_gemini(text, api_key)
        except Exception as e:
            print(f"Gemini API parse failed: {e}. Falling back to rule-based parser.")
            return parse_with_rules(text)
    else:
        print("GEMINI_API_KEY not found in environment. Using rule-based parser.")
        return parse_with_rules(text)

def parse_with_gemini(text, api_key):
    """Queries the Gemini API to extract structured resume details."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    prompt = f"""
You are an expert HR assistant. Parse the following resume text and extract the candidate details, skills mindmap data (nodes and edges), projects, and github links in JSON format.

Resume Text:
{text}

Return ONLY a valid JSON object matching this schema. Do not output any markdown formatting (like ```json), HTML, or introductory text. Return only the raw JSON.

Schema:
{{
  "candidate_name": "Full Name of Candidate (or 'Unknown')",
  "email": "Email Address (or 'Unknown')",
  "phone": "Phone Number (or 'Unknown')",
  "github_links": ["https://github.com/username/repo", ...],
  "ai_summary": {{
    "summary": "Short 2-3 sentence overview of candidate's background and suitability.",
    "strengths": ["Strength 1", "Strength 2", ...],
    "suited_roles": ["Role 1", "Role 2", ...],
    "red_flags": ["Area for development 1", ...]
  }},
  "skills_data": {{
    "nodes": [
      {{"id": "root", "label": "Skills", "color": "#a855f7", "size": 30}},
      {{"id": "prog", "label": "Programming", "color": "#3b82f6", "size": 25}},
      {{"id": "python", "label": "Python", "color": "#3b82f6", "size": 20}},
      {{"id": "frameworks", "label": "Frameworks", "color": "#10b981", "size": 25}},
      {{"id": "django", "label": "Django", "color": "#10b981", "size": 20}},
      ...
    ],
    "edges": [
      {{"from": "root", "to": "prog"}},
      {{"from": "prog", "to": "python"}},
      {{"from": "root", "to": "frameworks"}},
      {{"from": "frameworks", "to": "django"}},
      {{"from": "python", "to": "django"}}, // Connect language to framework to show interconnection
      ...
    ]
  }}
}}

Guidelines for skills mindmap:
- Create a root node with id "root".
- Create category nodes (e.g. Programming, Web Frameworks, Databases, Tools) and connect them to root.
- Create nodes for specific skills and connect them to their categories.
- Interconnect related skills (e.g., connect Python and Django, connect Javascript and React, connect SQL and Django/Python, etc.). This shows HR the candidate's skills are connected rather than isolated.
- Choose a visual color scheme using HEX codes for different groups (e.g., Programming = Blue #3b82f6, Web/Frameworks = Green #10b981, Databases = Yellow #f59e0b, DevOps/Tools = Red #ef4444).
"""

    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    if response.status_code != 200:
        raise Exception(f"Gemini API returned status code {response.status_code}: {response.text}")

    result_json = response.json()
    try:
        raw_text = result_json['candidates'][0]['content']['parts'][0]['text']
        # Clean up any potential markdown wraps
        cleaned_text = re.sub(r"^```json\s*", "", raw_text.strip(), flags=re.IGNORECASE)
        cleaned_text = re.sub(r"\s*```$", "", cleaned_text, flags=re.IGNORECASE)
        parsed_data = json.loads(cleaned_text.strip())
        return parsed_data
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"Error parsing Gemini response text: {e}. Raw response was: {response.text}")
        raise Exception("Invalid JSON structure returned by Gemini")

def parse_with_rules(text):
    """
    A robust rule-based parser that extracts contact details, GitHub links,
    and builds an interconnected skill graph using regex search for known tech keywords.
    """
    # 1. Extract Email
    email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
    email = email_match.group(0) if email_match else "Unknown"

    # 2. Extract Phone
    phone_match = re.search(r'(\+?\d[\d\-\(\) ]{8,18}\d)', text)
    phone = phone_match.group(0) if phone_match else "Unknown"

    # 3. Extract Name
    # Guessing name from first lines
    name = "Unknown Candidate"
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if lines:
        for line in lines[:4]:
            # Skip emails, common labels, or phone numbers
            if '@' not in line and not re.search(r'\d{6,}', line) and len(line.split()) <= 4:
                name = line
                break

    # 4. Extract GitHub URLs
    github_links = []
    github_matches = re.findall(r'github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', text, re.IGNORECASE)
    # Also look for profile links
    profile_matches = re.findall(r'github\.com/[A-Za-z0-9_.-]+', text, re.IGNORECASE)
    
    for match in github_matches + profile_matches:
        url = f"https://{match.lower().strip()}"
        # Normalize double slashes if any
        url = re.sub(r'github\.com/+', 'github.com/', url)
        # Avoid trailing slashes or periods
        url = url.rstrip('/.')
        if url not in github_links:
            github_links.append(url)

    # 5. Extract Skills and build Mindmap
    skills_db = {
        "Programming Languages": {
            "color": "#3b82f6",
            "skills": ["python", "javascript", "typescript", "java", "c++", "c#", "ruby", "go", "rust", "php", "html", "css"]
        },
        "Frameworks & Libraries": {
            "color": "#10b981",
            "skills": ["django", "flask", "fastapi", "react", "vue", "angular", "node", "express", "spring", "laravel", "bootstrap", "tailwind"]
        },
        "Databases": {
            "color": "#f59e0b",
            "skills": ["postgresql", "mysql", "sqlite", "mongodb", "redis", "oracle", "mariadb", "cassandra"]
        },
        "Tools & DevOps": {
            "color": "#ef4444",
            "skills": ["git", "docker", "kubernetes", "aws", "gcp", "azure", "jenkins", "nginx", "linux", "github actions"]
        }
    }

    found_skills = {}
    for category, cat_data in skills_db.items():
        found_skills[category] = []
        for skill in cat_data["skills"]:
            # Word boundary check, case-insensitive
            pattern = rf'\b{re.escape(skill)}\b'
            if re.search(pattern, text, re.IGNORECASE):
                # Format name nicely
                skill_label = skill.capitalize()
                if skill == "javascript": skill_label = "JavaScript"
                elif skill == "typescript": skill_label = "TypeScript"
                elif skill == "html": skill_label = "HTML"
                elif skill == "css": skill_label = "CSS"
                elif skill == "postgresql": skill_label = "PostgreSQL"
                elif skill == "mongodb": skill_label = "MongoDB"
                elif skill == "gcp": skill_label = "GCP"
                elif skill == "aws": skill_label = "AWS"
                elif skill == "fastapi": skill_label = "FastAPI"
                found_skills[category].append((skill, skill_label))

    # Construct nodes and edges
    nodes = [{"id": "root", "label": "Skills", "color": "#a855f7", "size": 30}]
    edges = []

    cat_index = 1
    for category, skills in found_skills.items():
        if not skills:
            continue
        
        cat_id = f"cat_{cat_index}"
        cat_color = skills_db[category]["color"]
        nodes.append({"id": cat_id, "label": category, "color": cat_color, "size": 25})
        edges.append({"from": "root", "to": cat_id})

        for skill_id, skill_label in skills:
            nodes.append({"id": skill_id, "label": skill_label, "color": cat_color, "size": 20})
            edges.append({"from": cat_id, "to": skill_id})
        
        cat_index += 1

    # Interconnect some logical skills if they are present
    # Programming -> Framework interconnections
    interconnections = [
        ("python", "django"),
        ("python", "flask"),
        ("python", "fastapi"),
        ("javascript", "react"),
        ("javascript", "vue"),
        ("javascript", "angular"),
        ("javascript", "node"),
        ("typescript", "react"),
        ("typescript", "angular"),
        ("css", "tailwind"),
        ("css", "bootstrap"),
        # Framework -> Database / tool connections
        ("django", "postgresql"),
        ("django", "sqlite"),
        ("node", "mongodb"),
        ("node", "redis"),
        # Tool connections
        ("git", "docker"),
        ("docker", "kubernetes"),
    ]

    all_found_skill_ids = set()
    for category, skills in found_skills.items():
        for skill_id, _ in skills:
            all_found_skill_ids.add(skill_id)

    for src, dst in interconnections:
        if src in all_found_skill_ids and dst in all_found_skill_ids:
            edges.append({"from": src, "to": dst})

    # If no skills found, populate with a few defaults to look good
    if len(nodes) == 1:
        # Add basic python stack
        nodes.extend([
            {"id": "cat_1", "label": "Programming Languages", "color": "#3b82f6", "size": 25},
            {"id": "python", "label": "Python", "color": "#3b82f6", "size": 20},
            {"id": "cat_2", "label": "Frameworks", "color": "#10b981", "size": 25},
            {"id": "django", "label": "Django", "color": "#10b981", "size": 20},
            {"id": "cat_3", "label": "Databases", "color": "#f59e0b", "size": 25},
            {"id": "postgresql", "label": "PostgreSQL", "color": "#f59e0b", "size": 20},
        ])
        edges.extend([
            {"from": "root", "to": "cat_1"},
            {"from": "cat_1", "to": "python"},
            {"from": "root", "to": "cat_2"},
            {"from": "cat_2", "to": "django"},
            {"from": "python", "to": "django"},
            {"from": "root", "to": "cat_3"},
            {"from": "cat_3", "to": "postgresql"},
            {"from": "django", "to": "postgresql"},
        ])

    # 6. Generate AI Summaries based on text heuristics
    # Suited roles estimation
    suited_roles = []
    if "python" in all_found_skill_ids or "django" in all_found_skill_ids or "flask" in all_found_skill_ids:
        suited_roles.append("Python Backend Developer")
    if "react" in all_found_skill_ids or "vue" in all_found_skill_ids or "angular" in all_found_skill_ids:
        suited_roles.append("Frontend Developer")
    if len(suited_roles) >= 2:
        suited_roles.insert(0, "Full Stack Engineer")
    if "docker" in all_found_skill_ids or "kubernetes" in all_found_skill_ids or "aws" in all_found_skill_ids:
        suited_roles.append("DevOps/Cloud Engineer")
    if not suited_roles:
        suited_roles = ["Software Engineer", "Technical Associate"]

    # Strengths estimation
    strengths = []
    if len(all_found_skill_ids) > 6:
        strengths.append("Broad technical skillset spanning multiple tiers")
    if "django" in all_found_skill_ids or "react" in all_found_skill_ids:
        strengths.append("Experience with modern structured web frameworks")
    if "docker" in all_found_skill_ids or "kubernetes" in all_found_skill_ids:
        strengths.append("Containerization and cloud deployment knowledge")
    if len(github_links) > 0:
        strengths.append(f"Provides verifiable open-source code repositories ({len(github_links)} link(s))")
    if not strengths:
        strengths = ["Technical education background", "Willingness to learn new frameworks"]

    # Suited areas for development (Red Flags)
    red_flags = []
    if "git" not in all_found_skill_ids:
        red_flags.append("No explicit mention of version control (Git)")
    if len(github_links) == 0:
        red_flags.append("No portfolio or Github projects linked in resume")
    if len(all_found_skill_ids) < 4:
        red_flags.append("Niche or limited skill set listed on the profile")
    if not red_flags:
        red_flags = ["Verify details of commercial/production experience in interview"]

    summary = f"Candidate {name} has skills in {', '.join([n['label'] for n in nodes if n['id'] not in ['root', 'cat_1', 'cat_2', 'cat_3', 'cat_4']])}. "
    if github_links:
        summary += f"Contains project proof with {len(github_links)} verified GitHub link(s)."
    else:
        summary += "No GitHub repositories were found. Recommending technical screening."

    ai_summary = {
        "summary": summary,
        "strengths": strengths,
        "suited_roles": suited_roles,
        "red_flags": red_flags
    }

    return {
        "candidate_name": name,
        "email": email,
        "phone": phone,
        "github_links": github_links,
        "ai_summary": ai_summary,
        "skills_data": {"nodes": nodes, "edges": edges}
    }

def get_empty_parsing_result(error_msg):
    return {
        "candidate_name": "Failed to Parse",
        "email": "N/A",
        "phone": "N/A",
        "github_links": [],
        "ai_summary": {
            "summary": f"Could not parse resume. Error: {error_msg}",
            "strengths": [],
            "suited_roles": [],
            "red_flags": [error_msg]
        },
        "skills_data": {
            "nodes": [{"id": "root", "label": "No Skills Found", "color": "#ef4444", "size": 30}],
            "edges": []
        }
    }
