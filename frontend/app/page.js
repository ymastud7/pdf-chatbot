'use client';

import { useState, useRef, useEffect } from 'react';
import './globals.css';

export default function Home() {
  // State management
  const [file, setFile] = useState(null);
  const [docId, setDocId] = useState('');
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [query, setQuery] = useState('');
  const [conversationId, setConversationId] = useState(null); // Track conversation
  
  // Refs
  const fileInputRef = useRef(null);
  const messagesEndRef = useRef(null);
  
  // Scroll to bottom of messages
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };
  
  useEffect(() => {
    scrollToBottom();
  }, [messages]);
  
  // Check if document processing is complete using Server-Sent Events
  useEffect(() => {
    let eventSource;
    
    if (docId && isProcessing) {
      // Create EventSource connection
      eventSource = new EventSource(`http://localhost:8000/sse/document-status/${docId}`);
      
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.status === "processed") {
            // Document is ready
            setIsProcessing(false);
            setMessages(prev => [...prev.filter(msg => msg.sender !== "system"), {
              id: Date.now(),
              text: "Document processing complete! You can now ask questions about your document.",
              sender: "system"
            }]);
            
            // Close the connection
            if (eventSource) {
              eventSource.close();
            }
          }
        } catch (error) {
          console.error("Error parsing SSE data:", error);
        }
      };
      
      eventSource.onerror = (error) => {
        console.error("SSE error:", error);
        // Optionally close connection on error
        // eventSource.close();
      };
    }
    
    // Cleanup function
    return () => {
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [docId, isProcessing]);
  
  // Handle file selection
  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };
  
  // Handle file upload
  const handleUpload = async () => {
    if (!file) return;
    
    setIsLoading(true);
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const response = await fetch('http://localhost:8000/upload', {
        method: 'POST',
        body: formData,
      });
      
      if (!response.ok) {
        throw new Error('Upload failed');
      }
      
      const data = await response.json();
      setDocId(data.doc_id);
      setIsProcessing(true);
      
      // Add system message
      setMessages([
        {
          id: Date.now(),
          text: "Your document is being processed in the background. This may take a minute...",
          sender: "system"
        }
      ]);
    } catch (error) {
      console.error('Upload error:', error);
      setMessages(prev => [...prev, {
        id: Date.now(),
        text: "Sorry, there was an error uploading your document. Please try again.",
        sender: "system"
      }]);
    } finally {
      setIsLoading(false);
    }
  };
  
  // Handle sending messages
  const handleSendMessage = async (e) => {
    e.preventDefault();
    
    if (!query.trim() || !docId) return;
    
    // Add user message
    const userMessage = {
      id: Date.now(),
      text: query,
      sender: "user"
    };
    
    setMessages(prev => [...prev, userMessage]);
    setIsLoading(true);
    const currentQuery = query;
    setQuery('');
    
    try {
      const requestBody = {
        doc_id: docId,
        query: currentQuery
      };
      
      // Include conversation ID if we have one
      if (conversationId) {
        requestBody.conversation_id = conversationId;
      }
      
      const response = await fetch('http://localhost:8000/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Chat request failed');
      }
      
      const data = await response.json();
      
      // Store conversation ID for future messages
      if (data.conversation_id && !conversationId) {
        setConversationId(data.conversation_id);
      }
      
      // Add AI message
      const aiMessage = {
        id: Date.now() + 1,
        text: data.answer,
        sender: "ai"
      };
      
      setMessages(prev => [...prev, aiMessage]);
    } catch (error) {
      console.error('Chat error:', error);
      let errorMessage = "Sorry, I encountered an error while processing your question. Please try again.";
      
      // Handle specific error cases
      if (error.message.includes("not found")) {
        errorMessage = "Your document is still being processed. Please wait a moment and try again.";
        // Keep the processing message visible
        setIsProcessing(true);
      } else if (error.message.includes("failed")) {
        errorMessage = `There was an issue processing your request: ${error.message}`;
      }
      
      setMessages(prev => [...prev, {
        id: Date.now(),
        text: errorMessage,
        sender: "system"
      }]);
    } finally {
      setIsLoading(false);
    }
  };
  
  // Reset the chat
  const resetChat = () => {
    setFile(null);
    setDocId('');
    setMessages([]);
    setIsProcessing(false);
    setQuery('');
    setConversationId(null); // Reset conversation context
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };
  
  return (
    <div className="container">
      <div className="header">
        <h1>PDF Chatbot</h1>
        <p>Upload a PDF document and ask questions about its content</p>
      </div>
      
      <div className={`card ${docId ? 'hidden' : ''}`}>
        <div className="upload-container">
          <div 
            className="upload-area"
            onClick={() => fileInputRef.current?.click()}
          >
            <div className="upload-icon">📁</div>
            <div className="upload-text">
              <h2>Upload PDF Document</h2>
              <p>Click to browse or drag and drop your PDF file here</p>
            </div>
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept=".pdf"
              className="file-input"
            />
          </div>
          
          <button
            className="upload-button"
            onClick={handleUpload}
            disabled={!file || isLoading}
          >
            {isLoading ? 'Uploading...' : 'Upload Document'}
          </button>
          
          {file && (
            <div>
              <p>Selected file: {file.name}</p>
            </div>
          )}
        </div>
      </div>
      
      <div className={`card ${!docId ? 'hidden' : ''}`}>
        <div className="processing-message" style={{ display: isProcessing ? 'block' : 'none' }}>
          <p>⏳ Your document is being processed in the background...</p>
          <p>This may take a minute. You can start asking questions once processing is complete.</p>
        </div>
        
        <div className="chat-container">
          <div className="messages-container">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`message ${
                  message.sender === 'user' 
                    ? 'user-message' 
                    : message.sender === 'ai' 
                      ? 'ai-message' 
                      : ''
                }`}
              >
                <div className="message-header">
                  {message.sender === 'user' 
                    ? 'You' 
                    : message.sender === 'ai' 
                      ? 'AI Assistant' 
                      : 'System'}
                </div>
                <div className="message-text">{message.text}</div>
              </div>
            ))}
            {isLoading && (
              <div className="message ai-message">
                <div className="message-header">AI Assistant</div>
                <div className="loading">
                  <div className="spinner"></div>
                  <span>Thinking...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
          
          <form className="input-container" onSubmit={handleSendMessage}>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask a question about your document..."
              disabled={isProcessing || isLoading}
            />
            <button 
              type="submit" 
              disabled={!query.trim() || isProcessing || isLoading}
            >
              Send
            </button>
          </form>
        </div>
        
        <div style={{ marginTop: '20px', textAlign: 'center' }}>
          <button onClick={resetChat} className="upload-button">
            Upload New Document
          </button>
        </div>
      </div>
    </div>
  );
}