"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { getMe, logout, type AuthState } from "@/lib/api";

export function AuthGate({
  children,
  requireAuth = true,
}: {
  children: React.ReactNode;
  requireAuth?: boolean;
}) {
  const router = useRouter();
  const path = usePathname();
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    getMe()
      .then((state) => {
        if (active) setAuth(state);
      })
      .catch(() => {
        if (active && requireAuth)
          router.replace(`/login?next=${encodeURIComponent(path)}`);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [path, requireAuth, router]);
  if (loading && requireAuth)
    return (
      <main className="grid min-h-screen place-items-center bg-slate-50 text-sm font-medium text-slate-600">
        <span className="rounded-full border border-slate-200 bg-white px-4 py-2 shadow-sm">
          Loading your workspace…
        </span>
      </main>
    );
  if (requireAuth && !auth) return null;
  if (!auth) return <>{children}</>;
  const links = [
    ["/dashboard", "Dashboard"],
    ["/dashboard/analyzer", "Analyze Resume"],
    ["/dashboard/history", "History"],
  ] as const;
  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <Link
            href="/dashboard"
            className="flex items-center gap-2 font-bold tracking-tight text-slate-900"
          >
            <span className="grid h-8 w-8 place-items-center rounded-xl bg-indigo-600 text-sm text-white">
              R
            </span>
            Resume Analyzer
          </Link>
          <nav className="flex flex-wrap items-center gap-1 text-sm font-medium">
            {links.map(([href, label]) => (
              <Link
                key={href}
                href={href}
                className={`rounded-lg px-2.5 py-2 sm:px-3 ${path === href ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-100"}`}
              >
                {label}
              </Link>
            ))}
            <span className="hidden border-l border-slate-200 px-3 text-xs text-slate-500 lg:inline">
              <span className="block max-w-36 truncate">{auth.user.email}</span>
              <span className="font-semibold text-emerald-700">
                Unlimited analyses
              </span>
            </span>
            <button
              onClick={() => logout().finally(() => router.replace("/login"))}
              className="ml-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-700 hover:bg-slate-50"
            >
              Logout
            </button>
          </nav>
        </div>
      </header>
      {children}
    </main>
  );
}
