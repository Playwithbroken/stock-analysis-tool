import React, { useEffect, useRef, useState } from "react";
import { X, Send, Bot, User } from "lucide-react";

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
  const isOpen = externalIsOpen !== undefined ? externalIsOpen : internalIsOpen;
  const setIsOpen =
    externalSetIsOpen !== undefined ? externalSetIsOpen : setInternalIsOpen;

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMessages([
      {
        role: "oracle",
        content:
          initialMessage ||
          "Hallo. Ich bin dein Broker Freund Desk. Ich kenne dein Portfolio, deine Signale und den Markt. Was willst du zuerst einordnen?",
      },
    ]);
  }, [initialMessage]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
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
          message: userMsg,
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
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "oracle",
          content:
            "Verbindung kurz unterbrochen. Versuch es direkt noch einmal.",
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
          : "surface-panel fixed inset-x-3 bottom-24 top-auto z-50 flex h-[min(72vh,44rem)] w-auto flex-col overflow-hidden rounded-[2rem] border border-black/8 bg-[rgba(250,248,244,0.98)] shadow-[0_-18px_48px_rgba(17,24,39,0.18)] backdrop-blur-3xl md:inset-y-0 md:right-0 md:left-auto md:bottom-0 md:top-0 md:h-auto md:w-full md:max-w-md md:rounded-none md:rounded-l-[2rem] md:border-l md:border-t-0 md:shadow-[-20px_0_50px_rgba(17,24,39,0.12)] xl:max-w-[28rem] 2xl:max-w-[31rem]"
      }`}
    >
      <div
        className={`flex items-center justify-between border-b border-black/8 bg-[linear-gradient(90deg,rgba(15,118,110,0.08),transparent)] p-6 ${isInline ? "px-0 pt-0" : ""}`}
      >
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-[1rem] border border-[var(--accent)]/15 bg-[var(--accent-soft)] text-[var(--accent)]">
            <Bot size={22} />
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-900">Broker Freund Desk</h3>
            <div className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
              <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
                Live market context
              </span>
            </div>
          </div>
        </div>
        {!isInline && (
          <button
            onClick={() => {
              setIsOpen(false);
              onClose?.();
            }}
            className="rounded-lg p-2 text-slate-500 transition-all hover:bg-black/[0.04] hover:text-slate-900"
          >
            <X size={20} />
          </button>
        )}
      </div>

      <div
        className={`flex-1 overflow-y-auto ${isInline ? "px-0 py-4" : "p-6"} space-y-6 scrollbar-hide`}
      >
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`flex max-w-[85%] gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}
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
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--accent)]"></span>
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--accent)] [animation-delay:0.2s]"></span>
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--accent)] [animation-delay:0.4s]"></span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

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
            placeholder="Frage nach Markt, Aktie, ETF oder Risiko..."
            className="w-full rounded-xl border border-black/8 bg-white py-3.5 pl-4 pr-12 text-sm text-slate-900 placeholder:text-slate-400 transition-all focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/20"
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
            Broker Freund Desk analysiert Live-Daten. Keine direkte Anlageberatung.
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
        className="group fixed bottom-24 left-4 right-4 z-40 flex h-[4.4rem] items-center justify-between rounded-[1.6rem] border border-white/65 bg-[linear-gradient(180deg,rgba(15,118,110,0.98),rgba(14,92,87,0.96))] px-4 text-white shadow-[0_24px_54px_rgba(15,118,110,0.26)] transition-all hover:scale-[1.01] hover:shadow-[0_28px_64px_rgba(15,118,110,0.3)] active:scale-[0.99] md:bottom-5 md:left-auto md:right-5 md:h-16 md:w-16 md:justify-center md:rounded-[1.45rem] md:px-0 sm:bottom-28 sm:left-6 sm:right-6 md:sm:right-8 md:sm:left-auto"
        aria-label="Open Broker Freund Desk"
      >
        <div className="absolute inset-0 rounded-[1.45rem] bg-white/8 opacity-0 transition-opacity group-hover:opacity-100"></div>
        <div className="absolute -top-2 right-3 rounded-full border border-white/15 bg-[#0b1216]/70 px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.16em] text-white/80 shadow-[0_10px_24px_rgba(15,23,42,0.16)] md:right-0">
          Live
        </div>
        <div className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-[1rem] border border-white/16 bg-white/14">
          <Bot size={22} />
        </div>
        <div className="relative min-w-0 flex-1 px-3 text-left md:hidden">
          <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-white/70">
            Broker Freund
          </div>
          <div className="truncate text-sm font-bold text-white">
            Open Desk
          </div>
          <div className="truncate text-[11px] leading-4 text-white/72">
            Signals, news, macro and crowd
          </div>
        </div>
        <div className="relative hidden rounded-full border border-white/14 bg-white/10 px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-white/80 md:block">
          Desk
        </div>
        <div className="pointer-events-none absolute bottom-0 right-[calc(100%+12px)] hidden w-[15.5rem] rounded-[1.3rem] border border-white/18 bg-[linear-gradient(180deg,rgba(11,18,22,0.95),rgba(15,118,110,0.92))] px-4 py-3 text-left text-white opacity-0 shadow-[0_24px_54px_rgba(15,23,42,0.24)] transition-all duration-200 group-hover:translate-x-0 group-hover:opacity-100 lg:block lg:translate-x-2">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-white/65">
              Broker Freund
            </div>
            <span className="rounded-full bg-white/12 px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.14em] text-white/80">
              Desk
            </span>
          </div>
          <div className="mt-1 text-sm font-bold text-white">Open Desk</div>
          <div className="mt-1 text-[11px] leading-5 text-white/72">
            Signals, news, macro and crowd context without covering the workspace.
          </div>
        </div>
      </button>

      {isOpen && chatContent}
    </>
  );
}
