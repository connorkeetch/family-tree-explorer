const FS_APPS = "https://www.familysearch.org/en/innovate/solutions-gallery";

export default function ImportGuide() {
  return (
    <div className="card" style={{ marginTop: 20 }}>
      <h2 style={{ marginTop: 0 }}>How do I get a GEDCOM file?</h2>
      <p className="sub">
        In your genealogy app or family-history website, look for <b>Export</b> or <b>Download tree</b>,
        then choose GEDCOM (<code>.ged</code>). Include the starting person and their ancestors.
        Upload the exported file here. You can use files from different genealogy services.
      </p>
      <p className="sub">
        Want to try it first? <a href="/example.ged" download>Download a fictional example GEDCOM</a>.
      </p>

      <details className="import-details">
        <summary>Exporting from FamilySearch</summary>
        <p className="sub">
          Use a compatible genealogy app from{" "}
          <a href={FS_APPS} target="_blank" rel="noopener noreferrer">FamilySearch's Solutions Gallery</a>.
          Follow the app's instructions to bring in your ancestors, then export a GEDCOM file.
          <b> This site never asks for your FamilySearch password.</b> You export on your side and upload the file.
        </p>
      </details>

      <details className="import-details">
        <summary>Advanced: export with a local command-line tool</summary>
        <p className="sub">
          With Python 3 installed, getmyancestors can export your FamilySearch ancestors.
          It runs on your computer and prompts for your FamilySearch password there:
        </p>
        <pre className="code"><code>{`pip install getmyancestors
getmyancestors -u YOUR_FS_USERNAME -a 15 -o full.ged`}</code></pre>
        <p className="sub">
          Upload <code>full.ged</code>. Increase <code>-a</code> for more generations.
          For a refresh, upload only the new full export.
        </p>
      </details>
    </div>
  );
}
