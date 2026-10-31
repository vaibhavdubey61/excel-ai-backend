# 🎓 Excel AI Coach - Cloud-Native Exam Prep Platform
**Excel Educational Institute | Intelligent Exam Coach for CA, CS, and CMA Students**

[![Cloud Backend](https://img.shields.io/badge/Render-Live_Cloud_Backend-46E3B7?style=flat-square&logo=render)](https://excel-ai-backend-yegx.onrender.com)
[![Vector DB](https://img.shields.io/badge/Pinecone-15%2C834_Cloud_Vectors-000000?style=flat-square&logo=pinecone)](https://pinecone.io)
[![CA Inter](https://img.shields.io/badge/CA_Inter-100%25_Indexed_(92%2F92_Ch)-success?style=flat-square)](https://boslive.icai.org)
[![CA Final](https://img.shields.io/badge/CA_Final-65_Chapters_Indexed-blue?style=flat-square)](https://boslive.icai.org)
[![AI Engine](https://img.shields.io/badge/Google_Gemini-Multi--Model_Failover-4285F4?style=flat-square&logo=google)](https://ai.google.dev/)
[![Lecture Video AI](https://img.shields.io/badge/Lecture_Videos-Zero--Timestamp_Summary-rose?style=flat-square)](https://youtube.com)

Excel AI Coach is an enterprise-grade AI exam preparation platform custom-built for **Excel Educational Institute**. It provides real-time level-aware doubt solving, exam-pattern working notes, interactive MCQ practice with instant scoring, handwritten answer sheet checking, and grounded study material ingestion via Retrieval-Augmented Generation (RAG).

---

## 🏠 Home PC Pickup & Testing Guide (Resume & Continue)

When switching back to your **Home PC**, follow these steps:

### 1. Pull Latest Updates from GitHub
```cmd
git pull origin main
```

### 2. Run the Live Verification Suite
We built an automated test runner that verifies all 5 core subsystems in ~15 seconds:
```cmd
python scripts/run_live_suite.py
```
This tests:
* `[Test 1]` Health check (`GET /api/health`)
* `[Test 2]` CA Foundation Chat (`BRS` grounding)
* `[Test 3]` CA Intermediate Chat (`Section 68 Buyback` grounding)
* `[Test 4]` Live Web Research Fallback (`DuckDuckGo` search & synthesis)
* `[Test 5]` Interactive MCQ Generation (`CA Inter Law` 3 MCQs with Pydantic JSON validation)

### 3. Launch Local Server
```cmd
run_web_local.bat
# Or manually:
python -m uvicorn app:app --port 8000
```
* **Student Web Interface:** [http://localhost:8000/](http://localhost:8000/)
* **Study Material & Admin Insights:** [http://localhost:8000/admin](http://localhost:8000/admin)

### 4. ICAI Study Material Ingestion Status & Resuming
* **Ingestion Milestone Reached:** 187 Documents Indexed | 9,626 Pages Processed | **15,834 Cloud Vectors** in Pinecone (`excel-ai-materials`).
* **CA Intermediate (English — May 2026):** **100% COMPLETE (92/92 Chapters)** across all 6 papers:
  - Paper 1 (Advanced Accounting): 10/10 ✅
  - Paper 2 (Corporate & Other Laws): 15/15 ✅
  - Paper 3 (Taxation - Direct Tax & GST): 19/19 ✅
  - Paper 4 (Cost & Management Accounting): 17/17 ✅
  - Paper 5 (Auditing and Ethics): 13/13 ✅
  - Paper 6 (Financial Management & SM): 18/18 ✅
  - Total: **8,776 vectors** live in Pinecone namespace `ca-inter`.
* **CA Final (English — May 2026):** **20 Chapters Indexed** (Paper 1: Financial Reporting covering Ind AS 115, 103, 101, Conceptual Framework, Schedule III Annexure — **1,654 vectors** in namespace `ca-final`).
* **CA Foundation (English):** 30 chapters indexed (**927 vectors** in namespace `ca-foundation`).
* When Google's daily embedding quota resets (at midnight UTC) or with a fresh key in `.env`:
```cmd
# Continue indexing remaining CA Intermediate (English) chapters:
python scripts/ingest_icai_bos.py --preset 3

# Harvest & index CA Final (English) chapters:
python scripts/ingest_icai_bos.py --preset 5

# Index CA Foundation (Hindi Medium):
python scripts/ingest_icai_bos.py --preset 2
```

---

## 🏢 Office PC Pickup Instructions (Fast Sync)

To pull the latest updates and run the platform on your **Office PC**, follow whichever scenario applies:

### ⚡ Scenario 1: If the repository is already cloned on your Office PC
Open Command Prompt or PowerShell in your project folder:
```cmd
git pull origin main
pip install -r requirements.txt
```
To launch the local web server:
```cmd
run_web_local.bat
```
* Student Web Chat: [http://localhost:8000/](http://localhost:8000/)
* Study Material & Insights Portal: [http://localhost:8000/admin](http://localhost:8000/admin)

---

### 📦 Scenario 2: If setting up fresh on your Office PC
```cmd
git clone https://github.com/vaibhavdubey61/excel-ai-backend.git
cd excel-ai-backend
copy .env.example .env
```
1. Open `.env` in Notepad and verify your API keys (`GEMINI_API_KEY`, `PINECONE_API_KEY`, `PINECONE_INDEX_HOST`).
2. Double-click the 1-click setup script:
   📁 **`setup_new_pc.bat`**  
   *(Installs Python packages, verifies configuration, and sets up mobile app packages if Node.js is present)*.
3. Start the server:
   📁 **`run_web_local.bat`**

---

### 🧪 Office PC Verification Commands
Verify that your office PC environment passes all 6 phases:
```cmd
# 1. Run all 39 automated unit & integration tests
python -m unittest discover tests

# 2. Run exam evaluation suite (10 standard CA exam questions across levels)
python scripts/eval_questions.py

# 3. Run Pinecone similarity threshold calibrator
python scripts/calibrate_threshold.py
```

---

## 🏗️ System Architecture & Namespace Routing

Excel AI isolates student courses and levels into distinct Pinecone vector namespaces (`ca-foundation`, `ca-inter`, `ca-final`). Every question is evaluated against the student's level-specific study material before falling back to general knowledge:

```mermaid
flowchart TD
    Student["🎓 Student Client<br/>(Web / Mobile App)"] -->|"Selects Course & Level<br/>(e.g., CA Inter)"| ChatAPI["🚀 FastAPI Backend<br/>(/api/chat or /api/mcq)"]
    
    ChatAPI -->|"Syllabus Validation<br/>(syllabus.py)"| Router{"Valid Course/Level?"}
    Router -->|"No"| Err400["HTTP 400 Bad Request"]
    Router -->|"Yes"| NSMap["Route to Namespace<br/>(e.g., 'ca-inter')"]
    
    NSMap -->|"Embed Query via<br/>gemini-embedding-001"| VectorDB[("🌲 Pinecone Serverless<br/>Namespace: 'ca-inter'")]
    VectorDB -->|"Top-k Chunks with<br/>Cosine Similarity"| Filter{"Score >= MIN_SCORE?<br/>(default 0.62)"}
    
    Filter -->|"Yes: Chunks Found"| GroundedPrompt["Strict Grounded Prompt<br/>(Use ONLY excerpts. If not covered,<br/>output NOT_IN_MATERIAL)"]
    Filter -->|"No: Score < 0.62"| GeneralPrompt["Level-Aware General Knowledge<br/>(Calibrated to Course & Level exam pattern)"]
    
    GroundedPrompt -->|"Gemini Call"| GroundCheck{"Reply starts with<br/>NOT_IN_MATERIAL?"}
    GroundCheck -->|"Yes: Excerpts Incomplete"| GeneralPrompt
    GroundCheck -->|"No: Grounded Answer"| CleanAnswer["Clean Math & Presentation<br/>(Strip raw LaTeX, disclaimers & labels)"]
    
    GeneralPrompt -->|"Gemini Call"| CleanAnswer
    CleanAnswer -->|"Log metadata internally to DB<br/>(Source, Top Score, Latency)"| DB[("🗄️ SQLite / PostgreSQL<br/>(chat_log table)")]
    CleanAnswer -->|"Student-Facing Response<br/>(Reply ONLY - zero leaked labels)"| Student
```

---

## 🔑 Environment Variables Reference

Configure these in your local `.env` file or in your **Render Environment Variables** dashboard:

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | String | *(Required)* | Google Gemini API key for embeddings and multi-model faculty inference. |
| `PINECONE_API_KEY` | String | *(Required)* | Pinecone API key for cloud serverless vector storage. |
| `PINECONE_INDEX_HOST` | URL | *(Required)* | Full HTTPS URL of the Pinecone index (e.g. `https://excel-ai-materials-xxxx.svc.aped-4627-b74a.pinecone.io`). |
| `ADMIN_PASSWORD` | String | `admin123` | Secret password required to access `/admin` and authorize all `/api/admin/*` routes (`X-Admin-Key` header). |
| `DATABASE_URL` | String | `sqlite:///data/app.db` | SQLAlchemy/SQLite connection string for study material catalogs and chat logs. |
| `MIN_SCORE` | Float | `0.62` | Cosine similarity threshold. Chunks below this score are dropped to prevent hallucinated material matching. |
| `PORT` | Integer | `8000` | Port on which the FastAPI application binds. |

> [!IMPORTANT]
> **Render Deployment Persistence:**
> On Render, the container file system is ephemeral and reset on every deploy. To ensure `data/app.db` (containing uploaded book metadata and chat interaction logs) survives deployments:
> 1. Attach a **Render Persistent Disk** mounted at `/data`, OR
> 2. Set `DATABASE_URL` to an external PostgreSQL database (e.g. Supabase or Neon free tier: `postgresql://user:password@host/dbname`).

---

## 📚 Study Material Upload Guide (Admin Portal)

Faculty and administrators manage coaching materials at `/admin` using their `ADMIN_PASSWORD`:

### Upload Rules:
1. **One Course & Level at a Time:** Every PDF or ZIP must be assigned to its target Course (CA, CS, CMA) and Level (Foundation, Inter, Final). This populates the correct Pinecone namespace (e.g. `ca-inter`).
2. **Subject Tagging:** Select the exact subject or paper from the dropdown (populated directly from `syllabus.py`). For ZIP archives, all contained PDFs are indexed under the selected track.
3. **Background Asynchronous Ingestion:** Uploads run as non-blocking FastAPI background tasks. The UI provides real-time polling progress without hitting browser request timeouts.
4. **Scanned PDF OCR Detection:** Pages containing unextractable scanned images are automatically flagged with `⚠️ Needs OCR` in the materials table.
5. **Legacy Namespace Notice:** Old materials uploaded to the default namespace prior to namespace isolation are marked deprecated. Re-upload coaching books under their respective course/level to activate them in student searches.

### Verifying Syllabus Schemes:
The syllabus hierarchy is declared in [`syllabus.py`](syllabus.py). The owner/faculty administrator must verify subjects against current ICAI / ICSI / ICMAI schemes:
* **CA Foundation:** Accounting, Business Laws, Quantitative Aptitude, Business Economics.
* **CA Inter:** Advanced Accounting, Corporate and Other Laws, Taxation, Cost and Management Accounting, Auditing and Ethics, Financial Management and Strategic Management.
* **CA Final:** Financial Reporting, Advanced Financial Management, Advanced Auditing and Professional Ethics, Direct Tax Laws and International Taxation, Indirect Tax Laws, Integrated Business Solutions.
* **CS & CMA:** Placeholder tracks are defined in `syllabus.py` for future module expansion.

---

## ⚡ Setup & Local Development

### 1. Clone & Configure
```bash
git clone https://github.com/vaibhavdubey61/excel-ai-backend.git
cd excel-ai-backend
copy .env.example .env
```
Edit `.env` with your API keys.

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run FastAPI Web Server
```bash
python app.py
```
* **Student Web Interface:** [http://localhost:8000/](http://localhost:8000/)
* **Admin Management & Insights:** [http://localhost:8000/admin](http://localhost:8000/admin)
* **API Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)

### 4. Run Mobile App (Expo Go)
```bash
cd excel-ai-mobile
npm install
npx expo start
```
Scan the QR code with the Expo Go app on iOS or Android.

---

## 🧪 Testing & Quality Assurance

The codebase includes full unit and integration test suites covering all 6 phases:

### Running Unit Tests
```bash
python -m unittest discover tests
```
Runs 39 automated tests across:
* **Phase 1:** Chunk size limits, SQLite database migrations, Gemini API failover & error handling, admin key authentication, rate limiting.
* **Phase 2:** Syllabus hierarchy, namespace resolution, chunk context tagging, OCR detection, asynchronous ingestion jobs.
* **Phase 3:** Student onboarding, 6-turn history management, follow-up query rewriting, image extraction, grounded vs general fallback.
* **Phase 4:** Exam math formatting cleaner (no raw LaTeX), Pydantic MCQ schema validation, 1-retry JSON recovery, namespace queries.
* **Phase 5:** Admin analytics calculation, gap identification (queries below `MIN_SCORE`), CSV chat log export.
* **Phase 6:** Complete integration checks, zero student disclaimer leakage, end-to-end admin authentication verification.

### Running Threshold Calibrator
```bash
python scripts/calibrate_threshold.py
```
Compares 10 in-syllabus CA questions against 10 out-of-syllabus questions against Pinecone to compute the mathematical optimal separation threshold for `MIN_SCORE`.

### Running Exam Question Evaluator
```bash
python scripts/eval_questions.py
```
Runs 10 standard CA examination questions across Foundation, Inter, and Final through the chat engine and verifies:
* Non-empty complete responses
* Zero banned disclaimers or leaked scores
* Zero raw LaTeX math glitches (`$$`, `\text`, etc.)
* Single-turn completeness without prompts to "continue"

---

## 📱 Features Summary

* **Level-Aware Faculty Coach:** Speaks with authoritative warmth calibrated specifically to the student's course and level.
* **Single-Turn Completeness:** Delivers complete statutory provisions and working notes without asking the student to "continue".
* **Clean Indian Commerce Notation:** Formats math and variance formulas cleanly (`₹`, `×`, `[]`) without raw LaTeX artifacts.
* **Teaching Lecture Video Summarization & Doubt Solving:** Students can paste any educational YouTube lecture URL into the chat. The AI Coach extracts the spoken transcript, generates a structured exam summary (**strictly zero timestamps or time codes**), and preserves the lecture context so students can ask follow-up doubts directly about what the faculty taught.
* **Interactive MCQ Drill Modal:** 5, 10, or 15 question tests with hidden answers, immediate per-question reasoning, and summary review filters ("All" vs "Mistakes Only").
* **Admin Telemetry & Gaps Detection:** Visualizes student inquiry volumes, material match percentages, average latencies, and material gaps for continuous curriculum enhancement.

---

## 👥 Support & Institute Info
**Excel Educational Institute**  
*Excellence in CA, CS, and CMA Coaching*
