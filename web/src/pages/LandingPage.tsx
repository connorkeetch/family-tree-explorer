import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import ConfirmDialog from "../components/ConfirmDialog";
import Skeleton from "../components/Skeleton";
import type { TreeSummary } from "../api/types";

function importedDate(tree: TreeSummary) {
  if (!tree.created_at) return "date unavailable";
  const value = tree.created_at;
  const date = new Date(/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? "date unavailable" :
    date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" });
}

export default function LandingPage() {
  const { user, logout } = useAuth();
  const [trees, setTrees] = useState<TreeSummary[] | null>(null);
  const [pendingDelete, setPendingDelete] = useState<TreeSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [exampleBusy, setExampleBusy] = useState(false);
  const [exampleError, setExampleError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const navigate = useNavigate();

  async function refresh() {
    setLoadError(null);
    setTrees(null);
    try {
      setTrees(await api.listTrees());
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Could not load your trees. Please try again.");
    }
  }
  useEffect(() => {
    refresh();
  }, []);

  async function confirmDelete() {
    if (!pendingDelete || deleting) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.deleteTree(pendingDelete.id);
      setPendingDelete(null);
      refresh();
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeleting(false);
    }
  }

  async function signOut() {
    await logout();
    navigate("/login");
  }

  async function tryExample() {
    if (exampleBusy) return;
    setExampleBusy(true);
    setExampleError(null);
    try {
      const response = await fetch("/example.ged");
      if (!response.ok) throw new Error("Could not load the example tree. Please try again.");
      const file = new File([await response.blob()], "example.ged", { type: "text/plain" });
      const { id } = await api.upload([file]);
      navigate(`/tree/${id}`);
    } catch (e) {
      setExampleError(e instanceof Error ? e.message : String(e));
    } finally {
      setExampleBusy(false);
    }
  }

  return (
    <div className="center">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h1>Your trees</h1>
        <span className="sub">
          {user?.email} ·{" "}
          <button className="linkbtn" onClick={signOut}>
            sign out
          </button>
        </span>
      </div>

      <div style={{ margin: "14px 0", display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Link className="btn btn-primary" to="/upload">
          Import my family tree →
        </Link>
        <button onClick={tryExample} disabled={exampleBusy}>
          {exampleBusy ? "Loading example…" : "Try an example tree"}
        </button>
      </div>
      <p className="sub">The example is a fictional family with made-up names and dates.</p>
      {exampleError && <div className="err" role="alert">{exampleError}</div>}

      {loadError ? (
        <div className="card err" role="alert">
          <p>{loadError}</p>
          <button onClick={refresh}>Retry</button>
        </div>
      ) : trees === null ? (
        <div className="card library-loading" role="status" aria-label="Loading your trees">
          {[0, 1, 2].map((i) => (
            <div className="row" key={i} style={{ justifyContent: "space-between" }}>
              <Skeleton w="55%" h={14} />
              <Skeleton w={120} h={24} r={7} />
            </div>
          ))}
        </div>
      ) : trees.length === 0 ? (
        <div className="card empty-state"><h2>No trees yet</h2><p className="sub">Start with the example, or import a GEDCOM file from your genealogy app.</p></div>
      ) : (
        <div className="tree-library">
          {trees.map((t) => (
            <article className="card tree-card" key={t.id}>
              <div className="tree-card-summary">
                <h2>{t.meta.root || "Unnamed tree"}</h2>
                <p className="sub">{Math.max(0, t.meta.n_direct - (t.meta.root_xref ? 1 : 0)).toLocaleString()} ancestors · {t.meta.max_gen} generations</p>
                <p className="sub tree-created">Imported {importedDate(t)}</p>
                {!!t.meta.source_files?.length && <p className="sub tree-file-list">Files: {t.meta.source_files.join(", ")}</p>}
              </div>
              <div className="tree-card-actions">
                <Link className="btn btn-primary" to={`/tree/${t.id}`} aria-label={`Open tree for ${t.meta.root || "unnamed tree"}, imported ${importedDate(t)}`}>
                  Open tree →
                </Link>
                <details>
                  <summary>More actions</summary>
                  <a className="btn" href={`/api/trees/${t.id}/export`}>Download analysis (JSON)</a>
                  <button aria-label={`Delete ${t.meta.root || "unnamed tree"}, imported ${importedDate(t)} (${t.id})`}
                    onClick={() => { setDeleteError(null); setPendingDelete(t); }}>
                    Delete tree
                  </button>
                </details>
              </div>
            </article>
          ))}
        </div>
      )}
      {trees && trees.length > 0 && (
        <p className="sub">Analysis downloads contain one tree. For a full backup of accounts and trees,
          follow the installation backup guide.</p>
      )}

      {pendingDelete && (
        <ConfirmDialog
          title="Delete this tree?"
          message={`“${pendingDelete.meta.root || "Unnamed tree"}”, imported ${importedDate(pendingDelete)}, and its analysis will be permanently removed. This can't be undone.`}
          confirmLabel={deleting ? "Deleting…" : "Delete tree"}
          danger
          error={deleteError}
          onConfirm={confirmDelete}
          onCancel={() => !deleting && setPendingDelete(null)}
        />
      )}
    </div>
  );
}
