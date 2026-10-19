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

const CLOUD_API_URL = 'https://excel-ai-backend-yegx.onrender.com/api/chat';
const { width: SCREEN_WIDTH } = Dimensions.get('window');

export default function App() {
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
        text: replyText,
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
          <View style={styles.headerBadge}>
            <Text style={styles.headerBadgeText}>ICAI / ICSI</Text>
          </View>
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
});
