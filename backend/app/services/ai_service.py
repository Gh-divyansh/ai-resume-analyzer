import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
import json


# ---------------------------------------------------------
# Load environment variables
# ---------------------------------------------------------

load_dotenv()


# ---------------------------------------------------------
# Gemini API Key
# ---------------------------------------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is missing. "
        "Make sure it exists in backend/.env"
    )


# ---------------------------------------------------------
# Gemini Client
# ---------------------------------------------------------

client = genai.Client(
    api_key=GEMINI_API_KEY
)


# ---------------------------------------------------------
# Resume AI Extraction
# ---------------------------------------------------------

def extract_resume_data(resume_text: str):

    prompt = f"""
You are an AI resume parser.

Analyze the following resume and extract structured information.

Return ONLY valid JSON.

The JSON must have exactly this structure:

{{
    "name": "",
    "title": "",
    "summary": "",
    "skills": [],
    "experience": [],
    "education": [],
    "projects": []
}}

Rules:

1. name:
   Extract the candidate's full name.

2. title:
   Extract the candidate's primary/current professional title.

3. summary:
   Write a short professional summary based only on the resume.

4. skills:
   Return a list of technical and professional skills.

5. experience:
   Return a list of objects.

   Each experience object should contain:

   {{
       "company": "",
       "role": "",
       "duration": "",
       "responsibilities": []
   }}

6. education:
   Return a list of objects.

   Each education object should contain:

   {{
       "degree": "",
       "institution": "",
       "duration": ""
   }}

7. projects:
   Return a list of objects.

   Each project object should contain:

   {{
       "name": "",
       "description": ""
   }}

8. Do not invent information.

9. If information is missing, return an empty string or empty list.

Resume:

----------------------------

{resume_text}

----------------------------
"""

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        ),
    )

    if response.parsed:
        return response.parsed

    return json.loads(response.text)