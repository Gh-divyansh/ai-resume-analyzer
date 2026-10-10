"use client";

import { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";

import {
  analyzeResume,
  improveResumeBullet,
  getUsage,
  type History,
  type UsageState,
  matchResume,
  optimizeResume,
  optimizeResumeDocument,
  optimizedResumeDownloadUrl,
  type AnalyzeResumeResponse,
  type BulletImprovementResult,
  type BulletImprovementContext,
  type JobMatchResult,
  type OptimizationPriority,
  type ResumeOptimizationResult,
  type OptimizedResumeResult,
} from "@/lib/api";

type IconName = "arrow" | "check" | "document" | "info" | "sparkle" | "warning";

type BulletTarget =
  | {
      key: string;
      kind: "experience";
      bullet: string;
      experienceIndex: number;
      responsibilityIndex: number;
      context: BulletImprovementContext;
    }
  | {
      key: string;
      kind: "projects";
      bullet: string;
      projectIndex: number;
      context: BulletImprovementContext;
    };

type BulletReview = {
  target: BulletTarget;
  improvement: BulletImprovementResult;
};

function Icon({
  name,
  className = "",
}: {
  name: IconName;
  className?: string;
}) {
  const paths: Record<IconName, React.ReactNode> = {
    arrow: <path d="M12 4v12m0-12 4.5 4.5M12 4 7.5 8.5M5 20h14" />,
    check: <path d="m5 12 4.2 4.2L19 6.5" />,
    document: (
      <path d="M14.5 3H6.8A1.8 1.8 0 0 0 5 4.8v14.4A1.8 1.8 0 0 0 6.8 21h10.4a1.8 1.8 0 0 0 1.8-1.8V7.5L14.5 3ZM14 3v5h5M8 12h8M8 16h6" />
    ),
    info: (
      <>
        <circle cx="12" cy="12" r="8.5" />
        <path d="M12 11v5m0-8.5h.01" />
      </>
    ),
    sparkle: (
      <path d="m12 3 .9 4.1L17 8l-4.1.9L12 13l-.9-4.1L7 8l4.1-.9L12 3Zm6.2 10.7.5 2.3 2.3.5-2.3.5-.5 2.3-.5-2.3-2.3-.5 2.3-.5.5-2.3ZM5.8 13.4l.5 2.3 2.3.5-2.3.5-.5 2.3-.5-2.3-2.3-.5 2.3-.5.5-2.3Z" />
    ),
    warning: (
      <>
        <path d="M10.3 4.4 3.7 16a2 2 0 0 0 1.7 3h13.2a2 2 0 0 0 1.7-3L13.7 4.4a2 2 0 0 0-3.4 0Z" />
        <path d="M12 9v3.8m0 3h.01" />
      </>
    ),
  };

  return (
    <svg
      aria-hidden="true"
      className={`h-5 w-5 ${className}`}
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={1.8}
      viewBox="0 0 24 24"
    >
      {paths[name]}
    </svg>
  );
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return <p className="mt-4 text-sm leading-6 text-slate-500">{children}</p>;
}

function SectionCard({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6 ${className}`}
    >
      {children}
    </section>
  );
}

function scoreTone(score: number) {
  if (score >= 80)
    return {
      label: "Strong",
      ring: "stroke-emerald-500",
      text: "text-emerald-700",
      bg: "bg-emerald-50",
    };
  if (score >= 60)
    return {
      label: "Promising",
      ring: "stroke-amber-500",
      text: "text-amber-700",
      bg: "bg-amber-50",
    };
  return {
    label: "Needs work",
    ring: "stroke-rose-500",
    text: "text-rose-700",
    bg: "bg-rose-50",
  };
}

function priorityTone(priority: OptimizationPriority) {
  if (priority === "high")
    return {
      label: "High priority",
      badge: "bg-rose-100 text-rose-800",
      border: "border-rose-200",
    };
  if (priority === "medium")
    return {
      label: "Medium priority",
      badge: "bg-amber-100 text-amber-800",
      border: "border-amber-200",
    };
  return {
    label: "Low priority",
    badge: "bg-sky-100 text-sky-800",
    border: "border-sky-200",
  };
}

function BulletReviewCard({
  review,
  onAccept,
  onDiscard,
}: {
  review: BulletReview;
  onAccept: () => void;
  onDiscard: () => void;
}) {
  const { improvement } = review;

  return (
    <div className="mt-4 rounded-xl border border-violet-200 bg-violet-50 p-4 text-sm leading-6">
      <div className="flex items-center gap-2 text-sm font-semibold text-violet-900">
        <Icon name="sparkle" className="h-4 w-4" />
        Review AI improvement
      </div>
      <dl className="mt-4 space-y-4">
        <div>
          <dt className="font-medium text-slate-700">Original</dt>
          <dd className="mt-1 rounded-lg bg-white/80 p-3 text-slate-700">
            {improvement.original}
          </dd>
        </div>
        <div>
          <dt className="font-medium text-slate-700">AI improved</dt>
          <dd className="mt-1 rounded-lg border border-violet-200 bg-white p-3 font-medium text-slate-900">
            {improvement.improved}
          </dd>
        </div>
        <div>
          <dt className="font-medium text-slate-700">Why</dt>
          <dd className="mt-1 text-slate-600">{improvement.reason}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-700">Keywords added</dt>
          <dd className="mt-2">
            {improvement.keywords_added.length ? (
              <div className="flex flex-wrap gap-2">
                {improvement.keywords_added.map((keyword) => (
                  <span
                    key={keyword}
                    className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-semibold text-violet-800"
                  >
                    {keyword}
                  </span>
                ))}
              </div>
            ) : (
              <span className="text-slate-500">
                No supported JD keywords were added.
              </span>
            )}
          </dd>
        </div>
        <div>
          <dt className="font-medium text-slate-700">Facts used</dt>
          <dd className="mt-2">
            {improvement.facts_used.length ? (
              <ul className="space-y-2 text-slate-600">
                {improvement.facts_used.map((fact, index) => (
                  <li key={`${fact}-${index}`} className="flex gap-2">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-violet-500" />
                    {fact}
                  </li>
                ))}
              </ul>
            ) : (
              <span className="text-slate-500">No facts were returned.</span>
            )}
          </dd>
        </div>
      </dl>
      <div className="mt-5 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={onAccept}
          className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-violet-700"
        >
          Accept
        </button>
        <button
          type="button"
          onClick={onDiscard}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
        >
          Discard
        </button>
      </div>
    </div>
  );
}

export function Analyzer() {
  const inputId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<AnalyzeResumeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [jobMatch, setJobMatch] = useState<JobMatchResult | null>(null);
  const [matchLoading, setMatchLoading] = useState(false);
  const [matchError, setMatchError] = useState("");
  const [optimization, setOptimization] =
    useState<ResumeOptimizationResult | null>(null);
  const [optimizationLoading, setOptimizationLoading] = useState(false);
  const [optimizationError, setOptimizationError] = useState("");
  const [documentOptimization, setDocumentOptimization] =
    useState<OptimizedResumeResult | null>(null);
  const [documentOptimizationLoading, setDocumentOptimizationLoading] =
    useState(false);
  const [documentOptimizationError, setDocumentOptimizationError] =
    useState("");
  const optimizationRequestId = useRef(0);
  const [bulletReview, setBulletReview] = useState<BulletReview | null>(null);
  const [bulletLoadingKey, setBulletLoadingKey] = useState<string | null>(null);
  const [bulletError, setBulletError] = useState<{
    key: string;
    message: string;
  } | null>(null);
  const [acceptedBulletOriginals, setAcceptedBulletOriginals] = useState<
    Record<string, string>
  >({});
  const bulletRequestId = useRef(0);
  const [auth] = useState<null>(null);
  const [usage, setUsage] = useState<UsageState | null>(null);
  const [usageLoading, setUsageLoading] = useState(true);
  const [anonymousExhausted, setAnonymousExhausted] = useState(false);
  // The dedicated /dashboard/history route is authoritative; these preserve the
  // existing optional summary until its final removal.
  const [history] = useState<History | null>(null);
  const [historyLoading] = useState(false);
  const [historyError] = useState("");
  async function loadHistory() {
    return undefined;
  }
  useEffect(() => {
    const loadUsage = () => {
      void getUsage()
        .then((current) => {
          setUsage(current);
          setAnonymousExhausted(
            !current.authenticated &&
              current.analysis_count >= (current.limit ?? 0),
          );
        })
        .catch(() =>
          setError(
            "Unable to check the current analysis allowance. Please refresh and try again.",
          ),
        )
        .finally(() => setUsageLoading(false));
    };
    loadUsage();
    const onPageShow = () => loadUsage();
    window.addEventListener("pageshow", onPageShow);
    return () => window.removeEventListener("pageshow", onPageShow);
  }, []);

  function clearOptimization() {
    optimizationRequestId.current += 1;
    setOptimization(null);
    setOptimizationLoading(false);
    setOptimizationError("");
  }

  function clearBulletImprovement() {
    bulletRequestId.current += 1;
    setBulletReview(null);
    setBulletLoadingKey(null);
    setBulletError(null);
  }

  async function handleAnalyze() {
    if (
      usage &&
      !usage.authenticated &&
      usage.analysis_count >= (usage.limit ?? 0)
    ) {
      if (!usage.authenticated) setAnonymousExhausted(true);
      else setError("Your two free account analyses have been used.");
      return;
    }
    if (!file) {
      setError("Please select a resume first.");
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);
    setJobMatch(null);
    setMatchError("");
    clearOptimization();
    clearBulletImprovement();
    setAcceptedBulletOriginals({});

    try {
      const nextResult = await analyzeResume(file);
      setResult(nextResult);
      if (nextResult.usage) {
        setUsage(nextResult.usage);
        setAnonymousExhausted(
          !nextResult.usage.authenticated &&
            nextResult.usage.analysis_count >= (nextResult.usage.limit ?? 0),
        );
      }
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Something went wrong while analyzing the resume.";
      setError(message);
      if (/used your 2 free analyses|free analysis limit/i.test(message))
        setAnonymousExhausted(true);
    } finally {
      setLoading(false);
    }
  }

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const selectedFile = event.target.files?.[0];
    if (!selectedFile) return;

    const extension = selectedFile.name.split(".").pop()?.toLowerCase();
    if (extension !== "pdf" && extension !== "docx") {
      setFile(null);
      setError("Only PDF and DOCX files are supported.");
      return;
    }

    setFile(selectedFile);
    setError("");
    setResult(null);
    setJobMatch(null);
    setMatchError("");
    clearOptimization();
    clearBulletImprovement();
    setAcceptedBulletOriginals({});
  }

  async function handleJobMatch() {
    if (!result) {
      setMatchError(
        "Analyze a resume before comparing it with a job description.",
      );
      return;
    }

    if (!jobDescription.trim()) {
      setMatchError("Paste a job description before analyzing the match.");
      return;
    }

    setMatchLoading(true);
    setMatchError("");
    setJobMatch(null);
    clearOptimization();
    clearBulletImprovement();

    try {
      setJobMatch(await matchResume(result.resume, jobDescription));
    } catch (err) {
      setMatchError(
        err instanceof Error
          ? err.message
          : "Something went wrong while analyzing the job match.",
      );
    } finally {
      setMatchLoading(false);
    }
  }

  async function handleOptimizeResume() {
    if (!result || !jobMatch) {
      setOptimizationError(
        "Analyze the job match before generating resume improvements.",
      );
      return;
    }

    if (!jobDescription.trim()) {
      setOptimizationError(
        "Paste a job description before generating resume improvements.",
      );
      return;
    }

    const requestId = optimizationRequestId.current + 1;
    optimizationRequestId.current = requestId;
    setOptimizationLoading(true);
    setOptimizationError("");
    setOptimization(null);

    try {
      const optimizationResult = await optimizeResume(
        result.resume,
        jobDescription,
        jobMatch,
      );
      if (requestId === optimizationRequestId.current) {
        setOptimization(optimizationResult);
      }
    } catch (err) {
      if (requestId === optimizationRequestId.current) {
        setOptimizationError(
          err instanceof Error
            ? err.message
            : "Something went wrong while generating resume improvements.",
        );
      }
    } finally {
      if (requestId === optimizationRequestId.current) {
        setOptimizationLoading(false);
      }
    }
  }

  async function handleGenerateOptimizedResume() {
    if (!result || !jobMatch || !jobDescription.trim()) {
      setDocumentOptimizationError(
        "Analyze this resume against a job description before generating an optimized version.",
      );
      return;
    }
    if (!result.analysis_id) {
      setDocumentOptimizationError(
        "This analysis is not linked to its original upload. Re-analyze the resume before generating an optimized version.",
      );
      return;
    }
    setDocumentOptimizationLoading(true);
    setDocumentOptimizationError("");
    setDocumentOptimization(null);
    try {
      setDocumentOptimization(
        await optimizeResumeDocument(
          result.resume,
          jobDescription,
          jobMatch,
          result.analysis_id,
        ),
      );
    } catch (err) {
      setDocumentOptimizationError(
        err instanceof Error
          ? err.message
          : "Unable to generate an optimized resume.",
      );
    } finally {
      setDocumentOptimizationLoading(false);
    }
  }

  async function handleImproveBullet(target: BulletTarget) {
    if (!result || !jobDescription.trim() || bulletLoadingKey) return;

    const requestId = bulletRequestId.current + 1;
    bulletRequestId.current = requestId;
    setBulletLoadingKey(target.key);
    setBulletError(null);
    setBulletReview(null);

    try {
      const improvement = await improveResumeBullet({
        resume: result.resume,
        job_description: jobDescription,
        bullet: target.bullet,
        context: target.context,
        ...(jobMatch ? { job_match: jobMatch } : {}),
        ...(optimization
          ? { optimization_recommendations: optimization.recommendations }
          : {}),
      });
      if (requestId === bulletRequestId.current) {
        setBulletReview({ target, improvement });
      }
    } catch {
      if (requestId === bulletRequestId.current) {
        setBulletError({
          key: target.key,
          message:
            "We couldn't generate a safe improvement for this bullet. Please try again.",
        });
      }
    } finally {
      if (requestId === bulletRequestId.current) {
        setBulletLoadingKey(null);
      }
    }
  }

  function handleAcceptBulletImprovement() {
    if (!bulletReview) return;

    const { target, improvement } = bulletReview;
    setResult((currentResult) => {
      if (!currentResult) return currentResult;

      if (target.kind === "experience") {
        const experience = currentResult.resume.experience.map(
          (item, experienceIndex) =>
            experienceIndex === target.experienceIndex
              ? {
                  ...item,
                  responsibilities: item.responsibilities.map(
                    (responsibility, responsibilityIndex) =>
                      responsibilityIndex === target.responsibilityIndex
                        ? improvement.improved
                        : responsibility,
                  ),
                }
              : item,
        );
        return {
          ...currentResult,
          resume: { ...currentResult.resume, experience },
        };
      }

      const projects = currentResult.resume.projects.map(
        (item, projectIndex) =>
          projectIndex === target.projectIndex
            ? { ...item, description: improvement.improved }
            : item,
      );
      return {
        ...currentResult,
        resume: { ...currentResult.resume, projects },
      };
    });
    setAcceptedBulletOriginals((current) => ({
      ...current,
      [target.key]: improvement.original,
    }));
    setJobMatch(null);
    setMatchError("");
    clearOptimization();
    clearBulletImprovement();
  }

  const score = result ? Math.min(Math.max(result.analysis.score, 0), 100) : 0;
  const tone = scoreTone(score);
  const circumference = 2 * Math.PI * 42;

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-8 text-slate-900 sm:px-6 sm:py-12">
      <div className="mx-auto max-w-6xl">
        <section className="mb-6 rounded-2xl border border-indigo-100 bg-indigo-50 p-4 text-sm shadow-sm">
          {usageLoading || !usage ? (
            <p className="font-medium text-indigo-900">
              Checking your analysis allowance…
            </p>
          ) : usage.authenticated ? (
            <p className="font-medium text-indigo-900">
              Unlimited analyses on your account.
            </p>
          ) : anonymousExhausted ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="font-semibold text-indigo-950">
                  You&apos;ve used your 2 free analyses.
                </p>
                <p className="mt-1 text-indigo-800">
                  Create your free account or log in to continue.
                </p>
              </div>
              <div className="flex gap-2">
                <Link
                  href="/signup"
                  className="rounded-lg bg-indigo-600 px-3 py-2 font-semibold text-white"
                >
                  Create account
                </Link>
                <Link
                  href="/login"
                  className="rounded-lg border border-indigo-200 bg-white px-3 py-2 font-semibold text-indigo-800"
                >
                  Log in
                </Link>
              </div>
            </div>
          ) : (
            <p className="font-medium text-indigo-900">
              {Math.max(0, (usage.limit ?? 0) - usage.analysis_count)} free
              analyses remaining — no signup required.
            </p>
          )}
        </section>
        {auth && (
          <section className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="font-semibold">Your history</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Only analyses and matches saved to your account are shown.
                </p>
              </div>
              <button
                type="button"
                onClick={loadHistory}
                disabled={historyLoading}
                className="rounded-lg border px-3 py-2 text-sm font-semibold disabled:opacity-50"
              >
                Refresh
              </button>
            </div>
            {historyLoading ? (
              <p className="mt-4 text-sm text-slate-500">
                Loading your private history…
              </p>
            ) : historyError ? (
              <p role="alert" className="mt-4 text-sm text-rose-700">
                {historyError}
              </p>
            ) : history &&
              !history.analyses.length &&
              !history.matches.length ? (
              <p className="mt-4 text-sm text-slate-500">
                No saved analyses or job matches yet.
              </p>
            ) : history ? (
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                <div>
                  <h3 className="text-sm font-semibold text-slate-700">
                    Resume analyses
                  </h3>
                  <div className="mt-2 space-y-2">
                    {history.analyses.map((item) => (
                      <article
                        key={item.id}
                        className="rounded-lg bg-slate-50 p-3 text-sm"
                      >
                        <p className="font-medium">
                          {item.filename || "Resume analysis"}
                        </p>
                        <p className="mt-1 text-slate-500">
                          {new Date(item.created_at).toLocaleString()} ·{" "}
                          {item.file_type?.toUpperCase() || "Resume"}
                        </p>
                      </article>
                    ))}
                  </div>
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-slate-700">
                    Job matches
                  </h3>
                  <div className="mt-2 space-y-2">
                    {history.matches.map((item) => (
                      <article
                        key={item.id}
                        className="rounded-lg bg-slate-50 p-3 text-sm"
                      >
                        <div className="flex justify-between gap-3">
                          <p className="font-medium line-clamp-2">
                            {item.job_description || "Job description"}
                          </p>
                          {typeof item.match_score === "number" && (
                            <span className="shrink-0 font-semibold text-indigo-700">
                              {item.match_score}/100
                            </span>
                          )}
                        </div>
                        <p className="mt-1 text-slate-500">
                          {new Date(item.created_at).toLocaleString()}
                        </p>
                      </article>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}
          </section>
        )}
        <header className="flex flex-col gap-5 border-b border-slate-200 pb-8 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-indigo-700">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-600 text-white">
                <Icon name="sparkle" className="h-4 w-4" />
              </span>
              Resume intelligence
            </div>
            <h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-4xl">
              AI Resume Analyzer
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600 sm:text-base">
              Upload a resume for a structured, ATS-style review of its content,
              skills, and overall readiness.
            </p>
          </div>
          {result && (
            <p className="text-sm text-slate-500">
              Analyzed{" "}
              <span className="font-medium text-slate-700">
                {result.filename}
              </span>
            </p>
          )}
        </header>

        <section
          aria-labelledby="upload-heading"
          className="mt-8 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-8"
        >
          <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 id="upload-heading" className="text-xl font-semibold">
                Analyze your resume
              </h2>
              <p className="mt-1 text-sm text-slate-600">
                PDF and DOCX files supported. We automatically validate that the
                document is a resume or CV before analysis.
              </p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <input
                id={inputId}
                type="file"
                accept=".pdf,.docx"
                onChange={handleFileChange}
                className="sr-only"
              />
              <label
                htmlFor={inputId}
                className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition hover:border-indigo-300 hover:bg-indigo-50"
              >
                <Icon name="document" className="text-indigo-600" />
                {file ? "Choose another file" : "Choose a document"}
              </label>
              <button
                type="button"
                onClick={handleAnalyze}
                disabled={loading || !file}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading && (
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                )}
                {loading ? "Validating and analyzing…" : "Analyze resume"}
              </button>
            </div>
          </div>
          {file && (
            <div className="mt-5 flex items-center gap-3 rounded-xl bg-slate-50 px-4 py-3 text-sm">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white text-indigo-600 shadow-sm">
                <Icon name="document" className="h-4 w-4" />
              </span>
              <span className="min-w-0 truncate font-medium text-slate-700">
                {file.name}
              </span>
              <span className="ml-auto shrink-0 text-slate-500">
                {(file.size / 1024 / 1024).toFixed(1)} MB
              </span>
            </div>
          )}
          {error && (
            <div
              role="alert"
              className="mt-5 flex gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"
            >
              <Icon name="warning" className="mt-0.5 shrink-0" />
              <p>{error}</p>
            </div>
          )}
        </section>

        {result && (
          <div className="mt-8 space-y-6">
            <div className="grid gap-6 lg:grid-cols-3">
              <SectionCard className="flex items-center gap-5">
                <div className="relative h-28 w-28 shrink-0">
                  <svg
                    className="h-full w-full -rotate-90"
                    viewBox="0 0 100 100"
                    aria-label={`Resume score: ${score} out of 100`}
                    role="img"
                  >
                    <circle
                      cx="50"
                      cy="50"
                      r="42"
                      className="stroke-slate-100"
                      fill="none"
                      strokeWidth="9"
                    />
                    <circle
                      cx="50"
                      cy="50"
                      r="42"
                      className={tone.ring}
                      fill="none"
                      strokeLinecap="round"
                      strokeWidth="9"
                      style={{
                        strokeDasharray: circumference,
                        strokeDashoffset: circumference * (1 - score / 100),
                      }}
                    />
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-2xl font-bold">{score}</span>
                    <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
                      of 100
                    </span>
                  </div>
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-500">
                    Overall score
                  </p>
                  <p
                    className={`mt-1 inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${tone.bg} ${tone.text}`}
                  >
                    {tone.label}
                  </p>
                  <p className="mt-2 text-xs leading-5 text-slate-500">
                    A content-based assessment, not a guarantee of interview
                    outcomes.
                  </p>
                </div>
              </SectionCard>
              <SectionCard className="lg:col-span-2">
                <p className="text-sm font-medium text-slate-500">
                  Resume overview
                </p>
                <h2 className="mt-2 text-2xl font-bold">
                  {result.resume.name || "Name not available"}
                </h2>
                <p className="mt-1 font-medium text-indigo-700">
                  {result.resume.title || "Professional title not available"}
                </p>
                <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-600">
                  {result.resume.summary ||
                    "No professional summary was found in the resume."}
                </p>
              </SectionCard>
            </div>

            <SectionCard>
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div className="flex items-center gap-3">
                    <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-50 text-indigo-700">
                      <Icon name="sparkle" />
                    </span>
                    <h2 className="text-lg font-semibold">ATS job match</h2>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-slate-500">
                    Paste a job description to compare it with this analyzed
                    resume. The resume will not be uploaded or parsed again.
                  </p>
                </div>
                <span className="shrink-0 rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                  Resume ready
                </span>
              </div>
              <label
                htmlFor="job-description"
                className="mt-5 block text-sm font-medium text-slate-700"
              >
                Job description
              </label>
              <textarea
                id="job-description"
                value={jobDescription}
                onChange={(event) => {
                  setJobDescription(event.target.value);
                  setJobMatch(null);
                  setMatchError("");
                  clearOptimization();
                  clearBulletImprovement();
                }}
                placeholder="Paste the role responsibilities, required skills, and qualifications here..."
                rows={7}
                className="mt-2 block w-full resize-y rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm leading-6 text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100"
              />
              <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-xs text-slate-500">
                  Uses the structured resume already shown above.
                </p>
                <button
                  type="button"
                  onClick={handleJobMatch}
                  disabled={matchLoading || !jobDescription.trim()}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {matchLoading && (
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                  )}
                  {matchLoading ? "Matching job..." : "Analyze job match"}
                </button>
              </div>
              {matchError && (
                <div
                  role="alert"
                  className="mt-4 flex gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"
                >
                  <Icon name="warning" className="mt-0.5 shrink-0" />
                  <p>{matchError}</p>
                </div>
              )}
            </SectionCard>

            {jobMatch && (
              <section
                aria-labelledby="match-results-heading"
                className="space-y-6"
              >
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-sm font-medium text-indigo-700">
                      ATS comparison
                    </p>
                    <h2
                      id="match-results-heading"
                      className="text-2xl font-bold"
                    >
                      Job match results
                    </h2>
                  </div>
                  <span className="text-sm text-slate-500">
                    Based on documented resume content
                  </span>
                </div>
                <div className="grid gap-6 lg:grid-cols-3">
                  <SectionCard className="flex items-center gap-5">
                    <div className="relative h-28 w-28 shrink-0">
                      <svg
                        className="h-full w-full -rotate-90"
                        viewBox="0 0 100 100"
                        aria-label={`Job match score: ${jobMatch.match_score} out of 100`}
                        role="img"
                      >
                        <circle
                          cx="50"
                          cy="50"
                          r="42"
                          className="stroke-slate-100"
                          fill="none"
                          strokeWidth="9"
                        />
                        <circle
                          cx="50"
                          cy="50"
                          r="42"
                          className="stroke-indigo-500"
                          fill="none"
                          strokeLinecap="round"
                          strokeWidth="9"
                          style={{
                            strokeDasharray: circumference,
                            strokeDashoffset:
                              circumference *
                              (1 -
                                Math.min(
                                  Math.max(jobMatch.match_score, 0),
                                  100,
                                ) /
                                  100),
                          }}
                        />
                      </svg>
                      <div className="absolute inset-0 flex flex-col items-center justify-center">
                        <span className="text-2xl font-bold">
                          {jobMatch.match_score}
                        </span>
                        <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
                          match score
                        </span>
                      </div>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-500">
                        Role alignment
                      </p>
                      <p className="mt-2 text-xs leading-5 text-slate-500">
                        Compares recognized job requirements, title keywords,
                        and documented evidence.
                      </p>
                    </div>
                  </SectionCard>
                  <SectionCard>
                    <p className="text-sm font-medium text-slate-500">
                      Title alignment
                    </p>
                    <div className="mt-3 flex items-end justify-between">
                      <span className="text-4xl font-bold text-slate-900">
                        {jobMatch.title_alignment}
                      </span>
                      <span className="mb-1 text-sm text-slate-500">/ 10</span>
                    </div>
                    <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className="h-full rounded-full bg-indigo-500"
                        style={{
                          width: `${Math.min(Math.max(jobMatch.title_alignment, 0), 10) * 10}%`,
                        }}
                      />
                    </div>
                    <p className="mt-3 text-xs leading-5 text-slate-500">
                      Based on documented title and role keywords.
                    </p>
                  </SectionCard>
                  <SectionCard>
                    <p className="text-sm font-medium text-slate-500">
                      Keyword coverage
                    </p>
                    <div className="mt-3 flex items-end justify-between">
                      <span className="text-4xl font-bold text-slate-900">
                        {jobMatch.keyword_coverage.percentage}%
                      </span>
                      <span className="mb-1 text-sm text-slate-500">
                        {jobMatch.keyword_coverage.matched} of{" "}
                        {jobMatch.keyword_coverage.total}
                      </span>
                    </div>
                    <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className="h-full rounded-full bg-indigo-500"
                        style={{
                          width: `${Math.min(Math.max(jobMatch.keyword_coverage.percentage, 0), 100)}%`,
                        }}
                      />
                    </div>
                    <p className="mt-3 text-xs leading-5 text-slate-500">
                      Important controlled ATS terms found in the resume.
                    </p>
                  </SectionCard>
                </div>
                <SectionCard>
                  <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <h3 className="text-lg font-semibold">Score breakdown</h3>
                      <p className="text-sm text-slate-500">
                        Each value is returned directly by the deterministic
                        matcher.
                      </p>
                    </div>
                    <span className="text-sm font-semibold text-indigo-700">
                      {jobMatch.match_score} / 100 total
                    </span>
                  </div>
                  <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
                    {[
                      {
                        label: "Skills",
                        value: jobMatch.score_breakdown.skills,
                        maximum: 45,
                        color: "bg-indigo-500",
                      },
                      {
                        label: "Experience",
                        value: jobMatch.score_breakdown.experience,
                        maximum: 20,
                        color: "bg-sky-500",
                      },
                      {
                        label: "Responsibilities",
                        value: jobMatch.score_breakdown.responsibilities,
                        maximum: 15,
                        color: "bg-violet-500",
                      },
                      {
                        label: "Seniority",
                        value: jobMatch.score_breakdown.seniority,
                        maximum: 10,
                        color: "bg-amber-500",
                      },
                      {
                        label: "Keywords",
                        value: jobMatch.score_breakdown.keywords,
                        maximum: 10,
                        color: "bg-emerald-500",
                      },
                    ].map((item) => (
                      <div
                        key={item.label}
                        className="rounded-xl bg-slate-50 p-4"
                      >
                        <div className="flex items-baseline justify-between gap-2">
                          <p className="text-sm font-medium text-slate-700">
                            {item.label}
                          </p>
                          <p className="text-sm font-semibold text-slate-900">
                            {item.value}
                            <span className="text-slate-400">
                              /{item.maximum}
                            </span>
                          </p>
                        </div>
                        <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200">
                          <div
                            className={`h-full rounded-full ${item.color}`}
                            style={{
                              width: `${(Math.min(Math.max(item.value, 0), item.maximum) / item.maximum) * 100}%`,
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </SectionCard>
                <div className="grid gap-6 lg:grid-cols-2">
                  <SectionCard>
                    <h3 className="text-lg font-semibold">Job requirements</h3>
                    <p className="mt-1 text-sm text-slate-500">
                      Required requirements have more influence on the match
                      score.
                    </p>
                    <div className="mt-5 grid gap-5 sm:grid-cols-2">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-rose-700">
                          Required
                        </p>
                        {jobMatch.requirements.required.length ? (
                          <div className="mt-3 flex flex-wrap gap-2">
                            {jobMatch.requirements.required.map((item) => (
                              <span
                                key={item}
                                className="rounded-full bg-rose-50 px-3 py-1.5 text-sm font-medium text-rose-800"
                              >
                                {item}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <EmptyState>
                            No controlled required requirements were identified.
                          </EmptyState>
                        )}
                      </div>
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-sky-700">
                          Preferred
                        </p>
                        {jobMatch.requirements.preferred.length ? (
                          <div className="mt-3 flex flex-wrap gap-2">
                            {jobMatch.requirements.preferred.map((item) => (
                              <span
                                key={item}
                                className="rounded-full bg-sky-50 px-3 py-1.5 text-sm font-medium text-sky-800"
                              >
                                {item}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <EmptyState>
                            No controlled preferred requirements were
                            identified.
                          </EmptyState>
                        )}
                      </div>
                    </div>
                  </SectionCard>
                  <SectionCard>
                    <h3 className="text-lg font-semibold">
                      Keyword coverage details
                    </h3>
                    {jobMatch.keyword_coverage.missing_keywords.length ? (
                      <>
                        <p className="mt-1 text-sm text-slate-500">
                          Terms recognized in the JD but not documented in this
                          resume.
                        </p>
                        <div className="mt-4 flex flex-wrap gap-2">
                          {jobMatch.keyword_coverage.missing_keywords.map(
                            (keyword) => (
                              <span
                                key={keyword}
                                className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-800"
                              >
                                {keyword.replace(
                                  /^(skill|responsibility):/,
                                  "",
                                )}
                              </span>
                            ),
                          )}
                        </div>
                      </>
                    ) : (
                      <EmptyState>
                        All controlled ATS keywords identified in this job
                        description are documented in the resume.
                      </EmptyState>
                    )}
                  </SectionCard>
                </div>
                <SectionCard>
                  <h3 className="text-lg font-semibold">Matched skills</h3>
                  {jobMatch.matched_skills.length ? (
                    <div className="mt-4 flex flex-wrap gap-2">
                      {jobMatch.matched_skills.map((skill) => (
                        <span
                          key={skill}
                          className="rounded-full bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-800"
                        >
                          {skill}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <EmptyState>
                      No recognized job requirements were matched in the resume.
                    </EmptyState>
                  )}
                </SectionCard>
                <div className="grid gap-6 lg:grid-cols-2">
                  {jobMatch.missing_skills.length > 0 && (
                    <SectionCard>
                      <div className="flex items-center gap-3">
                        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-50 text-amber-700">
                          <Icon name="warning" />
                        </span>
                        <h3 className="text-lg font-semibold">
                          Missing skills
                        </h3>
                      </div>
                      <div className="mt-4 flex flex-wrap gap-2">
                        {jobMatch.missing_skills.map((skill) => (
                          <span
                            key={skill}
                            className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-800"
                          >
                            {skill}
                          </span>
                        ))}
                      </div>
                    </SectionCard>
                  )}
                  {jobMatch.matching_experience.length > 0 && (
                    <SectionCard>
                      <h3 className="text-lg font-semibold">
                        Matching experience
                      </h3>
                      <ul className="mt-4 space-y-3">
                        {jobMatch.matching_experience.map((item, index) => (
                          <li
                            key={`${item}-${index}`}
                            className="flex gap-3 text-sm leading-6 text-slate-700"
                          >
                            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-500" />
                            {item}
                          </li>
                        ))}
                      </ul>
                    </SectionCard>
                  )}
                </div>
                <div className="grid gap-6 lg:grid-cols-2">
                  {jobMatch.gaps.length > 0 && (
                    <SectionCard>
                      <h3 className="text-lg font-semibold">Gaps to review</h3>
                      <ul className="mt-4 space-y-3">
                        {jobMatch.gaps.map((item, index) => (
                          <li
                            key={`${item}-${index}`}
                            className="flex gap-3 text-sm leading-6 text-slate-700"
                          >
                            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-rose-500" />
                            {item}
                          </li>
                        ))}
                      </ul>
                    </SectionCard>
                  )}
                  {jobMatch.recommendations.length > 0 && (
                    <SectionCard>
                      <h3 className="text-lg font-semibold">Recommendations</h3>
                      <ul className="mt-4 space-y-3">
                        {jobMatch.recommendations.map((item, index) => (
                          <li
                            key={`${item}-${index}`}
                            className="flex gap-3 text-sm leading-6 text-slate-700"
                          >
                            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold text-white">
                              {index + 1}
                            </span>
                            {item}
                          </li>
                        ))}
                      </ul>
                    </SectionCard>
                  )}
                  <SectionCard>
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <h3 className="text-lg font-semibold">
                          Generate optimized resume
                        </h3>
                        <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">
                          Create a separate, JD-specific version from grounded
                          bullet rewrites. Your original resume stays unchanged.
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={(event) => {
                          // This remains a client-side POST action even if the
                          // analyzer is ever embedded inside a form.
                          event.preventDefault();
                          void handleGenerateOptimizedResume();
                        }}
                        disabled={
                          documentOptimizationLoading || !result.analysis_id
                        }
                        className="rounded-xl bg-violet-600 px-5 py-3 text-sm font-semibold text-white disabled:opacity-50"
                      >
                        {documentOptimizationLoading
                          ? "Generating…"
                          : "Optimize resume"}
                      </button>
                    </div>
                    {documentOptimizationError && (
                      <p
                        role="alert"
                        className="mt-4 rounded-xl bg-rose-50 p-3 text-sm text-rose-700"
                      >
                        {documentOptimizationError}
                      </p>
                    )}
                    {documentOptimizationLoading && (
                      <p className="mt-4 text-sm text-violet-700">
                        Validating grounded rewrites and preparing your
                        optimized DOCX…
                      </p>
                    )}
                    {documentOptimization && (
                      <div className="mt-5 space-y-4">
                        {!documentOptimization.safe_rewrites_generated && (
                          <p className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                            No additional wording changes could be verified
                            without adding unsupported claims. Your separate
                            download preserves the original documented content;
                            review the unsupported requirements below.
                          </p>
                        )}
                        <p className="text-sm text-slate-600">
                          Actual deterministic match:{" "}
                          {documentOptimization.original_match_score ?? "—"} →{" "}
                          {documentOptimization.optimized_match_score ?? "—"}.
                          Downloads expire in 3 days or after three total
                          downloads.
                        </p>
                        <div className="flex flex-wrap gap-3">
                          {documentOptimization.available_formats.includes(
                            "docx",
                          ) && (
                            <a
                              href={optimizedResumeDownloadUrl(
                                documentOptimization.id,
                                "docx",
                              )}
                              className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700"
                            >
                              Download DOCX
                            </a>
                          )}
                        </div>
                        {documentOptimization.improvements.length > 0 && (
                          <ul className="space-y-3 text-sm">
                            {documentOptimization.improvements.map((item) => (
                              <li
                                key={item.original}
                                className="rounded-xl bg-slate-50 p-3"
                              >
                                <p className="text-slate-500">
                                  {item.original}
                                </p>
                                <p className="mt-1 font-medium text-slate-900">
                                  {item.improved}
                                </p>
                                <p className="mt-1 text-slate-600">
                                  {item.reason}
                                </p>
                              </li>
                            ))}
                          </ul>
                        )}
                        {documentOptimization.unsupported_requirements.length >
                          0 && (
                          <div>
                            <p className="text-sm font-semibold text-amber-800">
                              Unsupported JD requirements
                            </p>
                            <div className="mt-2 flex flex-wrap gap-2">
                              {documentOptimization.unsupported_requirements.map(
                                (item) => (
                                  <span
                                    key={item}
                                    className="rounded-full bg-amber-50 px-3 py-1 text-xs text-amber-800"
                                  >
                                    {item}
                                  </span>
                                ),
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </SectionCard>
                </div>

                <SectionCard>
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <div className="flex items-center gap-3">
                        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-violet-50 text-violet-700">
                          <Icon name="sparkle" />
                        </span>
                        <div>
                          <p className="text-sm font-medium text-violet-700">
                            Targeted editing guidance
                          </p>
                          <h3
                            id="resume-optimization-heading"
                            className="text-lg font-semibold"
                          >
                            How to Improve Your Resume
                          </h3>
                        </div>
                      </div>
                      <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
                        Generate prioritized, job-specific edits from the
                        current ATS match. Suggestions only identify places to
                        document evidence you can truthfully support.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={handleOptimizeResume}
                      disabled={optimizationLoading}
                      className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-violet-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {optimizationLoading && (
                        <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                      )}
                      {optimizationLoading
                        ? "Generating guidance..."
                        : optimization
                          ? "Refresh improvements"
                          : "Show improvements"}
                    </button>
                  </div>

                  {optimizationError && (
                    <div
                      role="alert"
                      className="mt-5 flex gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"
                    >
                      <Icon name="warning" className="mt-0.5 shrink-0" />
                      <p>{optimizationError}</p>
                    </div>
                  )}

                  {!optimization &&
                    !optimizationLoading &&
                    !optimizationError && (
                      <EmptyState>
                        Select{" "}
                        <span className="font-medium text-slate-700">
                          Show improvements
                        </span>{" "}
                        to get prioritized guidance for this job description.
                      </EmptyState>
                    )}

                  {optimizationLoading && (
                    <div
                      aria-live="polite"
                      className="mt-5 flex items-center gap-3 rounded-xl bg-violet-50 p-4 text-sm text-violet-800"
                    >
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-violet-300 border-t-violet-700" />
                      Reviewing the current ATS evidence…
                    </div>
                  )}

                  {optimization &&
                    (optimization.recommendations.length ? (
                      <div className="mt-6 space-y-6">
                        {(["high", "medium", "low"] as const).map(
                          (priority) => {
                            const items = optimization.recommendations.filter(
                              (item) => item.priority === priority,
                            );
                            const tone = priorityTone(priority);
                            return items.length ? (
                              <div key={priority}>
                                <div className="flex items-center gap-3">
                                  <span
                                    className={`rounded-full px-3 py-1 text-xs font-semibold ${tone.badge}`}
                                  >
                                    {tone.label}
                                  </span>
                                  <p className="text-sm text-slate-500">
                                    {items.length}{" "}
                                    {items.length === 1
                                      ? "recommendation"
                                      : "recommendations"}
                                  </p>
                                </div>
                                <div className="mt-3 space-y-3">
                                  {items.map((item) => (
                                    <article
                                      key={`${item.category}-${item.issue}`}
                                      className={`rounded-xl border p-4 ${tone.border} bg-slate-50`}
                                    >
                                      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                                        <div>
                                          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                                            {item.category}
                                          </p>
                                          <h4 className="mt-1 font-semibold text-slate-900">
                                            {item.section}
                                          </h4>
                                        </div>
                                        <span
                                          className={`w-fit rounded-full px-2.5 py-1 text-xs font-semibold ${tone.badge}`}
                                        >
                                          {tone.label}
                                        </span>
                                      </div>
                                      <dl className="mt-4 space-y-3 text-sm leading-6">
                                        <div>
                                          <dt className="font-medium text-slate-700">
                                            Issue
                                          </dt>
                                          <dd className="text-slate-600">
                                            {item.issue}
                                          </dd>
                                        </div>
                                        <div>
                                          <dt className="font-medium text-slate-700">
                                            What to improve
                                          </dt>
                                          <dd className="text-slate-700">
                                            {item.recommendation}
                                          </dd>
                                        </div>
                                        <div>
                                          <dt className="font-medium text-slate-700">
                                            Why it matters
                                          </dt>
                                          <dd className="text-slate-600">
                                            {item.reason}
                                          </dd>
                                        </div>
                                      </dl>
                                    </article>
                                  ))}
                                </div>
                              </div>
                            ) : null;
                          },
                        )}
                      </div>
                    ) : (
                      <EmptyState>
                        No targeted resume improvements were identified for the
                        current documented resume and job match.
                      </EmptyState>
                    ))}
                </SectionCard>
              </section>
            )}

            <div className="grid gap-6 lg:grid-cols-2">
              <SectionCard>
                <div className="flex items-center gap-3">
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700">
                    <Icon name="check" />
                  </span>
                  <h2 className="text-lg font-semibold">Strengths</h2>
                </div>
                {result.analysis.strengths.length ? (
                  <ul className="mt-5 space-y-3">
                    {result.analysis.strengths.map((item, index) => (
                      <li
                        key={`${item}-${index}`}
                        className="flex gap-3 text-sm leading-6 text-slate-700"
                      >
                        <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
                        {item}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState>No strengths were identified.</EmptyState>
                )}
              </SectionCard>
              <SectionCard>
                <div className="flex items-center gap-3">
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-50 text-amber-700">
                    <Icon name="warning" />
                  </span>
                  <h2 className="text-lg font-semibold">Areas to improve</h2>
                </div>
                {result.analysis.weaknesses.length ? (
                  <ul className="mt-5 space-y-3">
                    {result.analysis.weaknesses.map((item, index) => (
                      <li
                        key={`${item}-${index}`}
                        className="flex gap-3 text-sm leading-6 text-slate-700"
                      >
                        <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                        {item}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState>No weaknesses were identified.</EmptyState>
                )}
              </SectionCard>
            </div>

            <SectionCard>
              <div className="flex items-center gap-3">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-50 text-indigo-700">
                  <Icon name="sparkle" />
                </span>
                <div>
                  <h2 className="text-lg font-semibold">
                    Recommended next steps
                  </h2>
                  <p className="text-sm text-slate-500">
                    Use these as editing prompts; do not add claims you cannot
                    support.
                  </p>
                </div>
              </div>
              {result.analysis.suggestions.length ? (
                <ol className="mt-5 grid gap-3 md:grid-cols-2">
                  {result.analysis.suggestions.map((item, index) => (
                    <li
                      key={`${item}-${index}`}
                      className="flex gap-3 rounded-xl bg-slate-50 p-4 text-sm leading-6 text-slate-700"
                    >
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold text-white">
                        {index + 1}
                      </span>
                      {item}
                    </li>
                  ))}
                </ol>
              ) : (
                <EmptyState>No suggestions are available.</EmptyState>
              )}
            </SectionCard>

            <div className="grid gap-6 lg:grid-cols-3">
              <SectionCard className="lg:col-span-2">
                <h2 className="text-lg font-semibold">Skills found</h2>
                {result.resume.skills.length ? (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {result.resume.skills.map((skill, index) => (
                      <span
                        key={`${skill}-${index}`}
                        className="rounded-full bg-indigo-50 px-3 py-1.5 text-sm font-medium text-indigo-800"
                      >
                        {skill}
                      </span>
                    ))}
                  </div>
                ) : (
                  <EmptyState>No skills were found.</EmptyState>
                )}
              </SectionCard>
              <SectionCard>
                <div className="flex items-center gap-2">
                  <Icon name="info" className="text-slate-400" />
                  <h2 className="text-lg font-semibold">
                    Potential skills to develop
                  </h2>
                </div>
                {result.analysis.missing_skills.length ? (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {result.analysis.missing_skills.map((skill, index) => (
                      <span
                        key={`${skill}-${index}`}
                        className="rounded-full border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-700"
                      >
                        {skill}
                      </span>
                    ))}
                  </div>
                ) : (
                  <EmptyState>No missing skills were identified.</EmptyState>
                )}
              </SectionCard>
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              <SectionCard>
                <h2 className="text-lg font-semibold">Experience</h2>
                {!jobDescription.trim() && (
                  <p className="mt-2 text-sm text-slate-500">
                    Add a job description to enable one-bullet AI improvements.
                  </p>
                )}
                {result.resume.experience.length ? (
                  <div className="mt-5 space-y-6 border-l border-slate-200 pl-5">
                    {result.resume.experience.map((item, experienceIndex) => (
                      <article
                        key={`${item.company}-${item.role}-${experienceIndex}`}
                        className="relative"
                      >
                        <span className="absolute -left-[1.62rem] top-1.5 h-3 w-3 rounded-full border-2 border-white bg-indigo-500" />
                        <h3 className="font-semibold text-slate-900">
                          {item.role || "Role not available"}
                        </h3>
                        <p className="mt-0.5 text-sm font-medium text-indigo-700">
                          {item.company || "Company not available"}
                        </p>
                        {item.duration && (
                          <p className="mt-1 text-xs font-medium uppercase tracking-wide text-slate-500">
                            {item.duration}
                          </p>
                        )}
                        {item.responsibilities?.length > 0 && (
                          <ul className="mt-3 space-y-4">
                            {item.responsibilities.map(
                              (responsibility, responsibilityIndex) => {
                                const key = `experience-${experienceIndex}-${responsibilityIndex}`;
                                const target: BulletTarget = {
                                  key,
                                  kind: "experience",
                                  bullet: responsibility,
                                  experienceIndex,
                                  responsibilityIndex,
                                  context: {
                                    company: item.company,
                                    role: item.role,
                                    section: "experience",
                                  },
                                };
                                const isLoading = bulletLoadingKey === key;
                                return (
                                  <li
                                    key={`${responsibility}-${responsibilityIndex}`}
                                    className="rounded-lg bg-slate-50 p-3"
                                  >
                                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                      <p className="text-sm leading-6 text-slate-600">
                                        {responsibility}
                                      </p>
                                      <button
                                        type="button"
                                        onClick={() =>
                                          handleImproveBullet(target)
                                        }
                                        disabled={
                                          !jobDescription.trim() ||
                                          !responsibility ||
                                          Boolean(bulletLoadingKey)
                                        }
                                        className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-violet-200 bg-white px-3 py-2 text-xs font-semibold text-violet-700 transition hover:bg-violet-50 disabled:cursor-not-allowed disabled:opacity-50"
                                      >
                                        {isLoading && (
                                          <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-violet-300 border-t-violet-700" />
                                        )}
                                        {isLoading ? "Improving..." : "Improve"}
                                      </button>
                                    </div>
                                    {acceptedBulletOriginals[key] && (
                                      <p className="mt-3 text-xs leading-5 text-slate-500">
                                        <span className="font-semibold text-slate-600">
                                          Original:
                                        </span>{" "}
                                        {acceptedBulletOriginals[key]}
                                      </p>
                                    )}
                                    {bulletError?.key === key && (
                                      <p
                                        role="alert"
                                        className="mt-3 text-sm text-rose-700"
                                      >
                                        {bulletError.message}
                                      </p>
                                    )}
                                    {bulletReview?.target.key === key && (
                                      <BulletReviewCard
                                        review={bulletReview}
                                        onAccept={handleAcceptBulletImprovement}
                                        onDiscard={clearBulletImprovement}
                                      />
                                    )}
                                  </li>
                                );
                              },
                            )}
                          </ul>
                        )}
                      </article>
                    ))}
                  </div>
                ) : (
                  <EmptyState>No experience was found.</EmptyState>
                )}
              </SectionCard>
              <div className="space-y-6">
                <SectionCard>
                  <h2 className="text-lg font-semibold">Education</h2>
                  {result.resume.education.length ? (
                    <div className="mt-4 space-y-3">
                      {result.resume.education.map((item, index) => (
                        <article
                          key={`${item.degree}-${item.institution}-${index}`}
                          className="rounded-xl bg-slate-50 p-4"
                        >
                          <h3 className="font-semibold text-slate-900">
                            {item.degree || "Degree not available"}
                          </h3>
                          <p className="mt-1 text-sm text-slate-600">
                            {item.institution || "Institution not available"}
                          </p>
                          {item.duration && (
                            <p className="mt-1 text-xs text-slate-500">
                              {item.duration}
                            </p>
                          )}
                        </article>
                      ))}
                    </div>
                  ) : (
                    <EmptyState>No education information was found.</EmptyState>
                  )}
                </SectionCard>
                <SectionCard>
                  <h2 className="text-lg font-semibold">Projects</h2>
                  {!jobDescription.trim() && (
                    <p className="mt-2 text-sm text-slate-500">
                      Add a job description to enable one-bullet AI
                      improvements.
                    </p>
                  )}
                  {result.resume.projects.length ? (
                    <div className="mt-4 space-y-3">
                      {result.resume.projects.map((item, projectIndex) => {
                        const key = `project-${projectIndex}`;
                        const target: BulletTarget = {
                          key,
                          kind: "projects",
                          bullet: item.description,
                          projectIndex,
                          context: { section: "projects" },
                        };
                        const isLoading = bulletLoadingKey === key;
                        return (
                          <article
                            key={`${item.name}-${projectIndex}`}
                            className="rounded-xl bg-slate-50 p-4"
                          >
                            <h3 className="font-semibold text-slate-900">
                              {item.name || "Project name not available"}
                            </h3>
                            <div className="mt-2 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                              <p className="text-sm leading-6 text-slate-600">
                                {item.description ||
                                  "No project description was found."}
                              </p>
                              <button
                                type="button"
                                onClick={() => handleImproveBullet(target)}
                                disabled={
                                  !jobDescription.trim() ||
                                  !item.description ||
                                  Boolean(bulletLoadingKey)
                                }
                                className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-violet-200 bg-white px-3 py-2 text-xs font-semibold text-violet-700 transition hover:bg-violet-50 disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                {isLoading && (
                                  <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-violet-300 border-t-violet-700" />
                                )}
                                {isLoading ? "Improving..." : "Improve"}
                              </button>
                            </div>
                            {acceptedBulletOriginals[key] && (
                              <p className="mt-3 text-xs leading-5 text-slate-500">
                                <span className="font-semibold text-slate-600">
                                  Original:
                                </span>{" "}
                                {acceptedBulletOriginals[key]}
                              </p>
                            )}
                            {bulletError?.key === key && (
                              <p
                                role="alert"
                                className="mt-3 text-sm text-rose-700"
                              >
                                {bulletError.message}
                              </p>
                            )}
                            {bulletReview?.target.key === key && (
                              <BulletReviewCard
                                review={bulletReview}
                                onAccept={handleAcceptBulletImprovement}
                                onDiscard={clearBulletImprovement}
                              />
                            )}
                          </article>
                        );
                      })}
                    </div>
                  ) : (
                    <EmptyState>No projects were found.</EmptyState>
                  )}
                </SectionCard>
              </div>
            </div>
            <p className="pb-4 text-center text-xs text-slate-400">
              Analyzed file: {result.filename} ·{" "}
              {result.file_type.toUpperCase()}
            </p>
          </div>
        )}
      </div>
    </main>
  );
}

export default function LandingPage() {
  const primaryHref = "/dashboard/analyzer";
  return (
    <main className="min-h-screen overflow-hidden bg-slate-50 text-slate-900">
      <div className="absolute inset-x-0 top-0 -z-10 h-[34rem] bg-[radial-gradient(circle_at_20%_15%,#dbeafe,transparent_30%),radial-gradient(circle_at_80%_10%,#e0e7ff,transparent_32%),linear-gradient(#fff,#f8fafc)]" />
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-5 py-6">
        <Link
          href="/"
          className="text-lg font-bold tracking-tight text-indigo-700"
        >
          Resume Analyzer
        </Link>
        <div className="hidden gap-6 text-sm font-medium text-slate-600 md:flex">
          <a href="#features">Features</a>
          <a href="#how-it-works">How it works</a>
        </div>
        <div className="flex items-center gap-3 text-sm font-semibold">
          <a href="/login" className="px-3 py-2 text-slate-700">
            Login
          </a>
          <a
            href="/signup"
            className="rounded-lg bg-indigo-600 px-4 py-2 text-white shadow-sm hover:bg-indigo-700"
          >
            Get started
          </a>
        </div>
      </nav>
      <section className="mx-auto max-w-6xl px-5 pb-20 pt-16 text-center sm:pt-24">
        <p className="mx-auto w-fit rounded-full border border-indigo-200 bg-white/80 px-3 py-1 text-sm font-semibold text-indigo-700">
          Built for every profession, everywhere
        </p>
        <h1 className="mx-auto mt-6 max-w-4xl text-4xl font-bold tracking-tight sm:text-6xl">
          Turn your resume into a clearer path to your next role.
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg leading-8 text-slate-600">
          AI-powered resume analysis and job matching that turns documented
          experience into practical, ATS-style guidance—without inventing your
          story.
        </p>
        <div className="mt-9 flex flex-wrap justify-center gap-3">
          <a
            href={primaryHref}
            className="rounded-xl bg-indigo-600 px-6 py-3 font-semibold text-white shadow-lg shadow-indigo-200 hover:bg-indigo-700"
          >
            Analyze my resume
          </a>
          <a
            href="/login"
            className="rounded-xl border border-slate-300 bg-white px-6 py-3 font-semibold text-slate-700 hover:bg-slate-50"
          >
            Login
          </a>
        </div>
        <p className="mt-4 text-sm text-slate-500">
          Start with 2 free resume analyses.
        </p>
      </section>
      <section id="features" className="mx-auto max-w-6xl px-5 py-16">
        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {[
            [
              "Resume analysis",
              "Structured feedback on skills, experience, projects, and clarity.",
            ],
            [
              "Job matching",
              "Compare your existing resume against a job description.",
            ],
            [
              "Grounded AI insights",
              "Semantic understanding backed by source-aware safeguards.",
            ],
            [
              "ATS guidance",
              "See missing requirements, evidence, and practical next steps.",
            ],
            [
              "Targeted improvements",
              "Review safe, job-specific bullet suggestions before accepting them.",
            ],
            [
              "Your workspace",
              "Return to saved analyses and job matches from your dashboard.",
            ],
          ].map(([title, copy]) => (
            <article
              key={title}
              className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
            >
              <div className="mb-4 h-9 w-9 rounded-lg bg-indigo-100" />
              <h2 className="font-semibold">{title}</h2>
              <p className="mt-2 text-sm leading-6 text-slate-600">{copy}</p>
            </article>
          ))}
        </div>
      </section>
      <section id="how-it-works" className="border-y border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-5 py-16">
          <p className="text-sm font-semibold text-indigo-700">HOW IT WORKS</p>
          <h2 className="mt-2 text-3xl font-bold">
            A simple, focused workflow
          </h2>
          <div className="mt-8 grid gap-6 md:grid-cols-3">
            {[
              [
                "1",
                "Upload your resume",
                "We extract and structure only the information in your PDF or DOCX.",
              ],
              [
                "2",
                "Add a target job",
                "Paste the job description you want to evaluate against.",
              ],
              [
                "3",
                "Review actionable results",
                "See ATS alignment, gaps, guidance, and safe improvement options.",
              ],
            ].map(([n, t, c]) => (
              <div key={n} className="rounded-xl bg-slate-50 p-5">
                <span className="text-sm font-bold text-indigo-600">{n}</span>
                <h3 className="mt-3 font-semibold">{t}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-600">{c}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
      <footer className="mx-auto flex max-w-6xl flex-col gap-3 px-5 py-10 text-sm text-slate-500 sm:flex-row sm:items-center sm:justify-between">
        <span>© {new Date().getFullYear()} Resume Analyzer</span>
        <span>
          Private workspace · Grounded guidance · User-controlled changes
        </span>
      </footer>
    </main>
  );
}
