import { Link } from "react-router-dom";
import type { Chat, User } from "../api/client";

interface SidebarProps {
  chats: Chat[];
  activeChatId: number | null;
  user: User;
  onNewChat: () => void;
  onLogout: () => void;
}

export default function Sidebar({
  chats,
  activeChatId,
  user,
  onNewChat,
  onLogout,
}: SidebarProps) {
  return (
    <aside className="flex h-full w-72 shrink-0 flex-col bg-brand-navy text-white">
      <div className="p-4">
        <Link to="/" className="mb-4 block rounded bg-white p-2">
          <img src="/logo.png" alt="Veracitiz" className="mx-auto h-9" />
        </Link>
        <button
          onClick={onNewChat}
          className="w-full rounded bg-brand-maroon py-2 transition hover:bg-brand-maroon-dark"
        >
          + New chat
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-2">
        {chats.length === 0 && (
          <p className="px-3 py-2 text-sm text-white/60">No chats yet</p>
        )}
        {chats.map((chat) => (
          <Link
            key={chat.id}
            to={`/chat/${chat.id}`}
            title={chat.title}
            className={`mb-1 block truncate rounded px-3 py-2 text-sm transition ${
              chat.id === activeChatId ? "bg-white/20" : "hover:bg-white/10"
            }`}
          >
            {chat.title}
          </Link>
        ))}
      </nav>

      <div className="border-t border-white/20 p-4 text-sm">
        <p className="truncate text-white/70" title={user.email}>
          {user.email}
        </p>
        <button
          onClick={onLogout}
          className="mt-2 text-white underline-offset-2 hover:underline"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}