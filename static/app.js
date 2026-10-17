// Global State
let currentTab = 'doubt';
let isListening = false;
let recognition = null;
let currentMCQData = null;
let currentMCQIndex = 0;
let userScore = 0;
let selectedOptionState = {};

// Initialize Lucide icons on start
document.addEventListener("DOMContentLoaded", () => {
    lucide.createIcons();
    loadStats();
    initSpeechRecognition();
});

// Switch Tabs
function switchTab(tabId) {
    currentTab = tabId;

    // Desktop tab buttons
    document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
    const activeDesktopBtn = document.getElementById(`tab-btn-${tabId}`);
    if (activeDesktopBtn) activeDesktopBtn.classList.add("active");

    // Mobile tab buttons
    document.querySelectorAll("[id^='mob-tab-']").forEach(btn => {
        btn.classList.remove("bg-excel-600", "text-white");
        btn.classList.add("text-slate-300");
    });
    const activeMobBtn = document.getElementById(`mob-tab-${tabId}`);
    if (activeMobBtn) {
        activeMobBtn.classList.add("bg-excel-600", "text-white");
        activeMobBtn.classList.remove("text-slate-300");
    }

    // Hide all sections
    document.querySelectorAll(".tab-content").forEach(sec => sec.classList.add("hidden"));
    const targetSection = document.getElementById(`section-${tabId}`);
    if (targetSection) targetSection.classList.remove("hidden");

    if (tabId === 'materials') {
        loadStats();
    }

    lucide.createIcons();
}

// ----------------- TAB 1: CHAT & VOICE -----------------

function setQueryAndSend(text) {
    document.getElementById("chat-input").value = text;
    sendChatMessage();
}

function clearChat() {
    const chatContainer = document.getElementById("chat-messages");
    chatContainer.innerHTML = `
        <div class="flex gap-3">
            <div class="w-8 h-8 rounded-full bg-excel-700 text-white flex-shrink-0 flex items-center justify-center font-bold text-xs shadow-sm">
                AI
            </div>
            <div class="bg-slate-50 border border-slate-100 rounded-2xl rounded-tl-sm p-4 text-sm text-slate-700 max-w-2xl leading-relaxed shadow-sm">
                <p class="font-bold text-slate-900 mb-1">Chat Cleared</p>
                <p>Ready for your next exam doubt or question!</p>
            </div>
        </div>
    `;
}

