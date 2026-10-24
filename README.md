# 🎓 Excel AI Coach - Cloud-Native AI Platform
**Excel Educational Institute | Intelligent Exam Coach for CA, CS, and CMA Exams**

[![Cloud Backend](https://img.shields.io/badge/Render-Live_Cloud_Backend-46E3B7?style=flat-square&logo=render)](https://excel-ai-backend-yegx.onrender.com)
[![Vector DB](https://img.shields.io/badge/Pinecone-Serverless_Cloud_AWS-000000?style=flat-square&logo=pinecone)](https://pinecone.io)
[![AI Engine](https://img.shields.io/badge/Google_Gemini-Multi--Model_Failover-4285F4?style=flat-square&logo=google)](https://ai.google.dev/)
[![Mobile App](https://img.shields.io/badge/React_Native-Expo_ChatGPT_UI-61DAFB?style=flat-square&logo=react)](https://expo.dev)

Excel AI is an enterprise-grade AI exam preparation platform custom-built for **Excel Educational Institute**. It provides real-time doubt solving, handwritten answer paper checking with step marks, MCQ generation, and study material ingestion grounded in coaching notes via Retrieval-Augmented Generation (RAG).

---

## 🏗️ System Architecture

The entire platform runs **100% cloud-native**, meaning zero data or vector indexes are locked to a single local machine. You can seamlessly switch between home, office, and production environments:

```
                         ┌──────────────────────────────────────────────┐
                         │              STUDENT CLIENTS                 │
                         ├──────────────────────┬───────────────────────┤
                         │  Web App (ChatGPT UI)│ Mobile App (Expo Go)  │
                         │  https://...onrender │ iOS & Android Standalone
                         └──────────┬───────────┴───────────┬───────────┘
                                    │                       │
                                    ▼                       ▼
                         ┌──────────────────────────────────────────────┐
                         │        RENDER CLOUD BACKEND (FastAPI)        │
                         │    https://excel-ai-backend-yegx.onrender.com│
                         └──────────────┬───────────────────┬───────────┘
                                        │                   │
                     Semantic Queries   ▼                   ▼  Exam Solutions
                         ┌──────────────────────┐   ┌──────────────────────┐
                         │ PINECONE VECTOR DB   │   │  GOOGLE GEMINI AI    │
                         │ AWS Serverless us-east│   │  Multi-Model Failover│
                         │ 768-dim Embeddings   │   │  flash-lite / flash  │
                         └──────────────────────┘   └──────────────────────┘
```

1. **AI Inference Engine:** Google Gemini with dynamic multi-model failover (`gemini-flash-lite-latest` ➔ `gemini-flash-latest` ➔ `gemini-pro-latest`) to eliminate 503 capacity spikes and deliver answers in **< 4.5 seconds**.
2. **Cloud Vector Database:** Pinecone Serverless Cloud on AWS (`us-east-1`), 768 dimensions with cosine similarity, powered by Google's `gemini-embedding-001`.
3. **Continuous Deployment Server:** Render Cloud container auto-building from GitHub `main` branch.
4. **Student Experience (`/`):** Pure ChatGPT-style interface with camera attachment for answer sheets, audio voice queries, and zero technical clutter.
5. **Study Material Manager (`/admin`):** Dedicated portal for faculty to upload PDFs and `.zip` archives directly to the vector cloud.
6. **Mobile App (`excel-ai-mobile/`):** Standalone React Native (Expo) app replicating the ChatGPT mobile experience.

---

## 🖥️ Setting Up on a New Machine (e.g., Office PC)

When moving from your Home PC to your Office PC (or setting up a collaborator), follow this 3-minute setup guide:

### Prerequisites
* **Python 3.10+** ([python.org](https://www.python.org/downloads/)) - *Make sure "Add Python to PATH" is checked during installation.*
* **Git** ([git-scm.com](https://git-scm.com/)) - *Optional: you can also download as a ZIP.*
* **Node.js LTS** ([nodejs.org](https://nodejs.org/)) - *Only required if you want to run the React Native mobile app locally.*

---

### Step 1: Clone or Download the Repository

Open Command Prompt or PowerShell on your Office PC:
```bash
git clone https://github.com/vaibhavdubey61/excel-ai-backend.git
cd excel-ai-backend
```
*(If Git is not installed, download the repository ZIP directly from GitHub and extract it).*

---

### Step 2: Configure Environment Variables (`.env`)

In the root of the project, create a file named **`.env`** (you can copy `.env.example` as a template):

```bash
# On Windows CMD
copy .env.example .env
```

Open `.env` in Notepad or VS Code and configure the 4 keys:

```env
GEMINI_API_KEY=your_gemini_api_key_here
PINECONE_API_KEY=your_pinecone_api_key_here
PINECONE_INDEX_HOST=https://excel-ai-materials-dlalmyk.svc.aped-4627-b74a.pinecone.io
PORT=8000
```

> **Why is `.env` not in GitHub?**
> The `.env` file is git-ignored to protect your API credentials from being publicly exposed.

---

### Step 3: Run the 1-Click Setup Wizard

Double-click the setup batch file in the project folder:
📁 **`setup_new_pc.bat`**

This automated script will:
1. Upgrade `pip` and install all required Python libraries from `requirements.txt`.
2. Verify the presence of your `.env` configuration file.
3. Automatically install Expo/React Native mobile packages in `excel-ai-mobile/` if Node.js is present.

---

## 🌲 Pinecone Cloud Vector Database Details

You do **not** need to recreate the Pinecone database on your Office PC. It is hosted permanently in the cloud:

| Parameter | Configuration | Purpose |
| :--- | :--- | :--- |
| **Index Name** | `excel-ai-materials` | Main institute vector index |
| **Cloud Provider** | **AWS (Serverless)** | Zero server maintenance, instant scale |
| **Region** | `us-east-1` (N. Virginia) | Low-latency serverless tier |
| **Vector Dimensions** | **768** | Exact match with Google Gemini embeddings |
| **Distance Metric** | **Cosine** | Optimal semantic similarity matching |
| **Index Host URL** | `https://excel-ai-materials-dlalmyk.svc.aped-4627-b74a.pinecone.io` | Cloud query and upsert endpoint |

Because Pinecone is cloud-native, any PDF uploaded from your **Home PC**, your **Office PC**, or the **Web Admin Portal** is stored in the same global index. All students immediately get answers from it.

---

## 🚀 Running the Apps Locally on Office PC

Once setup is complete, you have 1-click batch scripts for every workflow:

### 1. Run the Local Web Server
Double-click:
📁 **`run_web_local.bat`**
* **Student Chat App:** `http://localhost:8000/`
* **Study Material Manager:** `http://localhost:8000/admin`
* **Health Check Endpoint:** `http://localhost:8000/api/health`

### 2. Run the Mobile App (Expo Go)
Double-click:
📁 **`run_mobile_app.bat`**
1. Install **Expo Go** from [Google Play Store](https://play.google.com/store/apps/details?id=host.exp.exponent) or [Apple App Store](https://apps.apple.com/app/expo-go/id982107449).
2. Scan the displayed terminal QR code with your phone camera or Expo Go.
3. The ChatGPT-style Excel AI mobile app will launch natively on your phone.

### 3. Batch-Upload Study Materials (`.zip` or `.pdf`)
Double-click:
📁 **`upload_zip.bat`**
* Drag and drop any `.zip` archive containing coaching PDFs into the terminal window.
* The script automatically unzips the files, extracts syllabus chunks, detects subjects (e.g. *Taxation, Corporate Law, Costing, Auditing*), generates Gemini embeddings, and upserts them directly to Pinecone Cloud.

---

## 🌐 Live Production Cloud Endpoints

The backend is permanently deployed on the cloud and running 24/7:

* **Live Student AI Chat:** [https://excel-ai-backend-yegx.onrender.com](https://excel-ai-backend-yegx.onrender.com)
* **Live Study Material Portal:** [https://excel-ai-backend-yegx.onrender.com/admin](https://excel-ai-backend-yegx.onrender.com/admin)
* **Backend Health Check:** [https://excel-ai-backend-yegx.onrender.com/api/health](https://excel-ai-backend-yegx.onrender.com/api/health)

---

## 🔄 Office PC <-> Home PC Synchronization Workflow

To ensure smooth switching between your home and office workstations:

1. **Before leaving a PC:**
   Commit and push any code changes:
   ```bash
   git add .
   git commit -m "Description of changes"
   git push origin main
   ```
   *(Render will automatically build and deploy your new changes to the cloud within 60 seconds).*

2. **When arriving at the other PC:**
   Pull the latest updates:
   ```bash
   git pull origin main
   ```

---

## 📂 Project Directory Structure

```
excel-ai-backend/
├── app.py                      # Core FastAPI backend, routing & endpoints
├── ai_service.py               # Gemini multi-model failover engine
├── cloud_vector_store.py       # Pinecone Serverless Cloud vector store integration
├── rag_engine.py               # Local vector fallback search matrix
├── ingest_materials.py         # Batch PDF & ZIP extraction and ingestion script
├── requirements.txt            # Python production dependencies
├── Dockerfile                  # Production container for Render deployment
├── .env.example                # Template for cloud API keys
├── setup_new_pc.bat            # 1-Click setup wizard for new/office machines
├── run_web_local.bat           # 1-Click local FastAPI server runner
├── run_mobile_app.bat          # 1-Click Expo Go mobile bundler runner
├── upload_zip.bat              # 1-Click batch ZIP study material uploader
├── static/
│   ├── index.html              # Clean ChatGPT-style Student interface
│   └── admin.html              # Drag-and-drop Study Material Cloud Portal
└── excel-ai-mobile/            # Standalone React Native Expo application
    ├── App.js                  # ChatGPT dark-themed mobile app with sidebar
    └── package.json            # Mobile React Native dependencies
```

---

## 👥 Support & Institute Info
**Excel Educational Institute**  
*Excellence in CA, CS, and CMA Coaching*
