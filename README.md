# 🎓 Excel AI Coach - Web App Prototype
**Excel Educational Institute | AI Coach for CA, CS, and CMA Exams**

A specialized AI Coach web prototype designed to demonstrate:
1. **AI Doubt Coach:** Grounded in coaching study materials with ICAI/ICSI/ICMAI exam-standard answer formatting (*Relevant Provisions $\rightarrow$ Facts $\rightarrow$ Analysis $\rightarrow$ Conclusion* / *Working Notes*).
2. **Answer Paper Evaluator (Multimodal):** Upload photos of handwritten answer sheets or typed answers to get step-by-step marks, strengths, critical flaws, and examiner pro-tips.
3. **Interactive MCQ Practice Zone:** Chapter-wise quizzes with timer, negative marking options, and official ICAI-style reasoning.
4. **Knowledge Base (PDF Manager):** Multi-subject repository where coaching institute PDFs (Tax, Law, Accounts, Costing, Auditing) can be uploaded and indexed.
5. **Voice Notes:** Speech-to-text audio input and audio read-aloud playback.

---

## 🚀 Running the Prototype Locally

Open PowerShell in this directory (`c:\Users\lenovo\Documents\Excel`) and run:

```bash
python start_app.py
```

- **Open on your PC:** [http://localhost:8000](http://localhost:8000)
- **Open on any phone / tablet on your Wi-Fi:** Open the local IP shown in the console (e.g., `http://192.168.1.X:8000`).

---

## 🌐 How to Showcase on ANY PC Anywhere in the World

You have two simple options to share this prototype publicly at **₹0 cost**:

### Option 1: Instant Live Public URL (Zero-Setup Tunnel)
Keep `start_app.py` running, and in a second terminal run:
```bash
# Using Cloudflare Tunnel (Free, no login required)
npx cloudflared tunnel --url http://localhost:8000
```
or download the single portable `cloudflared.exe` from Cloudflare:
```bash
cloudflared.exe tunnel --url http://localhost:8000
```
This instantly generates a public HTTPS link (e.g. `https://random-name.trycloudflare.com`) that anyone on any PC or smartphone can open immediately!

---

### Option 2: 24/7 Permanent Free Cloud Link (Hugging Face Spaces)
To have a link that stays live 24/7 even when your laptop is turned off:
1. Create a free account at [huggingface.co](https://huggingface.co).
2. Click **New Space** $\rightarrow$ select **Docker** as SDK $\rightarrow$ choose **Blank**.
3. Push or upload these files (`app.py`, `rag_engine.py`, `ai_service.py`, `static/`, `requirements.txt`, `Dockerfile`) into the Space repository.
4. Your prototype is live at `https://huggingface.co/spaces/<your-username>/excel-ai-coach` forever for free!

---

## 📚 Adding Your Coaching Institute Study Material PDFs

1. Open the web prototype $\rightarrow$ Click on the **Study Materials** tab.
2. Select the subject (e.g. `CA_Inter_Taxation`, `CA_Inter_Corporate_Law`, etc.).
3. Choose your coaching PDF file and click **Upload & Index PDF**.
4. The RAG engine will automatically parse the text, split it into semantic sections, and index it into the search matrix.

---

## 🔑 Activating Live Google Gemini 1.5 Flash AI

The prototype comes with built-in statutory knowledge and exam simulations so it works immediately.
To enable live AI generation and multimodal handwriting recognition:
1. Get a free API key from [Google AI Studio](https://aistudio.google.com/app/apikey) (takes 30 seconds, 100% free tier).
2. Go to the **Share & API** tab in the prototype.
3. Paste the key and click **Save Key**.
