import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, api, askStream, type Chat, type Message } from "../api/client";
import MessageBubble from "../components/MessageBubble";
import Sidebar from "../components/Sidebar";
import { useAuth } from "../context/AuthContext";

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
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [error, setError] = useState("");

  const abortRef = useRef<AbortController | null>(null);
  // Id of a chat we just created, so the load effect does not wipe the live stream
  const skipLoadRef = useRef<number | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

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

  return (
    <div className="flex h-screen bg-brand-sky">
      <Sidebar
        chats={chats}
        activeChatId={chatId}
        user={user}
        onNewChat={() => navigate("/chat")}
        onLogout={handleLogout}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto px-4 py-6 md:px-10">
          <div className="mx-auto flex max-w-3xl flex-col gap-4">
            {messages.length === 0 && !streaming && (
              <div className="mt-16 text-center">
                <h1 className="text-3xl font-bold text-brand-navy">
                  Talk to our Financial Bot
                </h1>
                <p className="mt-2">
                  Ask about the NABARD annual reports, FY2021 to FY2024.
                </p>
                <div className="mt-6 flex flex-col items-center gap-2">
                  {EXAMPLE_QUESTIONS.map((q) => (
                    <button
                      key={q}
                      onClick={() => send(q)}
                      className="rounded border border-brand-blue/40 bg-white px-4 py-2 text-sm text-brand-navy transition hover:border-brand-maroon hover:text-brand-maroon"
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
              <p className="rounded bg-red-50 px-3 py-2 text-sm text-brand-maroon">{error}</p>
            )}

            <div ref={bottomRef} />
          </div>
        </div>

        <div className="border-t border-gray-200 bg-white p-4">
          <div className="mx-auto flex max-w-3xl gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              maxLength={QUESTION_MAX_LENGTH}
              rows={2}
              placeholder="Ask a question about the reports..."
              className="flex-1 resize-none rounded border border-gray-300 px-3 py-2 outline-none focus:border-brand-navy"
            />
            <button
              onClick={() => send(input)}
              disabled={streaming || !input.trim()}
              className="self-end rounded bg-brand-maroon px-5 py-2.5 text-white transition hover:bg-brand-maroon-dark disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}