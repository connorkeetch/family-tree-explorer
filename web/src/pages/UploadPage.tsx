import { useState, useRef, DragEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../api/client";
import type { ImportPreview } from "../api/types";
import ImportGuide from "../components/ImportGuide";
import { formatYear } from "../lib/year";

const RESULT_LIMIT = 40;

export default function UploadPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [root, setRoot] = useState("");
  const [query, setQuery] = useState("");
  const [working, setWorking] = useState<"preview" | "import" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const busy = working !== null;
  const selected = preview?.people.find((person) => person.id === root);
  const search = query.trim().toLocaleLowerCase();
  const matches = preview?.people.filter((person) =>
    `${person.name} ${person.year ?? ""} ${person.place ?? ""}`.toLocaleLowerCase().includes(search)) ?? [];
  const suggested = preview?.people.find((person) => person.id === preview.suggested_root);
  const results = !search && suggested
    ? [suggested, ...matches.filter((person) => person.id !== suggested.id)].slice(0, RESULT_LIMIT)
    : matches.slice(0, RESULT_LIMIT);

  function pick(list: FileList | null) {
    if (busy || !list?.length) return;
    setFiles(Array.from(list));
    setPreview(null);
    setRoot("");
    setQuery("");
    setError(null);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    if (!busy) pick(e.dataTransfer.files);
  }

  async function readFiles() {
    if (busy || !files.length) return;
    setWorking("preview");
    setError(null);
    try {
      setPreview(await api.preview(files));
      setRoot("");
      setQuery("");
    } catch (e) {
      setError(`Could not read your files. ${e instanceof Error ? e.message : String(e)} Choose a GEDCOM export and try again.`);
    } finally {
      setWorking(null);
    }
  }

  async function submit() {
    if (busy || !selected) return;
    setWorking("import");
    setError(null);
    try {
      const { id } = await api.upload(files, selected.id);
      navigate(`/tree/${id}`);
    } catch (e) {
      setError(`Could not import your tree. ${e instanceof Error ? e.message : String(e)} Try importing again, or choose a new export.`);
      setWorking(null);
    }
  }

  return (
    <div className="center">
      <p className="sub"><Link to="/">&larr; Your trees</Link></p>
      <h1>Import your tree</h1>
      <p className="sub">Choose a GEDCOM file, then confirm the person whose ancestors you want to explore.</p>

      <h2>1. Choose your file</h2>
      <div
        className={"drop" + (over && !busy ? " over" : "")}
        aria-busy={busy}
        onDragOver={(e) => { e.preventDefault(); if (!busy) setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".ged,.gedcom"
          multiple
          hidden
          disabled={busy}
          onChange={(e) => pick(e.target.files)}
        />
        {files.length ? (
          <div>
            <b>{files.length}</b> file{files.length === 1 ? "" : "s"} selected
            <div className="sub" style={{ marginTop: 6 }}>{files.map((f) => f.name).join(", ")}</div>
          </div>
        ) : <div>Drop a GEDCOM (<code>.ged</code>) file here</div>}
        <button type="button" onClick={() => inputRef.current?.click()} disabled={busy}
          style={{ marginTop: 12 }}>
          Choose GEDCOM files
        </button>
      </div>

      <details className="import-details">
        <summary>Combining multiple exports</summary>
        <p className="sub">
          Select several files together only to combine complementary exports. People with the same
          FamilySearch ID are merged; people without one stay separate. For a refresh, choose only the
          new full export so older files do not bring back removed people or relationships.
        </p>
      </details>

      {!preview && (
        <button type="button" className="btn btn-primary" onClick={readFiles} disabled={busy || !files.length}>
          {working === "preview" ? "Reading files…" : "Find starting person"}
        </button>
      )}

      {preview && (
        <section className="import-preview" aria-labelledby="starting-person-heading">
          <h2 id="starting-person-heading">2. Confirm your starting person</h2>
          <p className="sub">
            Found {preview.people.length.toLocaleString()} people.
            {preview.candidate_count > 1
              ? ` There are ${preview.candidate_count.toLocaleString()} possible starting points. Choose the person you mean below.`
              : " Select the person you want to start with below."}
          </p>
          <fieldset disabled={busy} className="import-choices">
            <legend>Starting person</legend>
            <div className="field">
              <label htmlFor="person-search">Search by name, birth year, or birthplace</label>
              <input id="person-search" type="search" value={query}
                onChange={(e) => setQuery(e.target.value)} placeholder="Search people in your file" />
            </div>
            <p className="sub" role="status">
              {matches.length > RESULT_LIMIT
                ? `Showing ${RESULT_LIMIT} of ${matches.length.toLocaleString()} matches. Search to narrow the list.`
                : `${matches.length.toLocaleString()} match${matches.length === 1 ? "" : "es"}`}
            </p>
            <div className="import-people">
              {results.map((person) => (
                <label className="import-person" key={person.id}>
                  <input type="radio" name="starting-person" value={person.id} checked={root === person.id}
                    onChange={() => setRoot(person.id)} />
                  <span>
                    <b>{person.name || "Unnamed person"}</b>
                    {person.year !== null && ` · born ${formatYear(person.year)}`}
                    {person.place && <span className="sub"> · {person.place}</span>}
                    {person.id === preview.suggested_root && <span className="sub"> · Suggested — please confirm</span>}
                  </span>
                </label>
              ))}
            </div>
            {!results.length && <p>No matching people. Try a shorter name or a birth year.</p>}
          </fieldset>
          <p role="status">
            {selected
              ? <>Starting with <b>{selected.name || "Unnamed person"}</b>{selected.year !== null && ` (born ${formatYear(selected.year)})`}.</>
              : "Choose a person to enable import."}
          </p>
          <button type="button" className="btn btn-primary" onClick={submit} disabled={busy || !selected}>
            {working === "import" ? "Importing tree…" : "Import tree"}
          </button>
        </section>
      )}

      {busy && (
        <div style={{ marginTop: 14 }}>
          <div className="progress-indeterminate" role="progressbar"
            aria-label={working === "preview" ? "Reading GEDCOM files" : "Importing tree"}><span /></div>
          <p className="sub" role="status">
            {working === "preview" ? "Reading the people in your files…" : "Preparing your tree. Large imports may take several minutes. Keep this tab open."}
          </p>
        </div>
      )}
      {error && <div className="err" role="alert">{error}</div>}
      <ImportGuide />
    </div>
  );
}