async function sendChatMessage() {
    const input = document.getElementById("chat-input");
    const query = input.value.trim();
    if (!query) return;

    const subject = document.getElementById("chat-subject-select").value;
    const chatContainer = document.getElementById("chat-messages");

    // Append User message
    const userMsgId = "user-" + Date.now();
    const userDiv = document.createElement("div");
    userDiv.className = "flex gap-3 justify-end";
    userDiv.innerHTML = `
        <div class="bg-excel-navy text-white rounded-2xl rounded-tr-sm p-4 text-sm max-w-2xl leading-relaxed shadow-sm">
            <p>${escapeHtml(query)}</p>
            <div class="text-[10px] text-slate-400 mt-1 text-right">Target: ${subject}</div>
        </div>
        <div class="w-8 h-8 rounded-full bg-slate-300 text-slate-800 flex-shrink-0 flex items-center justify-center font-bold text-xs">
            You
        </div>
    `;
    chatContainer.appendChild(userDiv);
    input.value = "";
    chatContainer.scrollTop = chatContainer.scrollHeight;

    // Loading indicator
    const loadingId = "loading-" + Date.now();
    const loadingDiv = document.createElement("div");
    loadingDiv.id = loadingId;
    loadingDiv.className = "flex gap-3";
    loadingDiv.innerHTML = `
        <div class="w-8 h-8 rounded-full bg-excel-700 text-white flex-shrink-0 flex items-center justify-center font-bold text-xs">AI</div>
        <div class="bg-slate-50 border border-slate-100 rounded-2xl rounded-tl-sm p-4 text-sm text-slate-500 flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-excel-600 animate-bounce"></span>
            <span class="w-2 h-2 rounded-full bg-excel-600 animate-bounce" style="animation-delay: 0.2s"></span>
            <span class="w-2 h-2 rounded-full bg-excel-600 animate-bounce" style="animation-delay: 0.4s"></span>
            <span class="text-xs font-semibold text-slate-600 ml-1">Analyzing ICAI provisions & study materials...</span>
        </div>
    `;
    chatContainer.appendChild(loadingDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;

    try {
        const resp = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: query, subject: subject })
        });
        const data = await resp.json();

        // Remove loading
        const loader = document.getElementById(loadingId);
        if (loader) loader.remove();

        // Append AI response
        const aiDiv = document.createElement("div");
        aiDiv.className = "flex gap-3";

        let citationsHtml = "";
        if (data.citations && data.citations.length > 0) {
            citationsHtml = `
                <div class="mt-3 pt-3 border-t border-slate-200/80">
                    <p class="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1 flex items-center gap-1">
                        <i data-lucide="book-check" class="w-3.5 h-3.5 text-excel-600"></i>
                        <span>Verified In Institute Study Materials:</span>
                    </p>
                    <div class="flex flex-wrap gap-1.5">
                        ${data.citations.map(c => `
                            <span class="bg-white border border-slate-200 text-slate-700 text-[11px] px-2 py-0.5 rounded-md font-medium">
                                📄 ${c.doc_name} (Pg ${c.page})
                            </span>
                        `).join("")}
                    </div>
                </div>
            `;
        }

        const rawMarkdown = data.answer || "No response generated.";
        const renderedHtml = marked.parse(rawMarkdown);

        aiDiv.innerHTML = `
            <div class="w-8 h-8 rounded-full bg-excel-700 text-white flex-shrink-0 flex items-center justify-center font-bold text-xs shadow-sm">AI</div>
            <div class="bg-slate-50 border border-slate-100 rounded-2xl rounded-tl-sm p-5 text-sm text-slate-800 max-w-2xl leading-relaxed shadow-sm">
                <div class="markdown-body">${renderedHtml}</div>
                ${citationsHtml}
                <div class="mt-3 flex items-center justify-between text-[11px] text-slate-400 pt-2 border-t border-slate-100">
                    <span>Engine: ${data.engine || 'Excel AI Engine'}</span>
                    <button onclick="readAloud(this)" data-text="${escapeQuotes(rawMarkdown.replace(/[#*`_]/g, ''))}" class="hover:text-excel-600 flex items-center gap-1 font-semibold transition">
                        <i data-lucide="volume-2" class="w-3.5 h-3.5"></i>
                        <span>Read Aloud</span>
                    </button>
                </div>
            </div>
        `;
        chatContainer.appendChild(aiDiv);
        lucide.createIcons();
        chatContainer.scrollTop = chatContainer.scrollHeight;

    } catch (err) {
        const loader = document.getElementById(loadingId);
        if (loader) loader.remove();
        console.error(err);
        alert("Failed to reach Excel AI Coach. Please ensure the server is active.");
    }
}

// Voice Recognition (Speech-to-Text)
function initSpeechRecognition() {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRec) {
        recognition = new SpeechRec();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = "en-IN"; // Indian English

        recognition.onstart = () => {
            isListening = true;
            document.getElementById("voice-indicator").classList.remove("hidden");
            document.getElementById("voice-icon").setAttribute("data-lucide", "square");
            lucide.createIcons();
        };

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            document.getElementById("chat-input").value = transcript;
            sendChatMessage();
        };

        recognition.onend = () => {
            isListening = false;
            document.getElementById("voice-indicator").classList.add("hidden");
            document.getElementById("voice-icon").setAttribute("data-lucide", "mic");
            lucide.createIcons();
        };

        recognition.onerror = (e) => {
            console.error("Speech Recognition Error:", e);
            isListening = false;
            document.getElementById("voice-indicator").classList.add("hidden");
            document.getElementById("voice-icon").setAttribute("data-lucide", "mic");
            lucide.createIcons();
        };
    }
}

function toggleVoiceInput() {
    if (!recognition) {
        alert("Voice recognition is not supported in this browser. Please use Chrome, Edge, or Safari.");
        return;
    }
    if (isListening) {
        recognition.stop();
    } else {
        recognition.start();
    }
}

// Text-to-Speech (Read Aloud)
function readAloud(btn) {
    const text = btn.getAttribute("data-text");
    if (!text || !('speechSynthesis' in window)) return;

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text.substring(0, 500)); // Read first 500 chars cleanly
    utterance.rate = 1.0;
    utterance.lang = "en-IN";
    window.speechSynthesis.speak(utterance);
}

// ----------------- TAB 2: ANSWER EVALUATOR -----------------

function previewUpload(event) {
    const file = event.target.files[0];
    if (file) {
        document.getElementById("file-label").innerText = `Attached: ${file.name}`;
        if (file.type.startsWith("image/")) {
            const reader = new FileReader();
            reader.onload = (e) => {
                document.getElementById("image-preview").src = e.target.result;
                document.getElementById("preview-container").classList.remove("hidden");
            };
            reader.readAsDataURL(file);
        } else {
            document.getElementById("preview-container").classList.add("hidden");
        }
    }
}

async function submitAnswerForEvaluation() {
    const question = document.getElementById("eval-question").value.trim();
    const answerText = document.getElementById("eval-answer-text").value.trim();
    const fileInput = document.getElementById("eval-file");
    const file = fileInput.files[0];

    if (!question) {
        alert("Please enter the exam question being evaluated.");
        return;
    }

    if (!answerText && !file) {
        alert("Please either write your answer text or upload a photo of your handwritten paper.");
        return;
    }

    const evalResult = document.getElementById("eval-result");
    const evalBadge = document.getElementById("eval-badge");
    const evalBtn = document.getElementById("eval-btn");

    evalBtn.disabled = true;
    evalBtn.innerHTML = `
        <span class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
        <span>Evaluating Step Marks & Rubric...</span>
    `;

    evalBadge.className = "text-xs px-2.5 py-0.5 rounded-full font-semibold bg-amber-100 text-amber-800 animate-pulse";
    evalBadge.innerText = "Evaluating...";

    const formData = new FormData();
    formData.append("question", question);
    if (answerText) formData.append("student_answer_text", answerText);
    if (file) formData.append("file", file);

    try {
        const resp = await fetch("/api/evaluate", {
            method: "POST",
            body: formData
        });
        const data = await resp.json();

        evalBadge.className = "text-xs px-2.5 py-0.5 rounded-full font-semibold bg-emerald-100 text-emerald-800";
        evalBadge.innerText = "Evaluated";

        const rawMarkdown = data.evaluation || "Evaluation could not be generated.";
        evalResult.innerHTML = `
            <div class="markdown-body">
                ${marked.parse(rawMarkdown)}
            </div>
            <div class="mt-4 pt-3 border-t border-slate-100 text-[11px] text-slate-400">
                Evaluator Engine: ${data.engine || 'Excel AI Evaluator'}
            </div>
        `;

    } catch (err) {
        console.error(err);
        alert("Error during evaluation. Please verify server connection.");
    } finally {
        evalBtn.disabled = false;
        evalBtn.innerHTML = `
            <i data-lucide="check-square" class="w-4 h-4"></i>
            <span>Evaluate Answer Now</span>
        `;
        lucide.createIcons();
    }
}

// ----------------- TAB 3: MCQ PRACTICE ZONE -----------------

async function generateMCQs() {
    const subject = document.getElementById("mcq-subject").value;
    const topic = document.getElementById("mcq-topic").value.trim() || "Core Exam Concepts";
    const btn = document.getElementById("mcq-gen-btn");

    btn.disabled = true;
    btn.innerHTML = `<span class="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>`;

    try {
        const resp = await fetch("/api/generate-mcq", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ subject: subject, topic: topic, count: 5 })
        });
        const result = await resp.json();

        if (result.success && result.data && result.data.questions) {
            currentMCQData = result.data.questions;
            currentMCQIndex = 0;
            userScore = 0;
            selectedOptionState = {};
            document.getElementById("quiz-score-strip").classList.remove("hidden");
            renderCurrentQuestion();
        } else {
            alert("Could not generate MCQs. Please try again.");
        }
    } catch (err) {
        console.error(err);
        alert("Failed to generate quiz. Server might be busy.");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `
            <i data-lucide="sparkles" class="w-3.5 h-3.5 text-amber-400"></i>
            <span>Generate Quiz</span>
        `;
        lucide.createIcons();
    }
}

