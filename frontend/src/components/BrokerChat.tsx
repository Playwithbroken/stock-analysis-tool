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
      className={`${
        isInline
          ? "flex h-full flex-col"
          : "surface-panel fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-black/8 bg-[rgba(250,248,244,0.96)] shadow-[-20px_0_50px_rgba(17,24,39,0.12)] backdrop-blur-3xl"
      }`}
    >
      {/* Header */}
      <div
        className={`flex items-center justify-between border-b border-black/8 bg-[linear-gradient(90deg,rgba(15,118,110,0.08),transparent)] p-6 ${isInline ? "px-0 pt-0" : ""}`}
      >
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--accent)]/15 bg-[var(--accent-soft)]">
            <Bot size={24} className="text-[var(--accent)]" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-900">Broker Freund AI</h3>
            <div className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
              <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
                Live AI Insights
              </span>
            </div>
          </div>
        </div>
        {!isInline && (
          <button
            onClick={() => setIsOpen(false)}
            className="rounded-lg p-2 text-slate-500 transition-all hover:bg-black/[0.04] hover:text-slate-900"
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
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border ${
                  msg.role === "user"
                    ? "border-slate-300 bg-slate-200/70"
                    : "border-[var(--accent)]/15 bg-[var(--accent-soft)]"
                }`}
              >
                {msg.role === "user" ? (
                  <User size={16} className="text-slate-700" />
                ) : (
                  <Bot size={16} className="text-[var(--accent)]" />
                )}
              </div>
              <div
                className={`rounded-2xl border p-4 text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "border-slate-300 bg-slate-100 text-slate-800"
                    : "border-black/8 bg-white/80 text-slate-700"
                }`}
              >
                {msg.content}
              </div>
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-2xl border border-black/8 bg-white/80 p-4">
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] animate-bounce"></span>
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:0.2s]"></span>
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:0.4s]"></span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div
        className={`${isInline ? "border-t border-black/8 pt-4" : "border-t border-black/8 bg-white/60 p-6"}`}
      >
        {currentTicker && !isInline && (
          <div className="mb-4 flex items-center gap-2">
            <span className="rounded-md border border-[var(--accent)]/15 bg-[var(--accent-soft)] px-2 py-1 text-[10px] font-bold uppercase tracking-widest text-[var(--accent)]">
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
            className="w-full rounded-xl border border-black/8 bg-white pl-4 pr-12 py-3.5 text-sm text-slate-900 placeholder:text-slate-400 transition-all focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/20"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg bg-[var(--accent)] p-2 text-white transition-all hover:bg-[var(--accent-strong)] disabled:opacity-50"
          >
            <Send size={18} />
          </button>
        </div>
        {!isInline && (
          <p className="mt-4 text-center text-[10px] text-slate-500">
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
        className="fixed bottom-8 right-8 z-40 flex h-16 w-16 items-center justify-center rounded-full border border-[var(--accent)]/20 bg-[var(--accent)] text-white shadow-[0_22px_48px_rgba(15,118,110,0.28)] transition-all hover:scale-110 hover:bg-[var(--accent-strong)] active:scale-95 group"
      >
        <div className="absolute inset-0 rounded-full bg-[var(--accent)] animate-ping opacity-15 group-hover:opacity-30"></div>
        <Bot size={32} />
      </button>

      {isOpen && chatContent}
    </>
  );
}
