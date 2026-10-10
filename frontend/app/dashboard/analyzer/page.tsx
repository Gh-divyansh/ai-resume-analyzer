import { Analyzer } from "@/app/page";
import { AuthGate } from "@/components/auth-gate";

// The analyzer is intentionally public for the server-enforced anonymous free tier.
export default function AnalyzerPage(){return <AuthGate requireAuth={false}><Analyzer /></AuthGate>}
