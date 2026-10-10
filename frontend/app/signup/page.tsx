"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { PasswordField } from "@/components/password-field";
import { getMe, signup, GOOGLE_AUTH_URL } from "@/lib/api";

const emailPattern = /^\S+@\S+\.\S+$/;

function subscribeToLocation(callback: () => void) {
  window.addEventListener("popstate", callback);
  return () => window.removeEventListener("popstate", callback);
}

function oauthErrorCode() {
  return new URLSearchParams(window.location.search).get("oauth_error");
}

function oauthErrorMessage(code: string | null) {
  if (code === "google_token_exchange_failed")
    return "Google rejected the sign-up callback. Verify the exact Authorized redirect URI in Google Cloud Console.";
  if (
    code === "google_identity_fetch_failed" ||
    code === "google_identity_validation_failed"
  )
    return "Google could not verify the selected account. Please choose a verified Google account and try again.";
  if (
    code === "google_account_setup_failed" ||
    code === "google_account_conflict"
  )
    return "Your Google identity was verified, but the account could not be set up. Please try again.";
  if (code) return "Google sign-up could not be completed. Please try again.";
  return "";
}

export default function Signup() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [oauthLoading, setOauthLoading] = useState(false);
  const confirmError = useMemo(
    () => (confirm && password !== confirm ? "Passwords do not match." : ""),
    [confirm, password],
  );
  const oauthError = useSyncExternalStore(
    subscribeToLocation,
    oauthErrorCode,
    () => null,
  );
  const visibleError = error || oauthErrorMessage(oauthError);

  useEffect(() => {
    getMe()
      .then(() => router.replace("/dashboard/analyzer"))
      .catch(() => undefined);
  }, [router]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (loading) return;
    if (
      !name.trim() ||
      !emailPattern.test(email) ||
      password.length < 8 ||
      password !== confirm
    ) {
      setError(
        "Enter your name, a valid email, and matching passwords of at least 8 characters.",
      );
      return;
    }
    setError("");
    setLoading(true);
    try {
      await signup(name.trim(), email.trim(), password);
      router.replace("/dashboard/analyzer");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Unable to create your account. Please try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-gradient-to-br from-slate-50 via-indigo-50 to-slate-100 p-4">
      <form
        onSubmit={submit}
        className="w-full max-w-md space-y-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-xl shadow-slate-200/50 sm:p-8"
      >
        <Link href="/" className="text-sm font-semibold text-indigo-700">
          ← AI Resume Analyzer
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-950">
            Create your account
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Save your analyses and keep improving your applications.
          </p>
        </div>
        <div className="space-y-2">
          <label htmlFor="name" className="text-sm font-medium text-slate-700">
            Name
          </label>
          <input
            id="name"
            autoComplete="name"
            maxLength={120}
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="w-full rounded-xl border border-slate-300 px-3 py-3 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
          />
        </div>
        <div className="space-y-2">
          <label htmlFor="email" className="text-sm font-medium text-slate-700">
            Email
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            inputMode="email"
            maxLength={254}
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="w-full rounded-xl border border-slate-300 px-3 py-3 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
          />
        </div>
        <PasswordField
          id="password"
          label="Password"
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
          showStrength
        />
        <PasswordField
          id="confirm-password"
          label="Confirm password"
          value={confirm}
          onChange={setConfirm}
          autoComplete="new-password"
          error={confirmError}
        />
        {visibleError && (
          <p
            role="alert"
            className="rounded-lg bg-rose-50 p-3 text-sm text-rose-700"
          >
            {visibleError}
          </p>
        )}
        <button
          disabled={loading || oauthLoading || Boolean(confirmError)}
          className="w-full rounded-xl bg-indigo-600 p-3 font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? "Creating account…" : "Create account"}
        </button>
        <div className="flex items-center gap-3 text-xs text-slate-400">
          <span className="h-px flex-1 bg-slate-200" />
          or
          <span className="h-px flex-1 bg-slate-200" />
        </div>
        <a
          href={GOOGLE_AUTH_URL}
          onClick={() => {
            setError("");
            setOauthLoading(true);
          }}
          aria-busy={oauthLoading}
          className="block w-full rounded-xl border border-slate-300 p-3 text-center text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
        >
          {oauthLoading ? "Redirecting to Google…" : "Continue with Google"}
        </a>
        <p className="text-center text-sm text-slate-600">
          Already have an account?{" "}
          <Link href="/login" className="font-semibold text-indigo-700">
            Sign in
          </Link>
        </p>
      </form>
    </main>
  );
}
