const FS_APPS = "https://www.familysearch.org/en/innovate/solutions-gallery";

export default function ImportGuide() {
  return (
    <div className="card" style={{ marginTop: 20 }}>
      <h2 style={{ marginTop: 0 }}>How do I get my GEDCOM file?</h2>
      <p className="sub">
        Export your FamilySearch tree with a compatible genealogy app or a local tool,
        then upload the <code>.ged</code> file here. <b>This site never asks for or sees your FamilySearch password</b>{" "}
        — the export happens on your side, and you upload only the resulting file.
      </p>

      <h3>Using a genealogy app</h3>
      <p className="sub">FamilySearch's former direct GEDCOM export is no longer supported.</p>
      <ol className="sub" style={{ margin: 0, paddingLeft: 20, lineHeight: 1.8 }}>
        <li>
          Choose a compatible Family Tree Management app from{" "}
          <a href={FS_APPS} target="_blank" rel="noopener noreferrer">
            FamilySearch's Solutions Gallery
          </a>
          .
        </li>
        <li>
          Follow that app's instructions to import your FamilySearch ancestors,
          then export a GEDCOM (<code>.ged</code>) file.
        </li>
        <li>Drop that file in the box above.</li>
      </ol>

      <h3 style={{ marginTop: 18 }}>
        Local command-line option · getmyancestors
      </h3>
      <p className="sub" style={{ margin: "0 0 6px" }}>
        Needs Python 3. It prompts for your FamilySearch password (hidden) and runs entirely on your
        machine:
      </p>
      <pre className="code">
        <code>{`pip install getmyancestors
getmyancestors -u YOUR_FS_USERNAME -a 15 -o full.ged`}</code>
      </pre>
      <p className="sub" style={{ marginTop: 8 }}>
        Then upload <code>full.ged</code>. Increase <code>-a</code> for more generations.
        For a refresh, upload only the new full file; merging old exports keeps their
        deleted records and relationships. Select multiple files only when you intend
        to combine complementary pulls.
      </p>
    </div>
  );
}