function renderCurrentQuestion() {
    if (!currentMCQData || currentMCQData.length === 0) return;

    const q = currentMCQData[currentMCQIndex];
    document.getElementById("quiz-progress").innerText = `${currentMCQIndex + 1} / ${currentMCQData.length}`;
    document.getElementById("quiz-score").innerText = userScore;

    const container = document.getElementById("mcq-container");
    const hasAnswered = selectedOptionState[currentMCQIndex] !== undefined;
    const userSelected = selectedOptionState[currentMCQIndex];

    container.innerHTML = `
        <div class="space-y-4">
            <div class="flex items-center justify-between">
                <span class="text-xs uppercase font-extrabold px-2.5 py-1 rounded bg-amber-100 text-amber-800">
                    Question ${currentMCQIndex + 1} • ${q.difficulty || 'Exam Standard'}
                </span>
            </div>

            <h3 class="text-base font-bold text-slate-800 leading-snug">${escapeHtml(q.question)}</h3>

            <div class="space-y-2.5 mt-4">
                ${q.options.map((opt, idx) => {
                    const optLetter = opt.trim().substring(0, 1).toUpperCase();
                    let optClass = "bg-slate-50 border-slate-200 hover:border-excel-600/40 hover:bg-excel-50/50";
                    let badge = "";

                    if (hasAnswered) {
                        if (optLetter === q.correct_option.toUpperCase()) {
                            optClass = "bg-emerald-50 border-emerald-500 text-emerald-900 font-semibold";
                            badge = `<span class="text-xs text-emerald-700 font-bold ml-auto">✓ Correct</span>`;
                        } else if (userSelected === optLetter) {
                            optClass = "bg-red-50 border-red-500 text-red-900";
                            badge = `<span class="text-xs text-red-700 font-bold ml-auto">✗ Your Choice</span>`;
                        }
                    }

                    return `
                        <button onclick="handleOptionSelect('${optLetter}')" ${hasAnswered ? 'disabled' : ''} class="w-full text-left p-3.5 rounded-xl border text-sm flex items-center transition ${optClass}">
                            <span>${escapeHtml(opt)}</span>
                            ${badge}
                        </button>
                    `;
                }).join("")}
            </div>

            ${hasAnswered ? `
                <div class="mt-5 p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-700 leading-relaxed">
                    <p class="font-bold text-slate-900 mb-1 flex items-center gap-1">
                        <i data-lucide="book-open" class="w-3.5 h-3.5 text-excel-600"></i>
                        <span>ICAI Suggested Reasoning:</span>
                    </p>
                    <p>${escapeHtml(q.explanation)}</p>
                </div>
                <div class="flex justify-between items-center pt-4 border-t border-slate-100">
                    <button onclick="prevQuestion()" ${currentMCQIndex === 0 ? 'disabled' : ''} class="text-xs font-bold text-slate-500 hover:text-slate-800 disabled:opacity-30">Previous</button>
                    ${currentMCQIndex < currentMCQData.length - 1 ? `
                        <button onclick="nextQuestion()" class="bg-excel-navy text-white text-xs font-bold px-4 py-2 rounded-xl hover:bg-slate-800 transition">Next Question →</button>
                    ` : `
                        <span class="text-xs font-bold text-emerald-700">Quiz Completed! Total Score: ${userScore}/${currentMCQData.length}</span>
                    `}
                </div>
            ` : ''}
        </div>
    `;
    lucide.createIcons();
}

