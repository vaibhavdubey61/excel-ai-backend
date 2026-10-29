"""
Excel AI Coach - Video & Teaching Lecture Analysis Service.
Enables students to share teaching video links (e.g. YouTube) or video/audio clips,
generates comprehensive exam-focused lecture summaries (without timestamps),
and grounds the chat session so students can resolve doubts directly from the video.
"""
import re
import os
from typing import Optional, Tuple, Dict, Any
from youtube_transcript_api import YouTubeTranscriptApi
import httpx

# Session store mapping session_id -> { "video_id": ..., "title": ..., "author": ..., "transcript": ..., "summary": ... }
VIDEO_SESSION_STORE: Dict[str, Dict[str, Any]] = {}

YOUTUBE_REGEXES = [
    r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?(?:.*&)?v=([0-9A-Za-z_-]{11})',
    r'(?:https?:\/\/)?(?:www\.)?youtu\.be\/([0-9A-Za-z_-]{11})',
    r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/shorts\/([0-9A-Za-z_-]{11})',
    r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/live\/([0-9A-Za-z_-]{11})',
    r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/embed\/([0-9A-Za-z_-]{11})'
]

def extract_youtube_video_id(text: str) -> Optional[str]:
    """Extracts YouTube 11-char video ID from text or returns None."""
    if not text:
        return None
    for pattern in YOUTUBE_REGEXES:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return None

def fetch_youtube_metadata(video_id: str) -> Dict[str, Any]:
    """Fetches video title, channel/author name, and thumbnail via YouTube's public oEmbed API."""
    if not video_id:
        return {}
    try:
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "title": data.get("title", ""),
                    "author_name": data.get("author_name", "Excel Educational Institute"),
                    "thumbnail_url": data.get("thumbnail_url", "")
                }
    except Exception as e:
        print(f"[YouTube oEmbed Error]: {e}")
    return {}

