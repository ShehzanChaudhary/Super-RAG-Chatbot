import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowUp, Bot, Menu, Square } from "lucide-react";
import { ApiError, api, askStream, type Chat, type Message } from "../api/client";
import MessageBubble from "../components/MessageBubble";
import Sidebar from "../components/Sidebar";
import { useAuth } from "../context/AuthContext";
import { PENDING_QUESTION_KEY } from "./LandingPage";

const QUESTION_MAX_LENGTH = 2000;

const EXAMPLE_QUESTIONS = [
  "What is the total of sources of funds in FY2024?",
  "Show the sources of funds table for FY2023",
  "What was CPI inflation in March in FY2023?",
];

type LocalMessage = Pick<Message, "id" | "role" | "content" | "citations"> & {
  verified?: boolean;
};

export default function ChatPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const params = useParams();
  const chatId = params.chatId ? Number(params.chatId) : null;

  const [chats, setChats] = useState<Chat[]>([]);
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  // A question typed on the landing page is waiting in the input box
  const [input, setInput] = useState(() => sessionStorage.getItem(PENDING_QUESTION_KEY) ?? "");
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [error, setError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  // Id of a chat we just created, so the load effect does not wipe the live stream
  const skipLoadRef = useRef<number | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const refreshChats = useCallback(async () => {
    try {
      setChats(await api.listChats());
    } catch {
      // the sidebar is not critical, keep the old list
    }
  }, []);

  useEffect(() => {
    refreshChats();
  }, [refreshChats]);

  useEffect(() => {
    sessionStorage.removeItem(PENDING_QUESTION_KEY);
  }, []);

  // Load the chat history whenever the chat in the URL changes
  useEffect(() => {
    if (chatId !== null && skipLoadRef.current === chatId) {
      skipLoadRef.current = null;
      return;
    }

    abortRef.current?.abort();
    setStreaming(false);
    setStreamText("");
    setError("");

    if (chatId === null || Number.isNaN(chatId)) {
      setMessages([]);
      return;
    }

    let cancelled = false;
    api
      .getChat(chatId)
      .then((detail) => {
        if (!cancelled) setMessages(detail.messages);
      })
      .catch((err) => {
        if (!cancelled && err instanceof ApiError && err.status === 404) {
          navigate("/chat", { replace: true });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [chatId, navigate]);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "auto" });
  }, [messages, streamText]);

  // Grow the input box with the text, up to a limit
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || streaming) return;

    setInput("");
    setError("");
    setStreaming(true);
    setStreamText("");
    setMessages((prev) => [
      ...prev,
      { id: -Date.now(), role: "user", content: question, citations: null },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      let activeId = chatId;
      if (activeId === null || Number.isNaN(activeId)) {
        const chat = await api.createChat();
        activeId = chat.id;
        skipLoadRef.current = chat.id;
        navigate(`/chat/${chat.id}`, { replace: true });
      }

      let full = "";
      for await (const event of askStream(activeId, question, controller.signal)) {
        if (event.type === "token") {
          full += event.text;
          setStreamText(full);
        } else if (event.type === "error") {
          setError(event.message);
          break;
        } else {
          setMessages((prev) => [
            ...prev,
            {
              id: event.data.message_id ?? -Date.now() - 1,
              role: "assistant",
              content: full.trim(),
              citations: event.data.citations,
              verified: event.data.verified,
            },
          ]);
          refreshChats();
        }
      }
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      if (abortRef.current === controller) {
        setStreaming(false);
        setStreamText("");
      }
    }
  }

  function stop() {
    abortRef.current?.abort();
    setStreaming(false);
    setStreamText("");
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  }

  function handleLogout() {
    logout();
    navigate("/");
  }

  if (!user) return null;

  const activeTitle = chats.find((c) => c.id === chatId)?.title;
  const isEmpty = messages.length === 0 && !streaming;

  return (
    <div className="flex h-screen bg-brand-sky">
      <Sidebar
        chats={chats}
        activeChatId={chatId}
        user={user}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={() => navigate("/chat")}
        onLogout={handleLogout}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-black/5 bg-white px-4">
          <button
            onClick={() => setSidebarOpen(true)}
            aria-label="Open chat list"
            className="rounded-lg p-2 text-brand-navy hover:bg-black/5 md:hidden"
          >
            <Menu size={20} />
          </button>
          <p className="truncate text-sm font-semibold text-brand-navy">
            {activeTitle ?? "New chat"}
          </p>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-6 md:px-10">
          <div className="mx-auto flex max-w-3xl flex-col gap-5">
            {isEmpty && (
              <div className="mt-12 flex flex-col items-center text-center">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-maroon text-white">
                  <Bot size={28} aria-hidden />
                </div>
                <h1 className="mt-5 text-3xl font-bold text-brand-navy">
                  Talk to our Financial Bot
                </h1>
                <p className="mt-2">Ask about the NABARD annual reports, FY2021 to FY2024.</p>
                <div className="mt-6 flex flex-col items-stretch gap-2 sm:items-center">
                  {EXAMPLE_QUESTIONS.map((q) => (
                    <button
                      key={q}
                      onClick={() => send(q)}
                      className="rounded-full border border-brand-blue/40 bg-white px-5 py-2 text-sm text-brand-navy transition hover:border-brand-maroon hover:text-brand-maroon"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m) => (
              <MessageBubble
                key={m.id}
                role={m.role}
                content={m.content}
                citations={m.citations}
                verified={m.verified ?? true}
              />
            ))}

            {streaming && <MessageBubble role="assistant" content={streamText} streaming />}

            {error && (
              <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-brand-maroon">
                {error}
              </p>
            )}

            <div ref={bottomRef} />
          </div>
        </div>

        <div className="shrink-0 px-4 pb-5 pt-2 md:px-10">
          <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-3xl border border-gray-300 bg-white p-2 pl-5 shadow-sm focus-within:border-brand-navy">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              maxLength={QUESTION_MAX_LENGTH}
              rows={1}
              autoFocus
              aria-label="Your question"
              placeholder="Ask a question about the reports..."
              className="max-h-40 flex-1 resize-none bg-transparent py-2 text-gray-800 outline-none placeholder:text-gray-400"
            />
            {streaming ? (
              <button
                onClick={stop}
                aria-label="Stop answering"
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-navy text-white transition hover:bg-brand-navy/90"
              >
                <Square size={14} fill="currentColor" />
              </button>
            ) : (
              <button
                onClick={() => send(input)}
                disabled={!input.trim()}
                aria-label="Send"
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-maroon text-white transition hover:bg-brand-maroon-dark disabled:opacity-40"
              >
                <ArrowUp size={18} />
              </button>
            )}
          </div>
          <p className="mx-auto mt-2 max-w-3xl text-center text-xs text-gray-400">
            Answers come from the NABARD reports. Check the source page for important figures.
          </p>
        </div>
      </main>
    </div>
  );
}