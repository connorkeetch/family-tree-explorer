import { useState, useRef, DragEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../api/client";
import ImportGuide from "../components/ImportGuide";

export default function UploadPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [root, setRoot] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  function pick(list: FileList | null) {
    if (!list) return;
    setFiles(Array.from(list));
    setError(null);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    pick(e.dataTransfer.files);
  }

  async function submit() {
    if (!files.length) {
      setError("Choose at least one .ged file first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { id } = await api.upload(files, root.trim() || undefined);
      navigate(`/tree/${id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div className="center">
      <p className="sub">
        <Link to="/">&larr; Home</Link>
      </p>
      <p className="sub">
        Learning how imports work? <a href="/example.ged" download>Download the fictional example GEDCOM</a>.
      </p>
      <h1>Upload your tree</h1>
      <p className="sub">
        One or more GEDCOM (<code>.ged</code>) files. Multiple files are merged by
        FamilySearch ID. When refreshing a tree, upload the new full export alone
        so removed relationships are not brought back from older files.
      </p>

      <div
        className={"drop" + (over ? " over" : "")}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".ged,.gedcom"
          multiple
          hidden
          onChange={(e) => pick(e.target.files)}
        />
        {files.length ? (
          <div>
            <b>{files.length}</b> file{files.length === 1 ? "" : "s"} selected
            <div className="sub" style={{ marginTop: 6 }}>
              {files.map((f) => f.name).join(", ")}
            </div>
          </div>
        ) : (
          <div>
            <div style={{ fontSize: 16 }}>Drop a .ged file here</div>
            <div className="sub" style={{ marginTop: 6 }}>or choose a file below</div>
          </div>
        )}
        <button type="button" onClick={() => inputRef.current?.click()} disabled={busy}
          style={{ marginTop: 12 }}>
          Choose GEDCOM files
        </button>
      </div>

      <div className="field" style={{ marginTop: 16 }}>
        <label htmlFor="root-person">Root person FamilySearch ID (optional &mdash; auto-detected if blank)</label>
        <input
          id="root-person"
          type="text"
          placeholder="e.g. ABCD-123"
          value={root}
          onChange={(e) => setRoot(e.target.value)}
        />
      </div>

      <div style={{ marginTop: 16 }}>
        <button className="btn btn-primary" onClick={submit} disabled={busy}>
          {busy ? "Analyzing…" : "Analyze →"}
        </button>
      </div>

      {busy && (
        <div style={{ marginTop: 14 }}>
          <div className="progress-indeterminate" role="progressbar" aria-label="Analyzing upload">
            <span />
          </div>
          <div className="sub" style={{ marginTop: 6 }}>
            Parsing and analyzing your tree — large files and optional AI analysis
            can take several minutes. Don’t close this tab.
          </div>
        </div>
      )}

      {error && <div className="err">{error}</div>}

      <ImportGuide />
    </div>
  );
}
