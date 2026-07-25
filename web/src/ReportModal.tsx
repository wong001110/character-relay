import { useEffect, useMemo, useState } from "react";

import { api, type ReportFormat } from "./api";
import { useI18n } from "./i18n";
import { formatReportContent, reportFilename } from "./report";

interface Props {
  runId: string;
  format: ReportFormat;
  onClose: () => void;
}

export function ReportModal({ runId, format, onClose }: Props) {
  const { t } = useI18n();
  const [rawContent, setRawContent] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const content = useMemo(
    () => formatReportContent(rawContent, format),
    [rawContent, format]
  );
  const title = format === "markdown" ? t("report.labNote") : t("report.json");

  useEffect(() => {
    let active = true;
    api.getReport(runId, format)
      .then((next) => { if (active) setRawContent(next); })
      .catch((reason: Error) => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, [runId, format]);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  async function copy() {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  function download() {
    const type = format === "json" ? "application/json" : "text/markdown";
    const url = URL.createObjectURL(new Blob([content], { type }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = reportFilename(runId, format);
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="report-sheet paper-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="report-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button className="close-button" onClick={onClose} aria-label={t("creator.cancel")}>×</button>
        <div className="report-heading">
          <div>
            <p className={format === "markdown" ? "tape-label" : "tape-label rose"}>
              {t("report.archive")}
            </p>
            <h2 id="report-title">{title}</h2>
          </div>
          <div className="modal-toolbar">
            <button className="paper-button" onClick={() => void copy()} disabled={!content}>
              {copied ? t("report.copied") : t("report.copy")}
            </button>
            <button className="paper-button" onClick={download} disabled={!content}>
              {t("report.download")}
            </button>
          </div>
        </div>
        {error ? (
          <p className="error-note">{error}</p>
        ) : content ? (
          <pre className={`report-content ${format}`}>{content}</pre>
        ) : (
          <div className="report-loading">{t("report.opening")}</div>
        )}
      </section>
    </div>
  );
}
