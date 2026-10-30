import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { configured, supabase } from "./supabase";
import Inbox from "./pages/Inbox";
import Agencies from "./pages/Agencies";
import PostingPage from "./pages/Posting";
import Keywords from "./pages/Keywords";
import Search from "./pages/Search";
import Settings from "./pages/Settings";
import Login from "./pages/Login";

// Hash routes (#/posting/12) so the site works on GitHub Pages without server rewrites.
function useRoute(): string[] {
  const read = () => window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const on = () => setRoute(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

const NAV = [
  ["", "Inbox"],
  ["agencies", "Agencies"],
  ["search", "Search"],
  ["keywords", "Keywords"],
  ["settings", "Settings"],
] as const;

export default function App() {
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const route = useRoute();

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => data.subscription.unsubscribe();
  }, []);

  if (!configured) {
    return (
      <main className="narrow">
        <h1>Agency Tracker</h1>
        <p className="error">
          Not configured: set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY (see web/.env.example).
        </p>
      </main>
    );
  }
  if (session === undefined) return null;
  if (!session) return <Login />;

  const [page, arg] = route;
  let body;
  switch (page ?? "") {
    case "agencies": body = <Agencies />; break;
    case "posting": body = <PostingPage id={Number(arg)} userId={session.user.id} />; break;
    case "keywords": body = <Keywords />; break;
    case "search": body = <Search />; break;
    case "settings": body = <Settings userId={session.user.id} />; break;
    default: body = <Inbox agencyFilter={page === "agency" ? arg : undefined} />;
  }

  return (
    <>
      <header className="topbar">
        <a href="#/" className="brand">CA Education Agency Tracker</a>
        <nav>
          {NAV.map(([path, label]) => (
            <a key={path} href={`#/${path}`}
               className={(page ?? "") === path || (path === "" && page === "agency") ? "active" : ""}>
              {label}
            </a>
          ))}
        </nav>
        <button className="link" onClick={() => supabase.auth.signOut()}>
          Sign out
        </button>
      </header>
      <main>{body}</main>
    </>
  );
}
