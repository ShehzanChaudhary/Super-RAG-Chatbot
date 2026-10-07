import { Link } from "react-router-dom";
import { LogOut, MessageSquare, Plus } from "lucide-react";
import type { Chat, User } from "../api/client";

interface SidebarProps {
  chats: Chat[];
  activeChatId: number | null;
  user: User;
  open: boolean;
  onClose: () => void;
  onNewChat: () => void;
  onLogout: () => void;
}

export default function Sidebar({
  chats,
  activeChatId,
  user,
  open,
  onClose,
  onNewChat,
  onLogout,
}: SidebarProps) {
  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/30 md:hidden"
          onClick={onClose}
          aria-hidden
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-72 shrink-0 flex-col border-r border-black/5 bg-panel transition-transform md:static md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="p-4">
          <Link to="/" className="mb-4 block rounded-lg bg-white p-2 shadow-sm">
            <img src="/logo.png" alt="Veracitiz" className="mx-auto h-9" />
          </Link>
          <button
            onClick={() => {
              onNewChat();
              onClose();
            }}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-brand-maroon py-2.5 text-sm font-medium text-white transition hover:bg-brand-maroon-dark"
          >
            <Plus size={16} /> New chat
          </button>
        </div>

        <p className="px-5 pb-1 text-xs font-semibold text-gray-500">Recent chats</p>
        <nav className="flex-1 overflow-y-auto px-2 pb-2">
          {chats.length === 0 && (
            <p className="px-3 py-2 text-sm text-gray-500">Your chats will show up here.</p>
          )}
          {chats.map((chat) => {
            const active = chat.id === activeChatId;
            return (
              <Link
                key={chat.id}
                to={`/chat/${chat.id}`}
                title={chat.title}
                onClick={onClose}
                className={`mb-0.5 flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition ${
                  active
                    ? "bg-white font-medium text-brand-navy shadow-sm"
                    : "text-brand-text hover:bg-black/5"
                }`}
              >
                <MessageSquare size={15} className="shrink-0 opacity-60" aria-hidden />
                <span className="truncate">{chat.title}</span>
              </Link>
            );
          })}
        </nav>

        <div className="flex items-center gap-3 border-t border-black/5 p-4">
          <div
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-navy text-sm font-semibold uppercase text-white"
            aria-hidden
          >
            {user.email.charAt(0)}
          </div>
          <p className="min-w-0 flex-1 truncate text-sm text-brand-navy" title={user.email}>
            {user.email}
          </p>
          <button
            onClick={onLogout}
            aria-label="Sign out"
            title="Sign out"
            className="rounded-lg p-2 text-gray-500 transition hover:bg-black/5 hover:text-brand-maroon"
          >
            <LogOut size={17} />
          </button>
        </div>
      </aside>
    </>
  );
}