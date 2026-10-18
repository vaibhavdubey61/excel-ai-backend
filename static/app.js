// Excel AI - Minimalist Unified Frontend

let selectedFile = null;
let isRecording = false;
let speechRecognizer = null;

document.addEventListener("DOMContentLoaded", () => {
    lucide.createIcons();
    initClipboardPaste();
    initSpeechRecognition();
});

// Auto-resize textarea as user types
function autoResize(textarea) {
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 140) + "px";
}

// Enter to send (Shift+Enter for newline)
function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

// Quick Suggestion Click
function usePrompt(text) {
    const input = document.getElementById("chat-input");
    input.value = text;
    autoResize(input);
    input.focus();
    sendMessage();
}

// New Chat
function newChat() {
    document.getElementById("messages-container").innerHTML = "";
    document.getElementById("messages-container").classList.add("hidden");
    document.getElementById("welcome-view").classList.remove("hidden");
    document.getElementById("chat-input").value = "";
    autoResize(document.getElementById("chat-input"));
    clearAttachment();
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
    }
}

// File Attachment Handling (Photo / PDF)
function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;
    setAttachment(file);
}

function setAttachment(file) {
    selectedFile = file;
    const previewContainer = document.getElementById("attachment-preview");
    const thumb = document.getElementById("attachment-thumb");
    const icon = document.getElementById("attachment-icon");
    const nameSpan = document.getElementById("attachment-name");

    nameSpan.innerText = file.name;
    previewContainer.classList.remove("hidden");

    if (file.type.startsWith("image/")) {
        const reader = new FileReader();
        reader.onload = (e) => {
            thumb.src = e.target.result;
            thumb.classList.remove("hidden");
            icon.classList.add("hidden");
        };
        reader.readAsDataURL(file);
    } else {
        thumb.classList.add("hidden");
        icon.classList.remove("hidden");
    }
    lucide.createIcons();
}

function clearAttachment() {
    selectedFile = null;
    document.getElementById("file-input").value = "";
    document.getElementById("attachment-preview").classList.add("hidden");
    document.getElementById("attachment-thumb").src = "";
}

// Clipboard Paste (e.g. Ctrl + V to paste screenshot directly into chat)
function initClipboardPaste() {
    window.addEventListener("paste", (event) => {
        const items = (event.clipboardData || event.originalEvent.clipboardData).items;
        for (let item of items) {
            if (item.type.indexOf("image") === 0) {
                const blob = item.getAsFile();
                setAttachment(blob);
                break;
            }
        }
    });
}

// Voice Note (Speech-to-Text)
function initSpeechRecognition() {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRec) {
        speechRecognizer = new SpeechRec();
        speechRecognizer.continuous = false;
        speechRecognizer.interimResults = false;
        speechRecognizer.lang = "en-IN"; // English (India)

        speechRecognizer.onstart = () => {
            isRecording = true;
            document.getElementById("voice-indicator").classList.remove("hidden");
            document.getElementById("mic-icon").setAttribute("data-lucide", "square");
            document.getElementById("voice-btn").classList.add("text-red-500", "bg-red-50");
            lucide.createIcons();
        };

        speechRecognizer.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            const input = document.getElementById("chat-input");
            input.value = (input.value ? input.value + " " : "") + transcript;
            autoResize(input);
        };

        speechRecognizer.onend = () => {
            isRecording = false;
            document.getElementById("voice-indicator").classList.add("hidden");
            document.getElementById("mic-icon").setAttribute("data-lucide", "mic");
            document.getElementById("voice-btn").classList.remove("text-red-500", "bg-red-50");
            lucide.createIcons();
        };

        speechRecognizer.onerror = (e) => {
            console.error("Speech Recognition Error:", e);
            isRecording = false;
            document.getElementById("voice-indicator").classList.add("hidden");
            document.getElementById("mic-icon").setAttribute("data-lucide", "mic");
            document.getElementById("voice-btn").classList.remove("text-red-500", "bg-red-50");
            lucide.createIcons();
        };
    }
}

function toggleVoiceInput() {
    if (!speechRecognizer) {
        alert("Voice input is supported in Google Chrome, Microsoft Edge, and Safari.");
        return;
    }
    if (isRecording) {
        speechRecognizer.stop();
    } else {
        speechRecognizer.start();
    }
}

