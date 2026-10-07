import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { ApiError } from "../api/client";
import { useAuth } from "../context/AuthContext";

const PASSWORD_MIN_LENGTH = 8;

export default function AuthPage({ mode }: { mode: "login" | "signup" }) {
  const { user, loading, login, signup } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const isSignup = mode === "signup";

  if (!loading && user) return <Navigate to="/chat" replace />;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");

    if (isSignup && password.length < PASSWORD_MIN_LENGTH) {
      setError(`Password must be at least ${PASSWORD_MIN_LENGTH} characters.`);
      return;
    }

    setSubmitting(true);

    try {
      if (isSignup) {
        await signup(email, password);
      } else {
        await login(email, password);
      }

      navigate("/chat", { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Something went wrong. Try again."
      );
    } finally {
      setSubmitting(false);
    }
  }

  const inputClass =
    "mt-1.5 w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2.5 font-normal text-brand-navy outline-none transition focus:border-brand-navy focus:ring-2 focus:ring-brand-navy/10";

  return (
    <div className="flex min-h-screen flex-col">
      {/* Header */}
      <header className="flex h-[76px] items-center border-b border-black/5 bg-white px-6 md:px-16">
        <Link to="/">
          <img src="/logo.png" alt="Veracitiz" className="h-11" />
        </Link>
      </header>

      {/* Main */}
      <main className="grid flex-1 lg:grid-cols-2">
        {/* Left text section */}
        <aside className="hidden items-center bg-brand-cream px-12 lg:flex xl:px-20">
          <div className="max-w-lg">
            <h2 className="text-4xl font-bold leading-snug text-brand-navy xl:text-5xl">
              Answers from the NABARD reports, with the page to prove it.
            </h2>

            <p className="mt-6 max-w-md text-base leading-relaxed text-brand-text">
              Ask questions about the annual reports and get answers backed by
              the exact report page, tables and charts.
            </p>
          </div>
        </aside>

        {/* Right auth section */}
        <div className="flex items-center justify-center bg-brand-sky px-4 py-10">
          <form
            onSubmit={handleSubmit}
            className="w-full max-w-md rounded-xl bg-white p-8 shadow-lg shadow-brand-navy/5"
          >
            <h1 className="text-3xl font-bold text-brand-navy">
              {isSignup ? "Create your account" : "Sign in"}
            </h1>

            <p className="mt-1 text-sm">
              {isSignup
                ? "Sign up to ask questions and keep your chat history."
                : "Welcome back. Sign in to continue your chats."}
            </p>

            {/* Email */}
            <label className="mt-6 block text-sm font-semibold text-brand-navy">
              Email

              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                className={inputClass}
              />
            </label>

            {/* Password */}
            <label className="mt-4 block text-sm font-semibold text-brand-navy">
              Password

              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={isSignup ? "new-password" : "current-password"}
                  className={`${inputClass} pr-11`}
                />

                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={
                    showPassword ? "Hide password" : "Show password"
                  }
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-brand-navy"
                >
                  {showPassword ? (
                    <EyeOff size={18} />
                  ) : (
                    <Eye size={18} />
                  )}
                </button>
              </div>
            </label>

            {/* Signup password requirement */}
            {isSignup && (
              <p className="mt-1.5 text-xs">
                Use at least {PASSWORD_MIN_LENGTH} characters.
              </p>
            )}

            {/* Error */}
            {error && (
              <p
                role="alert"
                className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-brand-maroon"
              >
                {error}
              </p>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={submitting}
              className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg bg-brand-maroon py-2.5 font-medium text-white transition hover:bg-brand-maroon-dark disabled:opacity-60"
            >
              {submitting && (
                <Loader2 size={16} className="animate-spin" />
              )}

              {submitting
                ? "Please wait"
                : isSignup
                  ? "Sign up"
                  : "Sign in"}
            </button>

            {/* Switch between login/signup */}
            <p className="mt-5 text-center text-sm">
              {isSignup ? "Already have an account? " : "New here? "}

              <Link
                to={isSignup ? "/login" : "/signup"}
                className="font-medium text-brand-maroon hover:underline"
              >
                {isSignup ? "Sign in" : "Sign up"}
              </Link>
            </p>
          </form>
        </div>
      </main>
    </div>
  );
}