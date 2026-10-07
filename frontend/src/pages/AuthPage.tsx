import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../context/AuthContext";

const PASSWORD_MIN_LENGTH = 8;

export default function AuthPage({ mode }: { mode: "login" | "signup" }) {
  const { user, loading, login, signup } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const isSignup = mode === "signup";

  // Already logged in: go straight to the chat
  if (!loading && user) return <Navigate to="/chat" replace />;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");

    if (isSignup && password.length < PASSWORD_MIN_LENGTH) {
      setError(`Password must be at least ${PASSWORD_MIN_LENGTH} characters`);
      return;
    }

    setSubmitting(true);
    try {
      if (isSignup) await signup(email, password);
      else await login(email, password);
      navigate("/chat", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-brand-sky">
      <header className="flex h-[86px] items-center bg-white px-6 shadow-sm md:px-20">
        <Link to="/">
          <img src="/logo.png" alt="Veracitiz" className="h-12" />
        </Link>
      </header>

      <main className="flex flex-1 items-center justify-center px-4 py-10">
        <form
          onSubmit={handleSubmit}
          className="w-full max-w-md rounded bg-white p-8 shadow-lg"
        >
          <h1 className="text-3xl font-bold text-brand-navy">
            {isSignup ? "Create your account" : "Sign in"}
          </h1>

          <label className="mt-6 block text-sm font-semibold text-brand-navy">
            Email
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2 font-normal outline-none focus:border-brand-navy"
            />
          </label>

          <label className="mt-4 block text-sm font-semibold text-brand-navy">
            Password
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={isSignup ? "new-password" : "current-password"}
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2 font-normal outline-none focus:border-brand-navy"
            />
          </label>

          {isSignup && (
            <p className="mt-1 text-xs">At least {PASSWORD_MIN_LENGTH} characters.</p>
          )}

          {error && (
            <p className="mt-4 rounded bg-red-50 px-3 py-2 text-sm text-brand-maroon">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="mt-6 w-full rounded bg-brand-maroon py-2.5 text-white transition hover:bg-brand-maroon-dark disabled:opacity-60"
          >
            {submitting ? "Please wait..." : isSignup ? "Sign up" : "Sign in"}
          </button>

          <p className="mt-4 text-center text-sm">
            {isSignup ? "Already have an account? " : "New here? "}
            <Link
              to={isSignup ? "/login" : "/signup"}
              className="text-brand-maroon hover:underline"
            >
              {isSignup ? "Sign in" : "Sign up"}
            </Link>
          </p>
        </form>
      </main>
    </div>
  );
}