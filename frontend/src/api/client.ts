export interface Citation {
  doc_name: string;
  pdf_page: number;
  report_year: string;
  chunk_type: string;
  url: string;
}

export interface User {
  id: number;
  email: string;
  created_at: string;
}

export interface Chat {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
  citations: Citation[] | null;
  created_at: string;
}

export interface ChatDetail {
  chat: Chat;
  messages: Message[];
}

export interface DoneData {
  chat_id: number;
  title: string;
  message_id: number | null;
  found: boolean;
  verified: boolean;
  citations: Citation[];
}

export type StreamEvent =
  | { type: "token"; text: string }
  | { type: "done"; data: DoneData }
  | { type: "error"; message: string };

const TOKEN_KEY = "access_token";

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    // 422 validation errors come as a list
    if (Array.isArray(body.detail) && body.detail.length > 0) {
      return body.detail[0].msg ?? "Invalid request";
    }
  } catch {
    // body was not JSON
  }
  return `Request failed (${res.status})`;
}

function authHeaders(): Headers {
  const headers = new Headers({ "Content-Type": "application/json" });
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

function handleUnauthorized(path: string, status: number) {
  // A bad login is also a 401, but that is not an expired session
  if (status === 401 && !path.startsWith("/api/auth/login") && tokenStore.get()) {
    tokenStore.clear();
    window.dispatchEvent(new Event("auth:logout"));
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, { ...options, headers: authHeaders() });
  if (!res.ok) {
    handleUnauthorized(path, res.status);
    throw new ApiError(res.status, await readError(res));
  }
  return res.json() as Promise<T>;
}

export const api = {
  signup: (email: string, password: string) =>
    request<User>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  async login(email: string, password: string) {
    const data = await request<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    tokenStore.set(data.access_token);
  },

  logout: () => tokenStore.clear(),

  me: () => request<User>("/api/auth/me"),

  listChats: () => request<Chat[]>("/api/chats"),

  createChat: () => request<Chat>("/api/chats", { method: "POST" }),

  getChat: (chatId: number) => request<ChatDetail>(`/api/chats/${chatId}`),
};

function parseEvent(block: string): StreamEvent | null {
  let name = "";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!name || !data) return null;

  const payload = JSON.parse(data);
  if (name === "token") return { type: "token", text: payload.text };
  if (name === "done") return { type: "done", data: payload as DoneData };
  if (name === "error") return { type: "error", message: payload.message };
  return null;
}

/** Ask a question and receive the answer piece by piece. */
export async function* askStream(
  chatId: number,
  question: string,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const path = `/api/chats/${chatId}/ask`;
  const res = await fetch(path, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ question }),
    signal,
  });

  if (!res.ok || !res.body) {
    handleUnauthorized(path, res.status);
    throw new ApiError(res.status, await readError(res));
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    // Events are separated by a blank line
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      const event = parseEvent(block);
      if (!event) continue;
      if (event.type !== "token") finished = true;
      yield event;
    }
  }

  // The stream closed without a done or error event
  if (!finished) {
    yield { type: "error", message: "Jawab poora nahi aaya. Dobara try karo." };
  }
}