function handleOptionSelect(letter) {
    if (selectedOptionState[currentMCQIndex] !== undefined) return;
    const q = currentMCQData[currentMCQIndex];
    selectedOptionState[currentMCQIndex] = letter;

    if (letter === q.correct_option.toUpperCase()) {
        userScore += 1;
    }
    renderCurrentQuestion();
}

function nextQuestion() {
    if (currentMCQIndex < currentMCQData.length - 1) {
        currentMCQIndex++;
        renderCurrentQuestion();
    }
}

function prevQuestion() {
    if (currentMCQIndex > 0) {
        currentMCQIndex--;
        renderCurrentQuestion();
    }
}

// ----------------- TAB 4: MATERIALS & STATS -----------------

async function loadStats() {
    try {
        const resp = await fetch("/api/stats");
        const data = await resp.json();

        // Update top pill
        const statusText = document.getElementById("status-text");
        if (data.has_api_key) {
            statusText.innerText = "Gemini 1.5 Flash (Live AI)";
        } else {
            statusText.innerText = "AI Ready (RAG Active)";
        }

        // Update badge
        const badge = document.getElementById("total-chunks-badge");
        if (badge) {
            badge.innerText = `${data.total_chunks} Chunks • ${data.total_pdfs} Study PDFs`;
        }

        // Render subject cards
        const grid = document.getElementById("subject-cards-grid");
        if (grid && data.subjects) {
            grid.innerHTML = Object.entries(data.subjects).map(([subject, info]) => {
                const pdfList = info.pdf_files.length > 0 
                    ? info.pdf_files.map(f => `<li class="text-[11px] text-slate-600 truncate">📄 ${f}</li>`).join("")
                    : `<li class="text-[11px] text-slate-400 italic">Pre-loaded statutory knowledge active</li>`;

                return `
                    <div class="bg-slate-50 border border-slate-200/80 rounded-xl p-4 flex flex-col justify-between">
                        <div>
                            <div class="flex items-center justify-between mb-2">
                                <h4 class="font-bold text-xs text-slate-800 truncate">${subject.replace(/_/g, " ")}</h4>
                                <span class="text-[10px] bg-excel-100 text-excel-800 font-bold px-1.5 py-0.5 rounded">${info.chunks} Chunks</span>
                            </div>
                            <ul class="space-y-1 mb-3">
                                ${pdfList}
                            </ul>
                        </div>
                        <div class="text-[10px] text-slate-400 pt-2 border-t border-slate-200/60 flex items-center justify-between">
                            <span>${info.pdf_count} PDFs uploaded</span>
                            <span class="text-emerald-600 font-semibold">Indexed</span>
                        </div>
                    </div>
                `;
            }).join("");
        }

    } catch (err) {
        console.error("Stats load failed:", err);
    }
}