def fetch_youtube_transcript_text(video_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Fetches the full spoken transcript of a YouTube teaching video without timestamps.
    Returns (transcript_text, error_message).
    """
    try:
        api = YouTubeTranscriptApi()
        # 1. Try common languages first
        languages_priority = ['en', 'hi', 'en-IN', 'hi-Latn']
        try:
            fetched = api.fetch(video_id, languages=languages_priority)
            raw_entries = fetched.to_raw_data()
        except Exception:
            # 2. Fall back to listing all available transcripts (including auto-generated)
            transcript_list = api.list(video_id)
            transcript = next(iter(transcript_list))
            fetched = transcript.fetch()
            raw_entries = fetched.to_raw_data()

        # Join spoken words into clean continuous prose with ZERO TIMESTAMPS
        clean_chunks = []
        for item in raw_entries:
            text = (item.get("text") or "").strip()
            # Remove music/sound effect brackets like [Music], [Applause]
            text = re.sub(r'\[.*?\]', '', text).strip()
            if text:
                clean_chunks.append(text)

        full_transcript = " ".join(clean_chunks)
        if len(full_transcript) < 30:
            return None, "The video captions appear to be empty."
        return full_transcript, None

    except Exception as e:
        err_msg = str(e)
        if "Subtitles are disabled" in err_msg:
            return None, "Captions are disabled on this video by the creator."
        elif "Video unavailable" in err_msg:
            return None, "This video is private or unavailable."
        return None, f"Could not retrieve direct video captions ({err_msg[:80]})."

def clean_video_summary(text: str) -> str:
    """Post-processes the generated summary to strip any accidental timestamps or time ranges."""
    if not text:
        return ""
    # Strip patterns like `[00:00 - 05:20]`, `(12:34)`, `00:00 - `, `At 14:20: `
    cleaned = re.sub(r'\[?\b\d{1,2}:\d{2}(?::\d{2})?\b\s*(?:-|to)?\s*(?:\b\d{1,2}:\d{2}(?::\d{2})?\b)?\]?\s*:?', '', text)
    cleaned = re.sub(r'\bat\s+\d{1,2}:\d{2}\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\bminute\s+\d+\b', '', cleaned, flags=re.IGNORECASE)
    # Remove empty markdown bullet lines left by removed timestamps
    cleaned = re.sub(r'\n\s*[-*•]\s*\n', '\n', cleaned)
    return cleaned.strip()

def format_video_summary_prompt(transcript_text: str, course: str = "CA", level: str = "Inter", student_note: str = "", video_title: str = "") -> str:
    """Builds a high-yield academic lecture summary prompt with strict zero-timestamp enforcement."""
    trimmed_transcript = transcript_text[:120000]

    title_clause = f"Video Title: \"{video_title}\"\n" if video_title else ""

    prompt = f"""You are a senior commerce faculty mentor at Excel Educational Institute guiding a {course} {level} student.
A student has shared an educational teaching/lecture video. {title_clause}Below is the spoken transcript of the lecture.

Your task is to analyze what the faculty taught and provide an authoritative, high-yield **Lecture Teaching Summary** so the student can master the topic and ask questions or doubts.

CRITICAL FORMATTING INSTRUCTIONS (STRICT):
1. **DO NOT INCLUDE ANY TIMESTAMPS, TIME CODES, OR SECOND/MINUTE MARKERS** (e.g. NEVER write "00:00", "[12:30]", "At 15:40", "Minute 25", etc.). Present the summary purely as an academic teaching brief.
2. Structure your response clearly using the exact markdown format below:

---
### 📌 Lecture Overview & Topic
- **Subject & Topic:** [Identify the exact subject and topic, e.g. Corporate Law - Section 135 CSR, or Advanced Accounts - Ind AS 115]
- **Core Objective:** [What this lecture aims to teach the student for their exam]

### ⚖️ Applicable Statutory Provisions, Standards & Formulas
- [List every relevant Section of the Companies Act / Income Tax Act, Accounting Standard (AS/Ind AS), Standards on Auditing (SA), or financial mathematical formula explained by the faculty]

### 🧠 Core Concepts & Principles Taught
- [Breakdown of key legal principles, accounting rules, or conceptual steps taught in the lecture in clear bullet points]

### 📝 Practical Illustrations & Case Scenarios Solved
- [Step-by-step summary of the practical numerical sums or legal case studies the faculty worked through in the lecture, including the final conclusion reached]

### ⚠️ Crucial Exam Warnings & Faculty Pitfalls
- [Specific student mistakes, tricky points, or examiner traps that the faculty highlighted in the video]

### 💡 Key Takeaways for Quick Revision
- [3-5 crisp bullet points capturing the most important exam-worthy points for quick student recall]

### ❓ Suggested Doubts You Can Ask Me
- [Provide 3 insightful, high-value questions about this lecture that the student can tap or type to test their depth of understanding]
---

Student's Query / Note: {student_note if student_note else "Please provide a comprehensive summary of this lecture so I can ask doubts."}

SPOKEN LECTURE TRANSCRIPT:
\"\"\"
{trimmed_transcript}
\"\"\"
"""
    return prompt

def format_video_metadata_summary_prompt(
    video_id: str,
    title: str,
    author: str = "Excel Educational Institute",
    course: str = "CA",
    level: str = "Inter",
    student_note: str = ""
) -> str:
    """Builds an academic lecture summary prompt based on the verified video title, author, and exam syllabus when direct transcripts are unavailable."""
    prompt = f"""You are a senior commerce faculty mentor at Excel Educational Institute guiding a {course} {level} student.
The student has shared an official educational teaching lecture from {author}:
**Lecture Video:** "{title}" (YouTube ID: {video_id})

Your task is to analyze this teaching lecture topic and deliver an authoritative, high-yield **Lecture Teaching Summary** according to ICAI / ICSI / ICMAI exam presentation standards.

CRITICAL FORMATTING INSTRUCTIONS (STRICT):
1. **DO NOT INCLUDE ANY TIMESTAMPS, TIME CODES, OR SECOND/MINUTE MARKERS** (e.g. NEVER write "00:00", "[12:30]", "At 15:40", "Minute 25", etc.). Present the summary purely as an academic teaching brief.
2. Structure your response clearly using the exact markdown format below:

---
### 📌 Lecture Overview & Topic
- **Subject & Topic:** {title}
- **Faculty / Institute:** {author}
- **Core Objective:** [Explain what this lecture teaches the student for their {course} {level} exam]

### ⚖️ Applicable Statutory Provisions, Standards & Formulas
- [List every relevant Section of the Companies Act / Income Tax Act, Accounting Standard (AS/Ind AS), Standards on Auditing (SA), or financial mathematical formula associated with this topic]

### 🧠 Core Concepts & Principles Taught
- [Breakdown of key legal principles, presentation guidelines, or conceptual steps taught in the lecture in clear bullet points]

### 📝 Practical Illustrations & Presentation Techniques
- [Step-by-step guidance on how to write answers, step-wise mark allocations, working notes, and presentation methods taught in this lecture]

### ⚠️ Crucial Exam Warnings & Faculty Pitfalls
- [Specific student mistakes, examiner traps, and keyword omission penalties that faculty highlight on this topic]

### 💡 Key Takeaways for Quick Revision
- [3-5 crisp bullet points capturing the most important exam-worthy points for quick student recall]

### ❓ Suggested Doubts You Can Ask Me
- [Provide 3 insightful, high-value questions about this lecture that the student can tap or type to test their depth of understanding]
---

Student's Query / Note: {student_note if student_note else "Please provide a comprehensive summary of this lecture so I can ask doubts."}
"""
    return prompt

def store_video_session(session_id: str, video_id: str, transcript: str, summary: str, title: str = "", author: str = ""):
    """Saves the video context for subsequent doubt answering."""
    if session_id:
        VIDEO_SESSION_STORE[session_id] = {
            "video_id": video_id,
            "title": title,
            "author": author,
            "transcript": transcript,
            "summary": summary
        }

def get_video_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves the active video context for a chat session."""
    if not session_id:
        return None
    return VIDEO_SESSION_STORE.get(session_id)
