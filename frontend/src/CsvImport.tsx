import { useEffect, useRef, useState } from "react";

type Preview = {
  token: string;
  filename: string;
  kind: string;
  row_count: number;
  duplicate_rows: number;
  errors: string[];
  period_start: string | null;
  period_end: string | null;
  columns: string[];
  sample: Record<string, string | number | null>[];
};
export default function CsvImport({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [preview, setPreview] = useState<Preview | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [mode, setMode] = useState("append"),
    [complete, setComplete] = useState("");
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  async function upload(file?: File) {
    if (!file) return;
    setBusy(true);
    setError("");
    setPreview(null);
    setComplete("");
    try {
      const r = await fetch(
        "/api/planning/imports/preview?filename=" +
          encodeURIComponent(file.name),
        { method: "POST", headers: { "Content-Type": "text/csv" }, body: file },
      );
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "CSV preview failed");
      setPreview(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "CSV preview failed");
    } finally {
      setBusy(false);
    }
  }
  async function apply() {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      const r = await fetch("/api/planning/imports/commit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: preview.token, mode }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "Import failed");
      setComplete(
        `${data.rows_imported.toLocaleString()} rows imported. ${data.duplicates_skipped} existing duplicates skipped.`,
      );
      onImported();
      setPreview(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }
  function template() {
    const content =
      "month,item,product,customer,industry,vendor,actual_units,revenue\n";
    const u = URL.createObjectURL(new Blob([content], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = u;
    a.download = "sales-import-template.csv";
    a.click();
    URL.revokeObjectURL(u);
  }
  return (
    <dialog
      ref={dialog}
      className="import-dialog"
      onCancel={(e) => {
        if (busy) e.preventDefault();
        else onClose();
      }}
      aria-labelledby="import-title"
    >
      <div className="section-heading">
        <div>
          <h2 id="import-title">Import your sales data</h2>
          <p>Preview the file and choose how to apply it.</p>
        </div>
        <button
          className="text-button"
          onClick={onClose}
          disabled={busy}
          aria-label="Close import"
        >
          ✕
        </button>
      </div>
      <div className="import-body">
        <p>
          Sales CSVs need <b>month, item, actual_units, revenue</b>. Product,
          customer, industry, and vendor are optional. Existing source column
          names such as item_code and quantity are also accepted.
        </p>
        <p>
          For vendor mapping only, use two columns: <b>item, vendor</b>.
          For inventory inputs, use <b>item, on_hand_units, lead_time_days</b>
          (either numeric column may be supplied).
        </p>
        <div className="upload-zone">
          <label htmlFor="csv-file">
            Choose CSV file <small>UTF-8 · up to 20 MB</small>
          </label>
          <input
            id="csv-file"
            type="file"
            accept=".csv,text/csv"
            disabled={busy}
            onChange={(e) => upload(e.target.files?.[0])}
          />
          <button className="text-button" onClick={template}>
            Download sales template
          </button>
        </div>
        {busy && <p role="status">Processing your file…</p>}
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {complete && (
          <div className="import-success" role="status">
            {complete}
          </div>
        )}
        {preview && (
          <>
            <div className="import-summary">
              <strong>{preview.filename}</strong>
              <span>
                {preview.row_count.toLocaleString()} rows ·{" "}
                {preview.duplicate_rows} repeated rows removed
              </span>
              <span>
                {preview.kind === "vendor_mapping"
                  ? "Item → vendor mapping"
                  : preview.kind === "inventory_mapping"
                    ? "Item → inventory inputs"
                  : `${preview.period_start} — ${preview.period_end}`}
              </span>
            </div>
            {preview.errors.map((e) => (
              <p className="error" key={e}>
                {e}
              </p>
            ))}
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    {preview.columns.map((c) => (
                      <th key={c}>{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.sample.map((r, i) => (
                    <tr key={i}>
                      {preview.columns.map((c) => (
                        <td key={c}>{r[c] ?? "—"}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {preview.kind === "sales" && (
              <fieldset>
                <legend>How should this file be used?</legend>
                <label>
                  <input
                    type="radio"
                    name="import-mode"
                    checked={mode === "append"}
                    onChange={() => setMode("append")}
                  />{" "}
                  Add to the active dataset
                </label>
                <p>
                  Overlapping periods add to sales totals. Only exact duplicate
                  rows are skipped.
                </p>
                <label>
                  <input
                    type="radio"
                    name="import-mode"
                    checked={mode === "replace"}
                    onChange={() => setMode("replace")}
                  />{" "}
                  Use this file as the active dataset
                </label>
                <p>
                  The original SQL tables and previous imports remain preserved.
                </p>
              </fieldset>
            )}
            <button
              className="primary"
              onClick={apply}
              disabled={busy || preview.errors.length > 0}
            >
              Confirm import
            </button>
          </>
        )}
      </div>
    </dialog>
  );
}
