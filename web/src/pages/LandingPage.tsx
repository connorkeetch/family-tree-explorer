import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import ConfirmDialog from "../components/ConfirmDialog";
import Skeleton from "../components/Skeleton";
import type { TreeSummary } from "../api/types";

export default function LandingPage() {
  const { user, logout } = useAuth();
  const [trees, setTrees] = useState<TreeSummary[] | null>(null);
  const [pendingDelete, setPendingDelete] = useState<TreeSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [exampleBusy, setExampleBusy] = useState(false);
  const [exampleError, setExampleError] = useState<string | null>(null);
  const navigate = useNavigate();

  async function refresh() {
    try {
      setTrees(await api.listTrees());
    } catch {
      setTrees([]);
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

      {trees === null ? (
        <div className="card">
          {[0, 1, 2].map((i) => (
            <div className="row" key={i} style={{ justifyContent: "space-between" }}>
              <Skeleton w="55%" h={14} />
              <Skeleton w={120} h={24} r={7} />
            </div>
          ))}
        </div>
      ) : trees.length === 0 ? (
        <div className="card sub">Start with the example, or import a GEDCOM file from your genealogy app.</div>
      ) : (
        <div className="card">
          {trees.map((t) => (
            <div className="row" key={t.id} style={{ justifyContent: "space-between" }}>
              <Link to={`/tree/${t.id}`} style={{ flex: 1 }}>
                {t.meta.root || "(unnamed)"}{" "}
                <span className="cnt">
                  · {t.meta.n_direct.toLocaleString()} ancestors · gen {t.meta.max_gen}
                </span>
              </Link>
              <a
                className="btn"
                href={`/api/trees/${t.id}/export`}
                style={{ padding: "3px 8px", marginRight: 6 }}
              >
                Download analysis (JSON)
              </a>
              <button onClick={() => { setDeleteError(null); setPendingDelete(t); }} style={{ padding: "3px 8px" }}>
                Delete
              </button>
            </div>
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
          message={`“${pendingDelete.meta.root || "(unnamed)"}” and its analysis will be permanently removed. This can't be undone.`}
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
