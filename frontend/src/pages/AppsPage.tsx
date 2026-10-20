import { useEffect, useState } from "react";
import { api, errorMessage, type MyApplication } from "../api";
import { useAuth } from "../auth";
import Icon from "../components/Icon";
import { Alert, Avatar, Badge, EmptyState, PageHeader, Spinner } from "../components/ui";

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export default function AppsPage() {
  const { user } = useAuth();
  const [apps, setApps] = useState<MyApplication[] | null>(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");

  useEffect(() => {
    api.get<MyApplication[]>("/api/me/applications").then(setApps).catch((e) => setError(errorMessage(e)));
  }, []);

  // The whole name: Myanmar names have no separate first name.
  const firstName = user?.full_name || user?.username || "";
  const shown = apps?.filter((a) => `${a.name} ${a.description}`.toLowerCase().includes(q.toLowerCase())) ?? [];

  return (
    <>
      <PageHeader
        title={`${greeting()}, ${firstName}`}
        subtitle="Your systems. You're signed in to all of them, so there's no need to enter your password again."
      />
      <Alert>{error}</Alert>
      {!apps && !error && <Spinner />}

      {apps && apps.length > 6 && (
        <div className="search-box wide">
          <Icon name="search" />
          <input placeholder="Find a system…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      )}

      {apps && apps.length === 0 && (
        <div className="card">
          <EmptyState icon="lock" title="No systems yet">
            You don't have access to any systems. Ask your administrator to assign you a role.
          </EmptyState>
        </div>
      )}

      <div className="app-grid">
        {shown.map((app) => {
          const body = (
            <>
              <div className="app-card-top">
                <Avatar name={app.name} size={44} square />
                {app.home_url && <Icon name="external" className="app-card-arrow" />}
              </div>
              <h3>{app.name}</h3>
              <p className="muted">{app.description || "No description"}</p>
              <div className="chips">
                {app.roles.map((r) => <Badge key={r} tone="blue">{r}</Badge>)}
              </div>
            </>
          );
          return app.home_url ? (
            <a key={app.id} className="card app-card clickable" href={app.home_url}>{body}</a>
          ) : (
            <div key={app.id} className="card app-card" title="No launch URL configured">{body}</div>
          );
        })}
      </div>
    </>
  );
}
