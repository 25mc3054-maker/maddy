"use client";

import { useEffect, useRef, useState } from "react";

type Message = {
  role: "user" | "assistant";
  content: string;
};

type SpeechResult = {
  transcript: string;
};

type SpeechEvent = {
  results: ArrayLike<ArrayLike<SpeechResult>>;
};

type Recognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: SpeechEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

type RecognitionConstructor = new () => Recognition;

declare global {
  interface Window {
    SpeechRecognition?: RecognitionConstructor;
    webkitSpeechRecognition?: RecognitionConstructor;
  }
}

const API_URL =
  process.env.NEXT_PUBLIC_MADDY_API_URL ??
  "http://127.0.0.1:8000";

export default function Home() {
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState("");
  const [loading, setLoading] = useState(false);
  const [listening, setListening] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(false);
  const [error, setError] = useState("");

  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "Hello! I'm MADDY, your personal AI assistant. Ask me a question, manage tasks, or use your microphone to talk to me.",
    },
  ]);

  const bottomRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<Recognition | null>(null);

  useEffect(() => {
    setSpeechSupported(
      Boolean(
        window.SpeechRecognition ||
          window.webkitSpeechRecognition
      )
    );

    let id = localStorage.getItem("maddy_conversation_id");

    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem("maddy_conversation_id", id);
    }

    setConversationId(id);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [messages, loading]);

  function speak(text: string) {
    if (!("speechSynthesis" in window)) {
      setError("Speech output is unavailable in this browser.");
      return;
    }

    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-IN";
    utterance.rate = 1;
    utterance.pitch = 1;

    window.speechSynthesis.speak(utterance);
  }

  function startListening() {
    setError("");

    const SpeechRecognition =
      window.SpeechRecognition ||
      window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setError(
        "Voice recognition is unsupported in this browser. Please type your message."
      );
      return;
    }

    const recognition = new SpeechRecognition();

    recognition.lang = "en-IN";
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript;

      if (transcript) {
        setInput(transcript);
      }

      setListening(false);
    };

    recognition.onerror = (event) => {
      setError(`Microphone error: ${event.error}`);
      setListening(false);
    };

    recognition.onend = () => setListening(false);

    recognitionRef.current = recognition;

    try {
      recognition.start();
      setListening(true);
    } catch {
      setError("Unable to start the microphone. Please try again.");
      setListening(false);
    }
  }

  async function sendMessage(messageOverride?: string) {
    const message = (messageOverride ?? input).trim();

    if (!message || loading || !conversationId) {
      return;
    }

    setError("");
    setInput("");

    setMessages((previous) => [
      ...previous,
      { role: "user", content: message },
    ]);

    setLoading(true);

    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message,
          conversation_id: conversationId,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail ??
            `Backend request failed: ${response.status}`
        );
      }

      const answer: string =
        data.answer ??
        data.reply ??
        "I couldn't generate a response.";

      setMessages((previous) => [
        ...previous,
        { role: "assistant", content: answer },
      ]);

      speak(answer);
    } catch (err) {
      const details =
        err instanceof Error
          ? err.message
          : "Unknown error";

      setError(
        `Could not connect to MADDY. Check that the backend is running at ${API_URL}. Details: ${details}`
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#09090b] text-white">
      <div className="mx-auto flex min-h-screen max-w-5xl flex-col px-4 py-6 sm:px-8">
        <header className="flex items-center justify-between border-b border-white/10 pb-5">
          <div>
            <h1 className="text-3xl font-bold tracking-[0.2em]">
              MADDY
            </h1>
            <p className="mt-1 text-sm text-zinc-400">
              Your personal AI assistant
            </p>
          </div>

          <div className="flex items-center gap-2 rounded-full border border-white/10 px-3 py-2 text-sm text-zinc-300">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            Ready to assist
          </div>
        </header>

        <section className="flex flex-1 flex-col py-8">
          <div className="mb-8 text-center">
            <div className="mx-auto mb-4 flex h-24 w-24 items-center justify-center rounded-full border border-white/15 bg-white/[0.04] shadow-[0_0_60px_rgba(255,255,255,0.05)]">
              <span className="text-4xl font-light">M</span>
            </div>

            <h2 className="text-xl font-medium">
              How can I help you today?
            </h2>

            <p className="mt-2 text-sm text-zinc-500">
              Ask a question, manage tasks, or speak naturally.
            </p>
          </div>

          <div className="flex-1 space-y-5">
            {messages.map((message, index) => (
              <div
                key={`${index}-${message.role}`}
                className={`flex ${
                  message.role === "user"
                    ? "justify-end"
                    : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-5 py-3 leading-7 ${
                    message.role === "user"
                      ? "bg-white text-black"
                      : "border border-white/10 bg-white/[0.04] text-zinc-200"
                  }`}
                >
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wider opacity-60">
                    {message.role === "user" ? "You" : "MADDY"}
                  </p>

                  {message.content}

                  {message.role === "assistant" && index > 0 && (
                    <button
                      type="button"
                      onClick={() => speak(message.content)}
                      className="mt-3 block text-xs text-zinc-400 hover:text-white"
                    >
                      ▶ Speak again
                    </button>
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <p className="animate-pulse text-sm text-zinc-400">
                MADDY is thinking...
              </p>
            )}

            <div ref={bottomRef} />
          </div>

          {error && (
            <div
              role="alert"
              className="my-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200"
            >
              {error}
            </div>
          )}

          <div className="mt-8 rounded-2xl border border-white/10 bg-white/[0.03] p-3">
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void sendMessage();
              }}
              className="flex items-center gap-3"
            >
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Talk to MADDY or type a message..."
                disabled={loading}
                className="min-w-0 flex-1 bg-transparent px-3 py-3 text-sm outline-none placeholder:text-zinc-600 disabled:opacity-50"
              />

              <button
                type="button"
                onClick={startListening}
                disabled={loading || listening || !speechSupported}
                title="Use microphone"
                className="rounded-xl border border-white/10 px-4 py-3 text-sm hover:bg-white/10 disabled:opacity-40"
              >
                {listening ? "Listening..." : "🎙️"}
              </button>

              <button
                type="submit"
                disabled={loading || !input.trim()}
                className="rounded-xl bg-white px-5 py-3 text-sm font-semibold text-black hover:bg-zinc-200 disabled:opacity-40"
              >
                Send
              </button>
            </form>

            <div className="flex items-center justify-between px-3 pb-1 pt-2 text-xs text-zinc-600">
              <span>
                {listening
                  ? "Listening for your voice..."
                  : speechSupported
                    ? "Voice and text enabled"
                    : "Text enabled; voice recognition unavailable"}
              </span>

              <button
                type="button"
                onClick={() => window.speechSynthesis?.cancel()}
                className="hover:text-zinc-300"
              >
                Stop speech
              </button>
            </div>
          </div>
        </section>

        <footer className="border-t border-white/10 pt-4 text-center text-xs text-zinc-600">
          MADDY • Always Ready to assist .
        </footer>
      </div>
    </main>
  );
}


