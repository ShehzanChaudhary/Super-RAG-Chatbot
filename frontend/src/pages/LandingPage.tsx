import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function LandingPage() {
  const { user, loading } = useAuth();

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-[86px] items-center justify-between bg-white px-6 shadow-sm md:px-20">
        <Link to="/">
          <img src="/logo.png" alt="Veracitiz" className="h-12" />
        </Link>

        {!loading && (
          <nav className="flex items-center gap-3">
            {user ? (
              <Link
                to="/chat"
                className="rounded border border-brand-maroon px-5 py-2 text-brand-maroon transition hover:bg-brand-maroon hover:text-white"
              >
                Open chat
              </Link>
            ) : (
              <>
                <Link
                  to="/login"
                  className="px-4 py-2 uppercase text-brand-navy transition hover:text-brand-maroon"
                >
                  Sign in
                </Link>
                <Link
                  to="/signup"
                  className="rounded border border-brand-maroon px-5 py-2 text-brand-maroon transition hover:bg-brand-maroon hover:text-white"
                >
                  Sign up
                </Link>
              </>
            )}
          </nav>
        )}
      </header>

      <main className="flex flex-1 items-center bg-gradient-to-br from-brand-navy via-[#1d4a80] to-[#2d6aa8] px-6 py-16 md:px-40">
        <div className="max-w-xl rounded bg-white p-10 shadow-xl">
          <h1 className="text-4xl font-bold text-brand-navy">
            Talk to our Financial Bot
          </h1>
          <p className="mt-4 text-xl">
            Ask questions about the NABARD annual reports (FY2021 to FY2024) and
            get answers with the exact source page.
          </p>
          <Link
            to="/chat"
            className="mt-8 inline-block rounded bg-brand-maroon px-6 py-3 text-white transition hover:bg-brand-maroon-dark"
          >
            Talk to our Financial Bot
          </Link>
        </div>
      </main>

      <footer className="bg-brand-navy py-6 text-center text-sm text-white/80">
        © 2026 Veracitiz Solutions Pvt Ltd
      </footer>
    </div>
  );
}