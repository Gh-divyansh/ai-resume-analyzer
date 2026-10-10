"use client";

import { useMemo, useState } from "react";

type PasswordFieldProps = {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: "current-password" | "new-password";
  showStrength?: boolean;
  error?: string;
};

function strength(password: string) {
  const score = [password.length >= 8, /[a-z]/.test(password), /[A-Z]/.test(password), /\d/.test(password), /[^A-Za-z0-9]/.test(password)].filter(Boolean).length;
  if (!password) return { label: "", color: "bg-slate-200", width: "w-0" };
  if (score <= 2) return { label: "Weak", color: "bg-rose-500", width: "w-1/3" };
  if (score <= 3) return { label: "Fair", color: "bg-amber-500", width: "w-2/3" };
  return { label: "Strong", color: "bg-emerald-500", width: "w-full" };
}

export function PasswordField({ id, label, value, onChange, autoComplete, showStrength = false, error }: PasswordFieldProps) {
  const [visible, setVisible] = useState(false);
  const meter = useMemo(() => strength(value), [value]);

  return (
    <div className="space-y-2">
      <label htmlFor={id} className="text-sm font-medium text-slate-700">{label}</label>
      <div className="relative">
        <input id={id} value={value} onChange={(event) => onChange(event.target.value)} type={visible ? "text" : "password"} autoComplete={autoComplete} minLength={8} required aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-error` : showStrength ? `${id}-requirements` : undefined} className="w-full rounded-xl border border-slate-300 bg-white px-3 py-3 pr-16 text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100" />
        <button type="button" onClick={() => setVisible((current) => !current)} className="absolute inset-y-0 right-2 px-2 text-sm font-medium text-indigo-700 hover:text-indigo-900" aria-label={visible ? "Hide password" : "Show password"}>{visible ? "Hide" : "Show"}</button>
      </div>
      {showStrength && <div id={`${id}-requirements`} className="space-y-1" aria-live="polite"><div className="h-1.5 overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full transition-all ${meter.color} ${meter.width}`} /></div><p className="text-xs text-slate-500">Use at least 8 characters, with a mix of letters, numbers, or symbols. {meter.label && `Strength: ${meter.label}.`}</p></div>}
      {error && <p id={`${id}-error`} className="text-xs text-rose-700">{error}</p>}
    </div>
  );
}
