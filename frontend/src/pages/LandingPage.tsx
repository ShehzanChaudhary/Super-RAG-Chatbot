import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, BarChart3, FileSearch, MessagesSquare, Search, TrendingUp } from "lucide-react";
import { useAuth } from "../context/AuthContext";

export const PENDING_QUESTION_KEY = "pending_question";

const FEATURES = [
  {
    icon: FileSearch,
    title: "Exact source pages",
    text: "Every answer comes with the report and page it was taken from. Click a source to open that page.",
  },
  {
    icon: BarChart3,
    title: "Tables and charts",
    text: "Ask for a table or compare FY2022, FY2023 and FY2024 and get the figures laid out with charts.",
  },
  {
    icon: MessagesSquare,
    title: "Follow-up questions",
    text: "Ask \"own funds 2025\" and then just \"ok 2026\". The assistant keeps track of what you meant.",
  },
  {
    icon: TrendingUp,
    title: "Trends and projections",
    text: "Ask what the next years may look like and get an analysis based on the past figures.",
  },
];

export default function LandingPage() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (q) sessionStorage.setItem(PENDING_QUESTION_KEY, q);
    navigate(user ? "/chat" : "/login");
  }

  return (
    <div className="flex min-h-screen flex-col bg-white">
      <header className="sticky top-0 z-20 flex h-[76px] items-center justify-between border-b border-black/5 bg-white/95 px-6 backdrop-blur md:px-16">
        <Link to="/">
          <img src="/logo.png" alt="Veracitiz" className="h-11" />
        </Link>

        {!loading && (
          <nav className="flex items-center gap-2">
            {user ? (
              <Link
                to="/chat"
                className="rounded-full bg-brand-maroon px-5 py-2 text-sm font-medium text-white transition hover:bg-brand-maroon-dark"
              >
                Open chat
              </Link>
            ) : (
              <>
                <Link
                  to="/login"
                  className="rounded-full px-4 py-2 text-sm font-medium text-brand-navy transition hover:text-brand-maroon"
                >
                  Sign in
                </Link>
                <Link
                  to="/signup"
                  className="rounded-full bg-brand-maroon px-5 py-2 text-sm font-medium text-white transition hover:bg-brand-maroon-dark"
                >
                  Sign up
                </Link>
              </>
            )}
          </nav>
        )}
      </header>

      <section className="overflow-hidden bg-brand-cream">
        <div className="mx-atuo grid items-end gap-0 pl-6 md:pl-16 lg:grid-cols-[1.05fr_1fr]">
          <div className="self-center py-14 pr-6 lg:py-24">
            <h1 className="text-4xl font-bold leading-tight tracking-tight text-brand-navy md:text-5xl">
              Conversational AI Assistant for Local Knowledge Base of Veracitiz
            </h1>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-brand-text">
              Ask questions about the NABARD annual reports (FY2021 to FY2024) and get
              answers with the exact source page, tables and charts.
            </p>

            <form
              onSubmit={handleSubmit}
              className="mt-8 flex max-w-xl items-center gap-2 rounded-full border-2 border-brand-navy/70 bg-white py-1.5 pl-5 pr-1.5 shadow-sm focus-within:border-brand-blue"
            >
              <Search size={18} className="shrink-0 text-brand-navy/60" aria-hidden />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Talk to our assistant..."
                aria-label="Talk to our assistant"
                className="min-w-0 flex-1 bg-transparent py-2 text-sm text-brand-navy outline-none placeholder:text-gray-400"
              />
              <button
                type="submit"
                aria-label="Start chatting"
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-maroon text-white transition hover:bg-brand-maroon-dark"
              >
                <ArrowRight size={18} />
              </button>
            </form>
          </div>

          <div className="relative self-end justify-self-end">
            <img
              src="/robot.png"
              alt="Veracitiz assistant robot beside a shelf of reports"
              className="block w-full max-w-[620px] lg:max-w-none"
            />
          </div>
        </div>
      </section>

      <section id="about" className="mx-auto w-full max-w-6xl px-6 py-20 md:px-16">
        <h2 className="text-3xl font-bold text-brand-navy md:text-4xl">About the tool</h2>
        <div className="mt-5 max-w-3xl space-y-4 leading-relaxed">
          <p>
            Veracitiz builds AI applications that help the employees and stakeholders of an
            organization find answers to their queries from locally available documents. The
            assistant works on the NABARD annual reports, so nothing outside those reports
            is used to answer your question.
          </p>
          <p>
            Many queries need several large documents to be explored, and doing that by hand
            takes a lot of time. Along with the answer, the assistant points you to the exact
            report page it used, so you can verify every number yourself.
          </p>
        </div>

        <div className="mt-12 grid gap-x-10 gap-y-8 sm:grid-cols-2">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <div key={title} className="flex gap-4">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-brand-sky text-brand-navy">
                <Icon size={22} aria-hidden />
              </div>
              <div>
                <h3 className="font-semibold text-brand-navy">{title}</h3>
                <p className="mt-1 text-sm leading-relaxed">{text}</p>
              </div>
            </div>
          ))}
        </div>

        <Link
          to={user ? "/chat" : "/signup"}
          className="mt-12 inline-flex items-center gap-2 rounded-full bg-brand-navy px-6 py-3 text-sm font-medium text-white transition hover:bg-brand-navy/90"
        >
          {user ? "Open chat" : "Get started"} <ArrowRight size={16} />
        </Link>
      </section>

      <footer className="mt-auto bg-brand-navy py-6 text-center text-sm text-white/80">
        © 2026 Veracitiz Solutions Pvt Ltd
      </footer>
    </div>
  );
}