// Send Message
async function sendMessage() {
    const input = document.getElementById("chat-input");
    const text = input.value.trim();
    const currentAttachment = selectedFile;

    if (!text && !currentAttachment) return;

    // Switch from welcome view to message stream
    document.getElementById("welcome-view").classList.add("hidden");
    const container = document.getElementById("messages-container");
    container.classList.remove("hidden");

    // 1. Render User Message Bubble
    let attachmentHtml = "";
    if (currentAttachment && currentAttachment.type.startsWith("image/")) {
        const tempUrl = URL.createObjectURL(currentAttachment);
        attachmentHtml = `
            <div class="mb-2">
                <img src="${tempUrl}" class="max-h-48 rounded-xl border border-slate-700/50 shadow-sm" alt="attachment">
            </div>
        `;
    } else if (currentAttachment) {
        attachmentHtml = `
            <div class="mb-2 text-xs bg-slate-800 px-3 py-1.5 rounded-lg flex items-center gap-1.5">
                <i data-lucide="file" class="w-3.5 h-3.5 text-slate-300"></i>
                <span class="truncate">${escapeHtml(currentAttachment.name)}</span>
            </div>
        `;
    }

    const userDiv = document.createElement("div");
    userDiv.className = "flex justify-end";
    userDiv.innerHTML = `
        <div class="bg-slate-900 text-white rounded-2xl rounded-tr-sm px-4 py-3 max-w-xl text-sm leading-relaxed shadow-sm">
            ${attachmentHtml}
            ${text ? `<p>${escapeHtml(text)}</p>` : ''}
        </div>
    `;
    container.appendChild(userDiv);
    lucide.createIcons();

    // Reset input and attachment
    input.value = "";
    autoResize(input);
    clearAttachment();
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });

    // 2. Render Loading State
    const loadingId = "loader-" + Date.now();
    const loadingDiv = document.createElement("div");
    loadingDiv.id = loadingId;
    loadingDiv.className = "flex gap-3 items-start max-w-2xl";
    loadingDiv.innerHTML = `
        <div class="w-8 h-8 rounded-xl bg-amber-500 text-slate-900 font-black text-xs flex items-center justify-center flex-shrink-0 shadow-sm">
            E
        </div>
        <div class="bg-white border border-slate-200/80 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm flex items-center gap-2 text-xs font-medium text-slate-500">
            <span class="w-2 h-2 rounded-full bg-slate-400 animate-pulse"></span>
            <span class="w-2 h-2 rounded-full bg-slate-400 animate-pulse" style="animation-delay: 0.2s"></span>
            <span class="w-2 h-2 rounded-full bg-slate-400 animate-pulse" style="animation-delay: 0.4s"></span>
            <span class="ml-1 text-slate-600">Excel AI is analyzing...</span>
        </div>
    `;
    container.appendChild(loadingDiv);
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });

    // 3. Make API Call
    const formData = new FormData();
    if (text) formData.append("message", text);
    if (currentAttachment) formData.append("file", currentAttachment);

    try {
        const resp = await fetch("/api/chat", {
            method: "POST",
            body: formData
        });
        const data = await resp.json();

        // Remove loading state
        const loader = document.getElementById(loadingId);
        if (loader) loader.remove();

        const rawMarkdown = data.reply || "I could not generate an answer at this moment. Please try again.";
        const renderedHtml = marked.parse(rawMarkdown);

        // 4. Render Assistant Message
        const aiDiv = document.createElement("div");
        aiDiv.className = "flex gap-3 items-start";
        aiDiv.innerHTML = `
            <div class="w-8 h-8 rounded-xl bg-amber-500 text-slate-900 font-black text-xs flex items-center justify-center flex-shrink-0 shadow-sm mt-1">
                E
            </div>
            <div class="flex-1 bg-white border border-slate-200/80 rounded-2xl rounded-tl-sm p-5 shadow-sm space-y-3">
                <div class="markdown-body">
                    ${renderedHtml}
                </div>
                <div class="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400">
                    <span class="text-[11px] font-medium text-slate-400">Excel AI Exam Coach</span>
                    <div class="flex items-center gap-2">
                        <button onclick="copyToClipboard(this)" data-content="${escapeQuotes(rawMarkdown)}" title="Copy response" class="p-1 hover:text-slate-700 transition flex items-center gap-1 text-[11px] font-medium">
                            <i data-lucide="copy" class="w-3.5 h-3.5"></i>
                            <span>Copy</span>
                        </button>
                        <button onclick="readAloud(this)" data-text="${escapeQuotes(rawMarkdown.replace(/[#*`_]/g, ''))}" title="Listen to answer" class="p-1 hover:text-amber-600 transition flex items-center gap-1 text-[11px] font-medium">
                            <i data-lucide="volume-2" class="w-3.5 h-3.5"></i>
                            <span>Listen</span>
                        </button>
                    </div>
                </div>
            </div>
        `;
        container.appendChild(aiDiv);
        lucide.createIcons();
        window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });

    } catch (err) {
        console.error(err);
        const loader = document.getElementById(loadingId);
        if (loader) loader.remove();
        alert("Unable to reach Excel AI. Please make sure the server is running.");
    }
}

// Copy to clipboard
function copyToClipboard(btn) {
    const content = btn.getAttribute("data-content");
    if (!content) return;
    navigator.clipboard.writeText(content).then(() => {
        const span = btn.querySelector("span");
        const originalText = span.innerText;
        span.innerText = "Copied!";
        setTimeout(() => { span.innerText = originalText; }, 1500);
    });
}

// Text-to-Speech (Read Aloud)
function readAloud(btn) {
    const text = btn.getAttribute("data-text");
    if (!text || !('speechSynthesis' in window)) return;

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text.substring(0, 700));
    utterance.rate = 1.0;
    utterance.lang = "en-IN";
    window.speechSynthesis.speak(utterance);
}

// Helpers
function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

function escapeQuotes(str) {
    if (!str) return "";
    return str.replace(/"/g, '&quot;').replace(/'/g, "\\'");
}
