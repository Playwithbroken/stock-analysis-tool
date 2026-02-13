import React, { useState, useEffect, useRef } from "react";
import { MessageSquare, X, Send, Bot, User, Trash2 } from "lucide-react";

interface Message {
  role: "user" | "oracle";
  content: string;
}

interface BrokerChatProps {
  currentTicker?: string | string[];
  isInline?: boolean;
  initialMessage?: string;
  onClose?: () => void;
  isOpen?: boolean;
  setIsOpen?: (open: boolean) => void;
}

export default function BrokerChat({
  currentTicker,
  isInline = false,
  initialMessage,
  onClose,
  isOpen: externalIsOpen,
  setIsOpen: externalSetIsOpen,
}: BrokerChatProps) {
  const [internalIsOpen, setInternalIsOpen] = useState(false);

  // Use external state if provided, otherwise fallback to internal
  const isOpen = externalIsOpen !== undefined ? externalIsOpen : internalIsOpen;
  const setIsOpen =
    externalSetIsOpen !== undefined ? externalSetIsOpen : setInternalIsOpen;

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (initialMessage) {
      setMessages([
        {
          role: "oracle",
          content: initialMessage,
        },
      ]);
    } else {
      setMessages([
        {
          role: "oracle",
          content:
            "Hallo! Ich bin dein Broker Freund AI. Ich kenne dein Portfolio und den Markt. Was möchtest du wissen?",
        },
      ]);
    }
  }, [initialMessage]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMsg = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setLoading(true);

    try {
      const response = await fetch("/api/oracle/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: input,
          context_ticker: Array.isArray(currentTicker)
            ? currentTicker.join(",")
            : currentTicker,
        }),
      });
      const data = await response.json();
      setMessages((prev) => [
        ...prev,
        { role: "oracle", content: data.response },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "oracle",
          content:
            "Entschuldigung, Verbindung unterbrochen. Versuche es gleich nochmal.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const chatContent = (
    <div
      className={`${isInline ? "h-full flex flex-col" : "fixed inset-y-0 right-0 w-full max-w-md bg-[#020203] border-l border-white/10 shadow-2xl z-50 flex flex-col backdrop-blur-3xl bg-opacity-95"}`}
    >
      {/* Header */}
      <div
        className={`p-6 border-b border-white/10 flex justify-between items-center bg-linear-to-r from-purple-900/20 to-transparent ${isInline ? "px-0 pt-0" : ""}`}
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-purple-600/20 rounded-xl flex items-center justify-center border border-purple-500/40">
            <Bot size={24} className="text-purple-400" />
          </div>
          <div>
            <h3 className="font-bold text-white text-lg">Broker Freund AI</h3>
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse"></span>
              <span className="text-[10px] text-gray-400 uppercase tracking-widest font-bold">
                Live AI Insights
              </span>
            </div>
          </div>
        </div>
        {!isInline && (
          <button
            onClick={() => setIsOpen(false)}
            className="p-2 hover:bg-white/5 rounded-lg text-gray-500 hover:text-white transition-all"
          >
            <X size={20} />
          </button>
        )}
      </div>

      {/* Messages */}
      <div
        className={`flex-1 overflow-y-auto ${isInline ? "py-4 px-0" : "p-6"} space-y-6 scrollbar-hide`}
      >
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}
            >
              <div
                className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 border ${msg.role === "user" ? "bg-blue-600/20 border-blue-500/20" : "bg-purple-600/20 border-purple-500/20"}`}
              >
                {msg.role === "user" ? (
                  <User size={16} className="text-blue-400" />
                ) : (
                  <Bot size={16} className="text-purple-400" />
                )}
              </div>
              <div
                className={`p-4 rounded-2xl text-sm leading-relaxed ${msg.role === "user" ? "bg-blue-600/10 text-blue-50 border border-blue-500/10" : "bg-white/3 text-gray-100 border border-white/5"}`}
              >
                {msg.content}
              </div>
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-white/3 border border-white/5 p-4 rounded-2xl flex gap-2 items-center">
              <span className="w-1.5 h-1.5 bg-purple-500 rounded-full animate-bounce"></span>
              <span className="w-1.5 h-1.5 bg-purple-500 rounded-full animate-bounce [animation-delay:0.2s]"></span>
              <span className="w-1.5 h-1.5 bg-purple-500 rounded-full animate-bounce [animation-delay:0.4s]"></span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div
        className={`${isInline ? "pt-4 border-t border-white/10" : "p-6 border-t border-white/10 bg-black/40"}`}
      >
        {currentTicker && !isInline && (
          <div className="mb-4 flex items-center gap-2">
            <span className="text-[10px] text-purple-400 font-bold uppercase tracking-widest px-2 py-1 bg-purple-500/10 rounded-md border border-purple-500/20">
              Kontext: {currentTicker}
            </span>
          </div>
        )}
        <div className="relative">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Frage den Broker Freund..."
            className="w-full pl-4 pr-12 py-3.5 bg-white/3 border border-white/10 rounded-xl text-white placeholder-gray-600 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500/20 transition-all text-sm"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg disabled:opacity-50 transition-all"
          >
            <Send size={18} />
          </button>
        </div>
        {!isInline && (
          <p className="text-[10px] text-gray-600 mt-4 text-center">
            Broker Freund AI analysiert Live-Daten. Keine direkte
            Anlageberatung.
          </p>
        )}
      </div>
    </div>
  );

  if (isInline) return chatContent;

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-8 right-8 w-16 h-16 bg-linear-to-br from-purple-600 to-indigo-700 rounded-full shadow-2xl shadow-purple-500/40 flex items-center justify-center text-white hover:scale-110 active:scale-95 transition-all z-40 border border-white/10 group"
      >
        <div className="absolute inset-0 bg-purple-500 rounded-full animate-ping opacity-20 group-hover:opacity-40"></div>
        <Bot size={32} />
      </button>

      {isOpen && chatContent}
    </>
  );
}
