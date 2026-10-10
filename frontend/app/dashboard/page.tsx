"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AuthGate } from "@/components/auth-gate";
import { getHistory, type History } from "@/lib/api";

export default function Dashboard() {
  const [history, setHistory] = useState<History | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    getHistory()
      .then(setHistory)
      .catch(() => setError("Unable to load your recent activity."));
  }, []);
  return (
    <AuthGate>
      <section className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
        <div className="overflow-hidden rounded-3xl border border-indigo-100 bg-gradient-to-br from-indigo-600 to-violet-600 p-6 text-white shadow-lg shadow-indigo-100 sm:p-9">
          <p className="text-sm font-semibold text-indigo-100">
            YOUR CAREER WORKSPACE
          </p>
          <h1 className="mt-2 max-w-2xl text-3xl font-bold tracking-tight sm:text-4xl">
            Make every application more intentional.
          </h1>
          <p className="mt-3 max-w-xl text-sm leading-6 text-indigo-100">
            Analyze your resume, compare it with target jobs, and use grounded
            guidance to decide what to improve.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              href="/dashboard/analyzer"
              className="rounded-xl bg-white px-5 py-3 text-sm font-semibold text-indigo-700 shadow-sm hover:bg-indigo-50"
            >
              Analyze Resume
            </Link>
            <Link
              href="/dashboard/history"
              className="rounded-xl border border-indigo-300/60 px-5 py-3 text-sm font-semibold text-white hover:bg-white/10"
            >
              View history
            </Link>
          </div>
        </div>
        <div className="mt-8 flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-100 text-emerald-700">
            ∞
          </span>
          <div>
            <p className="font-semibold">Unlimited analyses</p>
            <p className="text-sm text-slate-500">
              Your account can continue saving analyses and job matches.
            </p>
          </div>
        </div>
        {error ? (
          <div
            role="alert"
            className="mt-8 rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-800"
          >
            {error}
          </div>
        ) : (
          <>
            <div className="mt-8 grid gap-4 sm:grid-cols-2">
              <Metric label="Saved analyses" value={history?.analyses.length} />
              <Metric label="Job matches" value={history?.matches.length} />
            </div>
            <section className="mt-8">
              <div className="flex items-end justify-between gap-4">
                <div>
                  <h2 className="text-xl font-bold">Recent activity</h2>
                  <p className="mt-1 text-sm text-slate-500">
                    Your most recent saved work.
                  </p>
                </div>
                <Link
                  href="/dashboard/history"
                  className="text-sm font-semibold text-indigo-700"
                >
                  View all
                </Link>
              </div>
              {!history ? (
                <div className="mt-4 h-28 animate-pulse rounded-2xl border border-slate-200 bg-white" />
              ) : !history.analyses.length && !history.matches.length ? (
                <div className="mt-4 rounded-2xl border border-dashed border-slate-300 bg-white p-6">
                  <h3 className="font-semibold">
                    Start with your first resume
                  </h3>
                  <p className="mt-1 text-sm text-slate-600">
                    Upload a PDF or DOCX to receive your structured review and
                    ATS-style feedback.
                  </p>
                </div>
              ) : (
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  {history.analyses.slice(0, 2).map((item) => (
                    <article
                      key={item.id}
                      className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
                    >
                      <p className="text-xs font-semibold uppercase tracking-wide text-indigo-700">
                        Analysis
                      </p>
                      <p className="mt-1 truncate font-semibold">
                        {item.filename || "Resume analysis"}
                      </p>
                      <p className="mt-2 text-sm text-slate-500">
                        {new Date(item.created_at).toLocaleString()}
                      </p>
                    </article>
                  ))}
                  {history.matches.slice(0, 2).map((item) => (
                    <article
                      key={item.id}
                      className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
                    >
                      <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">
                        Job match
                      </p>
                      <p className="mt-1 line-clamp-2 text-sm font-medium">
                        {item.job_description || "Job description"}
                      </p>
                      <p className="mt-2 text-sm text-slate-500">
                        {typeof item.match_score === "number"
                          ? `${item.match_score}/100 · `
                          : ""}
                        {new Date(item.created_at).toLocaleString()}
                      </p>
                    </article>
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </section>
    </AuthGate>
  );
}
function Metric({
  label,
  value,
}: {
  label: string;
  value: number | undefined;
}) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <p className="mt-2 text-3xl font-bold">{value ?? "…"}</p>
    </article>
  );
}
