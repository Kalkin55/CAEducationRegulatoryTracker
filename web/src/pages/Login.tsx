import { useState } from "react";
import { supabase } from "../supabase";

export default function Login() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setState("sending");
    setError(null);
    const { error } = await supabase.auth.signInWithOtp({
      email,
      // Invite-only: don't create accounts for unknown addresses.
      options: { shouldCreateUser: false, emailRedirectTo: window.location.href.split("#")[0] },
    });
    if (error) {
      setError(error.message);
      setState("idle");
    } else {
      setState("sent");
    }
  }

  return (
    <main className="narrow">
      <h1>CA Education Agency Tracker</h1>
      {state === "sent" ? (
        <p>Check {email} for a sign-in link.</p>
      ) : (
        <form onSubmit={submit} className="stack">
          <label>
            Work email
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <button disabled={state === "sending"}>Email me a sign-in link</button>
          {error && <p className="error">{error}</p>}
          <p className="muted">Only invited team members can sign in.</p>
        </form>
      )}
    </main>
  );
}
