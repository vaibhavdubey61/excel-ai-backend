import React, { useState, useRef, useEffect } from 'react';
import {
  StyleSheet,
  Text,
  View,
  TextInput,
  TouchableOpacity,
  ScrollView,
  SafeAreaView,
  StatusBar,
  Animated,
  Dimensions,
  Modal,
  Image,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Alert,
} from 'react-native';

// Storage abstraction (uses AsyncStorage if installed, else persistent memory store)
let AsyncStorage;
try {
  AsyncStorage = require('@react-native-async-storage/async-storage').default;
} catch (e) {
  const memoryStore = {};
  AsyncStorage = {
    getItem: async (key) => memoryStore[key] || null,
    setItem: async (key, val) => { memoryStore[key] = String(val); },
    removeItem: async (key) => { delete memoryStore[key]; }
  };
}

const BASE_API_URL = 'https://excel-ai-backend-yegx.onrender.com';
const CLOUD_API_URL = `${BASE_API_URL}/api/chat`;
const CLOUD_MCQ_URL = `${BASE_API_URL}/api/mcq/generate`;
const { width: SCREEN_WIDTH } = Dimensions.get('window');

function cleanExamMarkdown(text) {
  if (!text) return "";
  let cleaned = text;
  cleaned = cleaned.replace(/\s*\([Ww]ait,\s*let'?s\s*recalculate[^)]*\)/gi, "");
  cleaned = cleaned.replace(/\s*\([Ww]ait,\s*let'?s\s*check[^)]*\)/gi, "");
  cleaned = cleaned.replace(/Correction in options:[^\n.]*(\.|$)/gi, "");
  cleaned = cleaned.replace(/\\times\b/g, "×");
  cleaned = cleaned.replace(/\\cdot\b/g, "·");
  cleaned = cleaned.replace(/\\div\b/g, "÷");
  cleaned = cleaned.replace(/\\pm\b/g, "±");
  cleaned = cleaned.replace(/\\(leq|le)\b/g, "≤");
  cleaned = cleaned.replace(/\\(geq|ge)\b/g, "≥");
  cleaned = cleaned.replace(/\\(neq|ne)\b/g, "≠");
  for (let i = 0; i < 3; i++) {
    cleaned = cleaned.replace(/\\text\{([^{}]*)\}/g, "$1");
  }
  cleaned = cleaned.replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, "($1 / $2)");
  cleaned = cleaned.replace(/\\(quad|qquad|,|;|!)/g, " ");
  cleaned = cleaned.replace(/\\left\s*([(\[{|])/g, "$1");
  cleaned = cleaned.replace(/\\right\s*([)\]}|])/g, "$1");
  cleaned = cleaned.replace(/\\\[/g, "[").replace(/\\\]/g, "]").replace(/\\\(/g, "(").replace(/\\\)/g, ")");
  cleaned = cleaned.replace(/\$\$([\s\S]*?)\$\$/g, (m, p1) => "\n\n" + p1.trim() + "\n\n");
  cleaned = cleaned.replace(/\$([^\$\n]+)\$/g, (m, p1) => p1.trim());
  cleaned = cleaned.replace(/\$/g, "");
  return cleaned.trim();
}

export default function App() {
  // Course and Level state
  const [studentCourse, setStudentCourse] = useState('CA');
  const [studentLevel, setStudentLevel] = useState('Inter');
  const [onboardingVisible, setOnboardingVisible] = useState(false);
  const [tempCourse, setTempCourse] = useState('CA');
  const [tempLevel, setTempLevel] = useState('Inter');

  // Interactive MCQ Modal state
  const [mcqModalVisible, setMcqModalVisible] = useState(false);
  const [mcqLoading, setMcqLoading] = useState(false);
  const [mcqCount, setMcqCount] = useState(10);
  const [mcqCustomTopic, setMcqCustomTopic] = useState('');
  const [mcqQuizData, setMcqQuizData] = useState(null);
  const [mcqCurrentIndex, setMcqCurrentIndex] = useState(0);
  const [mcqUserAnswers, setMcqUserAnswers] = useState({});
  const [mcqSubmittedQuestions, setMcqSubmittedQuestions] = useState({});
  const [mcqShowResults, setMcqShowResults] = useState(false);
  const [mcqReviewMistakesOnly, setMcqReviewMistakesOnly] = useState(false);

  // State
  const [sessions, setSessions] = useState([
    {
      id: 'session_1',
      title: 'Section 115BAC Slabs',
      createdAt: Date.now(),
      messages: [
        {
          id: 'm1',
          role: 'assistant',
          text: 'Namaste! I am your **Excel AI Coach** for CA, CS, and CMA exams.\n\nAsk any conceptual doubt, paste an exam problem, or upload a photo of your handwritten answer sheet for evaluation.',
        },
      ],
    },
  ]);
  const [currentSessionId, setCurrentSessionId] = useState('session_1');
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [selectedImage, setSelectedImage] = useState(null);

  const sidebarAnim = useRef(new Animated.Value(-SCREEN_WIDTH * 0.78)).current;
  const scrollViewRef = useRef();

  const currentSession =
    sessions.find((s) => s.id === currentSessionId) || sessions[0];

  // Load saved course & level on mount
  useEffect(() => {
    (async () => {
      try {
        const c = await AsyncStorage.getItem('student_course');
        const l = await AsyncStorage.getItem('student_level');
        if (c && l) {
          setStudentCourse(c);
          setStudentLevel(l);
          setTempCourse(c);
          setTempLevel(l);
        } else {
          setOnboardingVisible(true);
        }
      } catch (err) {
        setOnboardingVisible(true);
      }
    })();
  }, []);

  const saveCourseLevel = async (c, l) => {
    setStudentCourse(c);
    setStudentLevel(l);
    setOnboardingVisible(false);
    try {
      await AsyncStorage.setItem('student_course', c);
      await AsyncStorage.setItem('student_level', l);
    } catch (e) {}
  };

  // Drawer Animation
  useEffect(() => {
    Animated.timing(sidebarAnim, {
      toValue: sidebarOpen ? 0 : -SCREEN_WIDTH * 0.78,
      duration: 250,
      useNativeDriver: true,
    }).current.start();
  }, [sidebarOpen]);

  const toggleSidebar = (open) => {
    setSidebarOpen(open);
  };

  const startNewChat = () => {
    const newId = 'session_' + Date.now();
    const newSession = {
      id: newId,
      title: 'New Chat',
      createdAt: Date.now(),
      messages: [],
    };
    setSessions([newSession, ...sessions]);
    setCurrentSessionId(newId);
    setSelectedImage(null);
    setInputText('');
    toggleSidebar(false);
  };

  const switchSession = (id) => {
    setCurrentSessionId(id);
    setSelectedImage(null);
    toggleSidebar(false);
  };

  const deleteSession = (id) => {
    if (sessions.length <= 1) {
      startNewChat();
      return;
    }
    const updated = sessions.filter((s) => s.id !== id);
    setSessions(updated);
    if (currentSessionId === id) {
      setCurrentSessionId(updated[0].id);
    }
  };

  const handleSend = async () => {
    const trimmed = inputText.trim();
    if (!trimmed && !selectedImage) return;

    const userMsgId = 'msg_' + Date.now();
    const userMsg = {
      id: userMsgId,
      role: 'user',
      text: trimmed,
      imageUrl: selectedImage ? selectedImage.uri : null,
    };

    // Update session title on first message
    let updatedTitle = currentSession.title;
    if (currentSession.messages.length === 0 && trimmed) {
      updatedTitle =
        trimmed.length > 24 ? trimmed.substring(0, 24) + '...' : trimmed;
    }

    const updatedMessages = [...currentSession.messages, userMsg];

    setSessions((prev) =>
      prev.map((s) =>
        s.id === currentSessionId
          ? { ...s, title: updatedTitle, messages: updatedMessages }
          : s
      )
    );

    const sendingText = trimmed;
    const sendingImage = selectedImage;
    setInputText('');
    setSelectedImage(null);
    setIsLoading(true);

    setTimeout(() => {
      scrollViewRef.current?.scrollToEnd({ animated: true });
    }, 100);

    try {
      const formData = new FormData();
      if (sendingText) formData.append('message', sendingText);
      if (sendingImage) {
        formData.append('file', {
          uri: sendingImage.uri,
          name: 'answersheet.jpg',
          type: 'image/jpeg',
        });
      }
      formData.append('course', studentCourse || 'CA');
      formData.append('level', studentLevel || 'Inter');
      const historyList = (currentSession.messages || []).slice(-6).map((m) => ({
        role: m.role || 'user',
        text: m.text || '',
      }));
      formData.append('history', JSON.stringify(historyList));

      const response = await fetch(CLOUD_API_URL, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();
      const replyText =
        data.reply ||
        'I could not generate an exam response at this time. Please retry.';

      const assistantMsg = {
        id: 'reply_' + Date.now(),
        role: 'assistant',
        text: cleanExamMarkdown(replyText),
      };

      setSessions((prev) =>
        prev.map((s) =>
          s.id === currentSessionId
            ? { ...s, messages: [...s.messages, assistantMsg] }
            : s
        )
      );
    } catch (error) {
      Alert.alert(
        'Connection Error',
        'Could not reach Excel AI Cloud Backend. Please check your internet.'
      );
    } finally {
      setIsLoading(false);
      setTimeout(() => {
        scrollViewRef.current?.scrollToEnd({ animated: true });
      }, 100);
    }
  };

  // Attach sample mock image or prompt photo upload
  const handleAttachPhoto = () => {
    Alert.alert(
      'Attach Answer Sheet',
      'Upload a photo of your handwritten answer sheet for evaluation.',
      [
        {
          text: 'Use Sample Answer Sheet Photo',
          onPress: () => {
            setSelectedImage({
              uri: 'https://images.unsplash.com/photo-1455390582262-044cdead277a?w=600',
              name: 'handwritten_answer.jpg',
            });
          },
        },
        { text: 'Cancel', style: 'cancel' },
      ]
    );
  };

  // Mobile MCQ Engine Handlers
  const startMobileQuiz = async () => {
    setMcqLoading(true);
    try {
      const resp = await fetch(CLOUD_MCQ_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          course: studentCourse,
          level: studentLevel,
          topic: mcqCustomTopic.trim() || 'Random',
          count: mcqCount,
        }),
      });
      if (!resp.ok) {
        const errJson = await resp.json().catch(() => ({}));
        throw new Error(errJson.detail || 'Failed to generate quiz');
      }
      const data = await resp.json();
      if (!data.questions || data.questions.length === 0) {
        throw new Error('No questions returned');
      }
      setMcqQuizData(data);
      setMcqCurrentIndex(0);
      setMcqUserAnswers({});
      setMcqSubmittedQuestions({});
      setMcqShowResults(false);
      setMcqReviewMistakesOnly(false);
    } catch (e) {
      Alert.alert('Quiz Notice', e.message || 'Could not load MCQs. Check internet connection.');
    } finally {
      setMcqLoading(false);
    }
  };

  const selectMobileOption = (key) => {
    if (mcqSubmittedQuestions[mcqCurrentIndex]) return;
    setMcqUserAnswers({ ...mcqUserAnswers, [mcqCurrentIndex]: key });
  };

  const submitMobileQuestion = () => {
    if (!mcqUserAnswers[mcqCurrentIndex]) {
      Alert.alert('Select Option', 'Please select an option before checking.');
      return;
    }
    setMcqSubmittedQuestions({ ...mcqSubmittedQuestions, [mcqCurrentIndex]: true });
  };

  const nextMobileQuestion = () => {
    if (!mcqQuizData) return;
    if (mcqCurrentIndex < mcqQuizData.questions.length - 1) {
      setMcqCurrentIndex(mcqCurrentIndex + 1);
    } else {
      setMcqShowResults(true);
    }
  };

  const resetMobileQuiz = () => {
    setMcqQuizData(null);
    setMcqShowResults(false);
    setMcqUserAnswers({});
    setMcqSubmittedQuestions({});
    setMcqCurrentIndex(0);
    setMcqReviewMistakesOnly(false);
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#171717" />

      {/* Top Header Bar */}
      <View style={styles.header}>
        <TouchableOpacity
          onPress={() => toggleSidebar(true)}
          style={styles.headerButton}
        >
          <Text style={styles.headerIconText}>☰</Text>
        </TouchableOpacity>

        <View style={styles.headerTitleContainer}>
          <Text style={styles.headerTitle}>Excel AI</Text>
          <TouchableOpacity
            onPress={() => setOnboardingVisible(true)}
            style={styles.headerBadge}
          >
            <Text style={styles.headerBadgeText}>
              {studentCourse} {studentLevel}
            </Text>
          </TouchableOpacity>
        </View>

        <TouchableOpacity onPress={startNewChat} style={styles.headerButton}>
          <Text style={styles.headerIconText}>✎</Text>
        </TouchableOpacity>
      </View>

      {/* Main Chat Messages Viewport */}
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.chatContainer}
      >
        <ScrollView
          ref={scrollViewRef}
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
        >
          {currentSession.messages.length === 0 ? (
            <View style={styles.welcomeBox}>
              <View style={styles.welcomeAvatar}>
                <Text style={styles.welcomeAvatarText}>E</Text>
              </View>
              <Text style={styles.welcomeTitle}>
                What would you like to master today?
              </Text>
              <Text style={styles.welcomeSubtitle}>
                Ask exam doubts, upload handwritten papers for checking, or
                practice questions.
              </Text>

              {/* Suggestion cards */}
              <View style={styles.suggestionsContainer}>
                <TouchableOpacity
                  style={[styles.suggestionCard, { borderColor: '#f59e0b', backgroundColor: '#1c1914' }]}
                  onPress={() => {
                    resetMobileQuiz();
                    setMcqModalVisible(true);
                  }}
                >
                  <Text style={[styles.suggestionTitle, { color: '#fbbf24' }]}>
                    🏆 Interactive MCQ Practice
                  </Text>
                  <Text style={styles.suggestionDesc}>
                    {studentCourse} {studentLevel} exam drill with live scoring & working notes
                  </Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.suggestionCard}
                  onPress={() =>
                    setInputText(
                      'Explain Section 115BAC new tax slabs and key deductions.'
                    )
                  }
                >
                  <Text style={styles.suggestionTitle}>
                    📌 Section 115BAC Slabs
                  </Text>
                  <Text style={styles.suggestionDesc}>
                    Tax rates & Sec 87A rebate rules
                  </Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.suggestionCard}
                  onPress={() =>
                    setInputText(
                      'What are the buy-back conditions under Section 68 of Companies Act?'
                    )
                  }
                >
                  <Text style={styles.suggestionTitle}>
                    ⚖️ Section 68 Buy-Back
                  </Text>
                  <Text style={styles.suggestionDesc}>
                    Quantum limits & debt-equity criteria
                  </Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.suggestionCard}
                  onPress={() =>
                    setInputText(
                      'Check my answer for this question and give step-wise marks:'
                    )
                  }
                >
                  <Text style={styles.suggestionTitle}>
                    📝 Check Handwritten Paper
                  </Text>
                  <Text style={styles.suggestionDesc}>
                    Score out of 10 & examiner feedback
                  </Text>
                </TouchableOpacity>
              </View>
            </View>
          ) : (
            currentSession.messages.map((msg) => (
              <View
                key={msg.id}
                style={[
                  styles.messageWrapper,
                  msg.role === 'user'
                    ? styles.userWrapper
                    : styles.assistantWrapper,
                ]}
              >
                {msg.role === 'assistant' && (
                  <View style={styles.assistantAvatar}>
                    <Text style={styles.assistantAvatarText}>E</Text>
                  </View>
                )}

                <View
                  style={[
                    styles.messageBubble,
                    msg.role === 'user' ? styles.userBubble : styles.assistantBubble,
                  ]}
                >
                  {msg.imageUrl && (
                    <Image
                      source={{ uri: msg.imageUrl }}
                      style={styles.uploadedImage}
                    />
                  )}
                  <Text
                    style={[
                      styles.messageText,
                      msg.role === 'user' ? styles.userText : styles.assistantText,
                    ]}
                  >
                    {msg.text}
                  </Text>
                </View>
              </View>
            ))
          )}

          {isLoading && (
            <View style={[styles.messageWrapper, styles.assistantWrapper]}>
              <View style={styles.assistantAvatar}>
                <Text style={styles.assistantAvatarText}>E</Text>
              </View>
              <View style={[styles.messageBubble, styles.assistantBubble]}>
                <View style={styles.loadingRow}>
                  <ActivityIndicator size="small" color="#f59e0b" />
                  <Text style={styles.loadingText}>
                    Excel AI is consulting exam notes...
                  </Text>
                </View>
              </View>
            </View>
          )}
        </ScrollView>

        {/* Selected Image Thumbnail Pill */}
        {selectedImage && (
          <View style={styles.imagePreviewPill}>
            <Image
              source={{ uri: selectedImage.uri }}
              style={styles.pillThumb}
            />
            <Text style={styles.pillText} numberOfLines={1}>
              {selectedImage.name}
            </Text>
            <TouchableOpacity onPress={() => setSelectedImage(null)}>
              <Text style={styles.pillRemove}>✕</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Bottom Input Capsule */}
        <View style={styles.inputContainer}>
          <TouchableOpacity
            onPress={handleAttachPhoto}
            style={styles.iconButton}
          >
            <Text style={styles.attachIcon}>📎</Text>
          </TouchableOpacity>

          <TextInput
            style={styles.inputField}
            placeholder="Ask Excel AI (Doubt, answer, or photo)..."
            placeholderTextColor="#888888"
            value={inputText}
            onChangeText={setInputText}
            multiline
          />

          <TouchableOpacity
            onPress={handleSend}
            disabled={!inputText.trim() && !selectedImage}
            style={[
              styles.sendButton,
              (!inputText.trim() && !selectedImage) && styles.sendButtonDisabled,
            ]}
          >
            <Text style={styles.sendIcon}>↑</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>

      {/* Collapsible Left Drawer (Chat History) */}
      {sidebarOpen && (
        <TouchableOpacity
          style={styles.drawerBackdrop}
          activeOpacity={1}
          onPress={() => toggleSidebar(false)}
        />
      )}

      <Animated.View
        style={[styles.sidebar, { transform: [{ translateX: sidebarAnim }] }]}
      >
        <SafeAreaView style={styles.sidebarInner}>
          <View style={styles.sidebarHeader}>
            <TouchableOpacity
              onPress={startNewChat}
              style={styles.newChatSidebarButton}
            >
              <Text style={styles.newChatPlus}>+</Text>
              <Text style={styles.newChatText}>New Chat</Text>
            </TouchableOpacity>
          </View>

          <Text style={styles.sidebarSectionTitle}>RECENT CONVERSATIONS</Text>

          <ScrollView style={styles.historyList}>
            {sessions.map((item) => {
              const isActive = item.id === currentSessionId;
              return (
                <TouchableOpacity
                  key={item.id}
                  onPress={() => switchSession(item.id)}
                  style={[
                    styles.historyItem,
                    isActive && styles.historyItemActive,
                  ]}
                >
                  <Text style={styles.historyChatIcon}>💬</Text>
                  <Text
                    style={[
                      styles.historyItemText,
                      isActive && styles.historyItemTextActive,
                    ]}
                    numberOfLines={1}
                  >
                    {item.title}
                  </Text>
                  <TouchableOpacity
                    onPress={() => deleteSession(item.id)}
                    style={styles.deleteButton}
                  >
                    <Text style={styles.deleteIcon}>✕</Text>
                  </TouchableOpacity>
                </TouchableOpacity>
              );
            })}
          </ScrollView>

          {/* Interactive MCQ Drill Button */}
          <TouchableOpacity
            onPress={() => {
              toggleSidebar(false);
              resetMobileQuiz();
              setMcqModalVisible(true);
            }}
            style={[styles.changeTrackButton, { marginBottom: 8, borderColor: 'rgba(245, 158, 11, 0.3)' }]}
          >
            <Text style={styles.changeTrackIcon}>🏆</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.changeTrackLabel}>Exam Drill</Text>
              <Text style={[styles.changeTrackValue, { color: '#fbbf24' }]}>
                Interactive MCQs
              </Text>
            </View>
            <Text style={[styles.changeTrackAction, { color: '#fbbf24' }]}>Start</Text>
          </TouchableOpacity>

          {/* Change Course / Level Button */}
          <TouchableOpacity
            onPress={() => {
              toggleSidebar(false);
              setOnboardingVisible(true);
            }}
            style={styles.changeTrackButton}
          >
            <Text style={styles.changeTrackIcon}>🎓</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.changeTrackLabel}>Exam Track</Text>
              <Text style={styles.changeTrackValue}>
                {studentCourse} {studentLevel}
              </Text>
            </View>
            <Text style={styles.changeTrackAction}>Change</Text>
          </TouchableOpacity>

          {/* Sidebar Footer */}
          <View style={styles.sidebarFooter}>
            <View style={styles.footerAvatar}>
              <Text style={styles.footerAvatarText}>E</Text>
            </View>
            <View>
              <Text style={styles.footerName}>Excel AI Coach</Text>
              <Text style={styles.footerSub}>Excel Educational Institute</Text>
            </View>
          </View>
        </SafeAreaView>
      </Animated.View>

      {/* Onboarding / Change Track Modal */}
      <Modal
        visible={onboardingVisible}
        transparent
        animationType="fade"
        onRequestClose={() => {
          if (studentCourse && studentLevel) setOnboardingVisible(false);
        }}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Choose Your Exam Track</Text>
            <Text style={styles.modalSubtitle}>
              Tailors all doubts, statutory sections, and MCQs to your level.
            </Text>

            <Text style={styles.modalSectionLabel}>1. SELECT COURSE</Text>
            <View style={styles.optionRow}>
              {['CA', 'CS', 'CMA'].map((c) => (
                <TouchableOpacity
                  key={c}
                  onPress={() => {
                    setTempCourse(c);
                    if (c === 'CS') setTempLevel('Executive');
                    else setTempLevel('Inter');
                  }}
                  style={[
                    styles.optionButton,
                    tempCourse === c && styles.optionButtonActive,
                  ]}
                >
                  <Text
                    style={[
                      styles.optionButtonText,
                      tempCourse === c && styles.optionButtonTextActive,
                    ]}
                  >
                    {c}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={styles.modalSectionLabel}>2. SELECT LEVEL</Text>
            <View style={styles.optionRow}>
              {(tempCourse === 'CS'
                ? ['Executive', 'Professional']
                : ['Foundation', 'Inter', 'Final']
              ).map((lvl) => (
                <TouchableOpacity
                  key={lvl}
                  onPress={() => setTempLevel(lvl)}
                  style={[
                    styles.optionButton,
                    tempLevel === lvl && styles.optionButtonActive,
                  ]}
                >
                  <Text
                    style={[
                      styles.optionButtonText,
                      tempLevel === lvl && styles.optionButtonTextActive,
                    ]}
                  >
                    {lvl}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <TouchableOpacity
              onPress={() => saveCourseLevel(tempCourse, tempLevel)}
              style={styles.confirmTrackButton}
            >
              <Text style={styles.confirmTrackButtonText}>
                Confirm Exam Track
              </Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* Interactive MCQ Practice Modal */}
      <Modal
        visible={mcqModalVisible}
        transparent
        animationType="slide"
        onRequestClose={() => setMcqModalVisible(false)}
      >
        <View style={styles.modalBackdrop}>
          <View style={[styles.modalCard, { maxHeight: '90%', width: '92%', padding: 18 }]}>
            {/* Header */}
            <View style={styles.mcqModalHeader}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Text style={{ fontSize: 18 }}>🏆</Text>
                <View>
                  <Text style={styles.modalTitle}>Interactive MCQ Drill</Text>
                  <Text style={styles.modalSubtitle}>
                    {studentCourse} {studentLevel} • Official Exam Standard
                  </Text>
                </View>
              </View>
              <TouchableOpacity
                onPress={() => setMcqModalVisible(false)}
                style={styles.closeModalButton}
              >
                <Text style={styles.closeModalButtonText}>✕</Text>
              </TouchableOpacity>
            </View>

            {/* View 1: Setup View */}
            {!mcqQuizData && !mcqShowResults && (
              <ScrollView style={{ marginTop: 12 }}>
                <Text style={styles.modalSectionLabel}>1. NUMBER OF QUESTIONS</Text>
                <View style={styles.optionRow}>
                  {[5, 10].map((c) => (
                    <TouchableOpacity
                      key={c}
                      onPress={() => setMcqCount(c)}
                      style={[
                        styles.optionButton,
                        mcqCount === c && styles.optionButtonActive,
                      ]}
                    >
                      <Text
                        style={[
                          styles.optionButtonText,
                          mcqCount === c && styles.optionButtonTextActive,
                        ]}
                      >
                        {c} Questions
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>

                <Text style={styles.modalSectionLabel}>2. CHAPTER OR TOPIC (OPTIONAL)</Text>
                <TextInput
                  style={styles.mcqTopicInput}
                  placeholder="e.g. Standard Costing, Section 115BAC, Buyback..."
                  placeholderTextColor="#666"
                  value={mcqCustomTopic}
                  onChangeText={setMcqCustomTopic}
                />

                <TouchableOpacity
                  onPress={startMobileQuiz}
                  disabled={mcqLoading}
                  style={[styles.confirmTrackButton, { marginTop: 24 }]}
                >
                  {mcqLoading ? (
                    <ActivityIndicator color="#0f172a" />
                  ) : (
                    <Text style={styles.confirmTrackButtonText}>
                      Start {mcqCount}-Question Interactive Drill
                    </Text>
                  )}
                </TouchableOpacity>
              </ScrollView>
            )}

            {/* View 2: Active Quiz Taking View */}
            {mcqQuizData && !mcqShowResults && (
              <ScrollView style={{ marginTop: 10 }}>
                {(() => {
                  const q = mcqQuizData.questions[mcqCurrentIndex];
                  const total = mcqQuizData.questions.length;
                  const correctKey = (q.correct_answer || q.correct_option || '').toUpperCase().trim();
                  const isSubmitted = Boolean(mcqSubmittedQuestions[mcqCurrentIndex]);
                  const userChoice = mcqUserAnswers[mcqCurrentIndex];

                  return (
                    <View>
                      {/* Counter */}
                      <View style={styles.mcqProgressRow}>
                        <Text style={styles.mcqCounterText}>
                          Question {mcqCurrentIndex + 1} of {total}
                        </Text>
                        <Text style={styles.mcqStatusText}>
                          {Object.keys(mcqSubmittedQuestions).length} of {total} completed
                        </Text>
                      </View>

                      {/* Question Card */}
                      <View style={styles.mcqQuestionCard}>
                        <Text style={styles.mcqQuestionText}>
                          {cleanExamMarkdown(q.question)}
                        </Text>
                      </View>

                      {/* 4 Options */}
                      <View style={{ gap: 8, marginTop: 12 }}>
                        {['A', 'B', 'C', 'D'].map((key) => {
                          const optText = cleanExamMarkdown(q.options[key] || '');
                          const isSelected = userChoice === key;

                          let btnStyle = styles.mcqOptionNormal;
                          let textStyle = styles.mcqOptionTextNormal;

                          if (!isSubmitted) {
                            if (isSelected) {
                              btnStyle = styles.mcqOptionSelected;
                              textStyle = styles.mcqOptionTextSelected;
                            }
                          } else {
                            if (key === correctKey) {
                              btnStyle = styles.mcqOptionCorrect;
                              textStyle = styles.mcqOptionTextCorrect;
                            } else if (isSelected && key !== correctKey) {
                              btnStyle = styles.mcqOptionIncorrect;
                              textStyle = styles.mcqOptionTextIncorrect;
                            }
                          }

                          return (
                            <TouchableOpacity
                              key={key}
                              onPress={() => selectMobileOption(key)}
                              disabled={isSubmitted}
                              style={[styles.mcqOptionButton, btnStyle]}
                            >
                              <View style={styles.mcqOptionBadge}>
                                <Text style={styles.mcqOptionBadgeText}>{key}</Text>
                              </View>
                              <Text style={[styles.mcqOptionText, textStyle]}>
                                {optText}
                              </Text>
                            </TouchableOpacity>
                          );
                        })}
                      </View>

                      {/* Instant Feedback & Reasoning Box */}
                      {isSubmitted && (
                        <View style={styles.mcqReasoningCard}>
                          <Text style={styles.mcqReasoningTitle}>
                            💡 Reasoning & Working Notes:
                          </Text>
                          <Text style={styles.mcqReasoningBody}>
                            {cleanExamMarkdown(q.explanation)}
                          </Text>
                        </View>
                      )}

                      {/* Navigation Actions */}
                      <View style={styles.mcqNavRow}>
                        {!isSubmitted ? (
                          <TouchableOpacity
                            onPress={submitMobileQuestion}
                            disabled={!userChoice}
                            style={[
                              styles.mcqSubmitButton,
                              !userChoice && { opacity: 0.4 },
                            ]}
                          >
                            <Text style={styles.mcqSubmitButtonText}>
                              Check Answer
                            </Text>
                          </TouchableOpacity>
                        ) : (
                          <TouchableOpacity
                            onPress={nextMobileQuestion}
                            style={styles.mcqNextButton}
                          >
                            <Text style={styles.mcqNextButtonText}>
                              {mcqCurrentIndex === total - 1
                                ? 'Finish & View Score'
                                : 'Next Question →'}
                            </Text>
                          </TouchableOpacity>
                        )}
                      </View>
                    </View>
                  );
                })()}
              </ScrollView>
            )}

            {/* View 3: Results View */}
            {mcqQuizData && mcqShowResults && (
              <ScrollView style={{ marginTop: 10 }}>
                {(() => {
                  const total = mcqQuizData.questions.length;
                  let correctCount = 0;
                  mcqQuizData.questions.forEach((q, idx) => {
                    const cKey = (q.correct_answer || q.correct_option || '').toUpperCase().trim();
                    if (mcqUserAnswers[idx] === cKey) correctCount++;
                  });
                  const scorePct = Math.round((correctCount / total) * 100);

                  return (
                    <View>
                      <View style={styles.mcqScoreCard}>
                        <Text style={{ fontSize: 32 }}>🏆</Text>
                        <Text style={styles.mcqScoreTitle}>Your Score</Text>
                        <Text style={styles.mcqScoreNumber}>
                          {correctCount} / {total} ({scorePct}%)
                        </Text>
                        <Text style={styles.mcqFeedbackText}>
                          {scorePct >= 80
                            ? 'Ranker Standard! Flawless conceptual mastery.'
                            : scorePct >= 60
                            ? 'Exam Pass Standard! Strong command with minor revisions.'
                            : 'Focus Needed! Review the solutions below.'}
                        </Text>
                      </View>

                      {/* Solutions list */}
                      <Text style={[styles.modalSectionLabel, { marginTop: 16 }]}>
                        QUESTION-BY-QUESTION SOLUTIONS
                      </Text>
                      {mcqQuizData.questions.map((q, idx) => {
                        const cKey = (q.correct_answer || q.correct_option || '').toUpperCase().trim();
                        const picked = mcqUserAnswers[idx];
                        const isCorrect = picked === cKey;

                        return (
                          <View key={idx} style={styles.mcqReviewItem}>
                            <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 }}>
                              <Text style={styles.mcqReviewNum}>Q{idx + 1}</Text>
                              <Text style={[styles.mcqReviewStatus, { color: isCorrect ? '#34d399' : '#f87171' }]}>
                                {isCorrect ? '✓ Correct' : `✗ Selected ${picked || 'None'}`}
                              </Text>
                            </View>
                            <Text style={styles.mcqReviewQuestion}>{cleanExamMarkdown(q.question)}</Text>
                            <Text style={styles.mcqReviewCorrect}>Correct Answer: ({cKey}) {cleanExamMarkdown(q.options[cKey] || '')}</Text>
                            <Text style={styles.mcqReviewExplanation}>💡 {cleanExamMarkdown(q.explanation)}</Text>
                          </View>
                        );
                      })}

                      <TouchableOpacity
                        onPress={resetMobileQuiz}
                        style={[styles.confirmTrackButton, { marginTop: 16, backgroundColor: '#333' }]}
                      >
                        <Text style={[styles.confirmTrackButtonText, { color: '#fbbf24' }]}>
                          Retake / Practice Another
                        </Text>
                      </TouchableOpacity>
                    </View>
                  );
                })()}
              </ScrollView>
            )}
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#212121',
  },
  header: {
    height: 54,
    borderBottomWidth: 1,
    borderBottomColor: '#2f2f2f',
    backgroundColor: '#171717',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
  },
  headerButton: {
    width: 38,
    height: 38,
    borderRadius: 10,
    backgroundColor: '#242424',
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerIconText: {
    color: '#ffffff',
    fontSize: 18,
    fontWeight: 'bold',
  },
  headerTitleContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  headerTitle: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: 'bold',
  },
  headerBadge: {
    backgroundColor: 'rgba(245, 158, 11, 0.15)',
    borderColor: 'rgba(245, 158, 11, 0.3)',
    borderWidth: 1,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 12,
  },
  headerBadgeText: {
    color: '#f59e0b',
    fontSize: 10,
    fontWeight: 'bold',
  },
  chatContainer: {
    flex: 1,
  },
  scrollContent: {
    padding: 16,
    paddingBottom: 20,
  },
  welcomeBox: {
    alignItems: 'center',
    marginVertical: 40,
  },
  welcomeAvatar: {
    width: 60,
    height: 60,
    borderRadius: 20,
    backgroundColor: '#f59e0b',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
  },
  welcomeAvatarText: {
    fontSize: 28,
    fontWeight: '900',
    color: '#171717',
  },
  welcomeTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#ffffff',
    textAlign: 'center',
    marginBottom: 6,
  },
  welcomeSubtitle: {
    fontSize: 13,
    color: '#999999',
    textAlign: 'center',
    paddingHorizontal: 20,
    marginBottom: 24,
  },
  suggestionsContainer: {
    width: '100%',
    gap: 10,
  },
  suggestionCard: {
    backgroundColor: '#282828',
    borderColor: '#383838',
    borderWidth: 1,
    borderRadius: 16,
    padding: 14,
  },
  suggestionTitle: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: 'bold',
    marginBottom: 4,
  },
  suggestionDesc: {
    color: '#aaaaaa',
    fontSize: 12,
  },
  messageWrapper: {
    flexDirection: 'row',
    marginBottom: 18,
    alignItems: 'flex-start',
  },
  userWrapper: {
    justifyContent: 'flex-end',
  },
  assistantWrapper: {
    justifyContent: 'flex-start',
  },
  assistantAvatar: {
    width: 32,
    height: 32,
    borderRadius: 10,
    backgroundColor: '#f59e0b',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 10,
    marginTop: 2,
  },
  assistantAvatarText: {
    fontSize: 15,
    fontWeight: '900',
    color: '#171717',
  },
  messageBubble: {
    maxWidth: '82%',
    borderRadius: 20,
    paddingHorizontal: 15,
    paddingVertical: 12,
  },
  userBubble: {
    backgroundColor: '#2f2f2f',
    borderColor: '#404040',
    borderWidth: 1,
    borderTopRightRadius: 4,
  },
  assistantBubble: {
    backgroundColor: '#262626',
    borderColor: '#333333',
    borderWidth: 1,
    borderTopLeftRadius: 4,
    flex: 1,
  },
  userText: {
    color: '#ffffff',
    fontSize: 14,
    lineHeight: 20,
  },
  assistantText: {
    color: '#dddddd',
    fontSize: 14,
    lineHeight: 22,
  },
  uploadedImage: {
    width: 180,
    height: 120,
    borderRadius: 10,
    marginBottom: 8,
  },
  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  loadingText: {
    color: '#aaaaaa',
    fontSize: 12,
  },
  imagePreviewPill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#2d2d2d',
    borderColor: '#444444',
    borderWidth: 1,
    borderRadius: 12,
    paddingHorizontal: 10,
    paddingVertical: 6,
    marginHorizontal: 16,
    marginBottom: 8,
    gap: 8,
  },
  pillThumb: {
    width: 24,
    height: 24,
    borderRadius: 4,
  },
  pillText: {
    flex: 1,
    color: '#ffffff',
    fontSize: 11,
  },
  pillRemove: {
    color: '#aaaaaa',
    fontSize: 14,
    paddingHorizontal: 4,
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    backgroundColor: '#2d2d2d',
    borderColor: '#3f3f3f',
    borderWidth: 1,
    borderRadius: 28,
    marginHorizontal: 14,
    marginBottom: 12,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  iconButton: {
    padding: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  attachIcon: {
    fontSize: 18,
    color: '#aaaaaa',
  },
  inputField: {
    flex: 1,
    color: '#ffffff',
    fontSize: 14,
    paddingVertical: 6,
    paddingHorizontal: 8,
    maxHeight: 100,
  },
  sendButton: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: '#ffffff',
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 4,
  },
  sendButtonDisabled: {
    backgroundColor: '#555555',
    opacity: 0.5,
  },
  sendIcon: {
    color: '#171717',
    fontSize: 18,
    fontWeight: 'bold',
  },
  drawerBackdrop: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.6)',
    zIndex: 99,
  },
  sidebar: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    left: 0,
    width: SCREEN_WIDTH * 0.78,
    backgroundColor: '#171717',
    borderRightWidth: 1,
    borderRightColor: '#2f2f2f',
    zIndex: 100,
  },
  sidebarInner: {
    flex: 1,
  },
  sidebarHeader: {
    padding: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#262626',
  },
  newChatSidebarButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#242424',
    borderColor: '#333333',
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 14,
  },
  newChatPlus: {
    fontSize: 18,
    color: '#f59e0b',
    fontWeight: 'bold',
  },
  newChatText: {
    color: '#ffffff',
    fontSize: 13,
    fontWeight: 'bold',
  },
  sidebarSectionTitle: {
    color: '#777777',
    fontSize: 10,
    fontWeight: 'bold',
    letterSpacing: 1,
    paddingHorizontal: 16,
    marginTop: 16,
    marginBottom: 8,
  },
  historyList: {
    flex: 1,
    paddingHorizontal: 8,
  },
  historyItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 12,
    marginBottom: 4,
  },
  historyItemActive: {
    backgroundColor: '#262626',
    borderColor: '#383838',
    borderWidth: 1,
  },
  historyChatIcon: {
    marginRight: 10,
    fontSize: 13,
  },
  historyItemText: {
    flex: 1,
    color: '#999999',
    fontSize: 13,
  },
  historyItemTextActive: {
    color: '#ffffff',
    fontWeight: 'bold',
  },
  deleteButton: {
    padding: 4,
  },
  deleteIcon: {
    color: '#777777',
    fontSize: 12,
  },
  sidebarFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    padding: 14,
    borderTopWidth: 1,
    borderTopColor: '#262626',
    backgroundColor: '#121212',
  },
  footerAvatar: {
    width: 32,
    height: 32,
    borderRadius: 8,
    backgroundColor: '#f59e0b',
    alignItems: 'center',
    justifyContent: 'center',
  },
  footerAvatarText: {
    color: '#171717',
    fontSize: 16,
    fontWeight: '900',
  },
  footerName: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: 'bold',
  },
  footerSub: {
    color: '#777777',
    fontSize: 10,
  },
  changeTrackButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1f1f1f',
    borderColor: '#333333',
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 14,
    marginHorizontal: 12,
    marginBottom: 8,
    gap: 8,
  },
  changeTrackIcon: {
    fontSize: 16,
  },
  changeTrackLabel: {
    color: '#888888',
    fontSize: 10,
    fontWeight: 'bold',
    textTransform: 'uppercase',
  },
  changeTrackValue: {
    color: '#f59e0b',
    fontSize: 12,
    fontWeight: 'bold',
  },
  changeTrackAction: {
    color: '#ffffff',
    fontSize: 11,
    fontWeight: '600',
    backgroundColor: '#2e2e2e',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 8,
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.85)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  modalCard: {
    backgroundColor: '#1e1e1e',
    borderColor: '#383838',
    borderWidth: 1,
    borderRadius: 24,
    width: '100%',
    maxWidth: 400,
    padding: 22,
  },
  modalTitle: {
    color: '#ffffff',
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 4,
  },
  modalSubtitle: {
    color: '#999999',
    fontSize: 12,
    marginBottom: 16,
  },
  modalSectionLabel: {
    color: '#aaaaaa',
    fontSize: 10,
    fontWeight: 'bold',
    letterSpacing: 1,
    marginBottom: 8,
    marginTop: 8,
  },
  optionRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 10,
  },
  optionButton: {
    flex: 1,
    backgroundColor: '#2a2a2a',
    borderColor: '#3e3e3e',
    borderWidth: 1,
    paddingVertical: 10,
    borderRadius: 12,
    alignItems: 'center',
  },
  optionButtonActive: {
    backgroundColor: '#f59e0b',
    borderColor: '#f59e0b',
  },
  optionButtonText: {
    color: '#cccccc',
    fontSize: 12,
    fontWeight: 'bold',
  },
  optionButtonTextActive: {
    color: '#171717',
    fontWeight: '900',
  },
  confirmTrackButton: {
    backgroundColor: '#f59e0b',
    paddingVertical: 14,
    borderRadius: 14,
    alignItems: 'center',
    marginTop: 16,
  },
  confirmTrackButtonText: {
    color: '#171717',
    fontSize: 13,
    fontWeight: '900',
  },
  mcqModalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#333',
  },
  closeModalButton: {
    padding: 6,
  },
  closeModalButtonText: {
    color: '#888',
    fontSize: 18,
    fontWeight: 'bold',
  },
  mcqTopicInput: {
    backgroundColor: '#262626',
    borderColor: '#383838',
    borderWidth: 1,
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: '#fff',
    fontSize: 13,
  },
  mcqProgressRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  mcqCounterText: {
    color: '#fbbf24',
    fontSize: 12,
    fontWeight: 'bold',
  },
  mcqStatusText: {
    color: '#888',
    fontSize: 11,
  },
  mcqQuestionCard: {
    backgroundColor: '#262626',
    borderColor: '#383838',
    borderWidth: 1,
    borderRadius: 14,
    padding: 14,
    marginBottom: 6,
  },
  mcqQuestionText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
    lineHeight: 20,
  },
  mcqOptionButton: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    borderRadius: 12,
    borderWidth: 1.5,
    gap: 10,
  },
  mcqOptionNormal: {
    backgroundColor: '#262626',
    borderColor: '#383838',
  },
  mcqOptionSelected: {
    backgroundColor: 'rgba(245, 158, 11, 0.15)',
    borderColor: '#f59e0b',
  },
  mcqOptionCorrect: {
    backgroundColor: 'rgba(16, 185, 129, 0.2)',
    borderColor: '#10b981',
  },
  mcqOptionIncorrect: {
    backgroundColor: 'rgba(239, 68, 68, 0.2)',
    borderColor: '#ef4444',
  },
  mcqOptionBadge: {
    width: 26,
    height: 26,
    borderRadius: 8,
    backgroundColor: '#333',
    alignItems: 'center',
    justifyContent: 'center',
  },
  mcqOptionBadgeText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: 'bold',
  },
  mcqOptionText: {
    flex: 1,
    fontSize: 13,
  },
  mcqOptionTextNormal: {
    color: '#e5e5e5',
  },
  mcqOptionTextSelected: {
    color: '#fbbf24',
    fontWeight: '600',
  },
  mcqOptionTextCorrect: {
    color: '#34d399',
    fontWeight: '600',
  },
  mcqOptionTextIncorrect: {
    color: '#f87171',
  },
  mcqReasoningCard: {
    backgroundColor: '#122014',
    borderColor: 'rgba(16, 185, 129, 0.4)',
    borderWidth: 1,
    borderRadius: 12,
    padding: 12,
    marginTop: 12,
  },
  mcqReasoningTitle: {
    color: '#34d399',
    fontSize: 12,
    fontWeight: 'bold',
    marginBottom: 4,
  },
  mcqReasoningBody: {
    color: '#d1fae5',
    fontSize: 12,
    lineHeight: 18,
  },
  mcqNavRow: {
    marginTop: 14,
    alignItems: 'flex-end',
  },
  mcqSubmitButton: {
    backgroundColor: '#f59e0b',
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 12,
  },
  mcqSubmitButtonText: {
    color: '#0f172a',
    fontSize: 13,
    fontWeight: 'bold',
  },
  mcqNextButton: {
    backgroundColor: '#f59e0b',
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 12,
  },
  mcqNextButtonText: {
    color: '#0f172a',
    fontSize: 13,
    fontWeight: 'bold',
  },
  mcqScoreCard: {
    backgroundColor: '#262626',
    borderColor: 'rgba(245, 158, 11, 0.4)',
    borderWidth: 1,
    borderRadius: 16,
    padding: 20,
    alignItems: 'center',
    gap: 6,
  },
  mcqScoreTitle: {
    color: '#aaa',
    fontSize: 11,
    fontWeight: 'bold',
    textTransform: 'uppercase',
  },
  mcqScoreNumber: {
    color: '#fff',
    fontSize: 26,
    fontWeight: 'bold',
  },
  mcqFeedbackText: {
    color: '#fbbf24',
    fontSize: 12,
    textAlign: 'center',
  },
  mcqReviewItem: {
    backgroundColor: '#262626',
    borderColor: '#383838',
    borderWidth: 1,
    borderRadius: 12,
    padding: 12,
    marginBottom: 10,
  },
  mcqReviewNum: {
    color: '#aaa',
    fontSize: 11,
    fontWeight: 'bold',
  },
  mcqReviewStatus: {
    fontSize: 11,
    fontWeight: 'bold',
  },
  mcqReviewQuestion: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '600',
    marginBottom: 6,
  },
  mcqReviewCorrect: {
    color: '#34d399',
    fontSize: 12,
    fontWeight: '600',
    marginBottom: 4,
  },
  mcqReviewExplanation: {
    color: '#a3a3a3',
    fontSize: 11,
    lineHeight: 16,
  },
});