async function uploadStudyMaterial() {
    const subject = document.getElementById("upload-subject-select").value;
    const fileInput = document.getElementById("material-pdf-file");
    const file = fileInput.files[0];

    if (!file) {
        alert("Please select a PDF file of your coaching study material.");
        return;
    }

    const btn = document.getElementById("upload-material-btn");
    btn.disabled = true;
    btn.innerHTML = `<span class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span> <span>Indexing PDF...</span>`;

    const formData = new FormData();
    formData.append("subject", subject);
    formData.append("file", file);

    try {
        const resp = await fetch("/api/upload-pdf", {
            method: "POST",
            body: formData
        });
        const data = await resp.json();
        if (data.success) {
            alert(data.message);
            fileInput.value = "";
            loadStats();
        } else {
            alert("Upload failed.");
        }
    } catch (err) {
        console.error(err);
        alert("Upload error. Please verify server is running.");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `
            <i data-lucide="plus" class="w-4 h-4"></i>
            <span>Upload & Index PDF</span>
        `;
        lucide.createIcons();
    }
}

// ----------------- TAB 5: SHARE & SETTINGS -----------------

async function saveApiKey() {
    const key = document.getElementById("gemini-key-input").value.trim();
    if (!key) {
        alert("Please enter a valid Gemini API key.");
        return;
    }

    const statusMsg = document.getElementById("key-status-msg");
    statusMsg.className = "text-xs font-semibold text-slate-500";
    statusMsg.innerText = "Saving & verifying...";

    try {
        const resp = await fetch("/api/set-api-key", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: key })
        });
        const data = await resp.json();
        if (data.success) {
            statusMsg.className = "text-xs font-semibold text-emerald-600";
            statusMsg.innerText = "✓ Gemini API Key successfully configured! Live AI is now active.";
            loadStats();
        }
    } catch (err) {
        statusMsg.className = "text-xs font-semibold text-red-600";
        statusMsg.innerText = "Failed to update API key.";
    }
}

// Helper utilities
function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

function escapeQuotes(str) {
    if (!str) return "";
    return str.replace(/"/g, '&quot;').replace(/'/g, "\\'");
}
