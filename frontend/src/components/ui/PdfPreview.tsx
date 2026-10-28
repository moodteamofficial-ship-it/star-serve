import { useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

let workerReady: Promise<void> | null = null;

/**
 * Serve the pdf.js worker as a blob: URL with an explicit JS MIME type.
 * Cloud/nginx mis-labelled .mjs as octet-stream + nosniff blocks module workers.
 */
function ensurePdfWorker(): Promise<void> {
  if (!workerReady) {
    workerReady = (async () => {
      try {
        const response = await fetch(pdfWorkerUrl, { credentials: "same-origin" });
        if (!response.ok) throw new Error(`PDF worker HTTP ${response.status}`);
        const buffer = await response.arrayBuffer();
        const blob = new Blob([buffer], { type: "text/javascript" });
        pdfjs.GlobalWorkerOptions.workerSrc = URL.createObjectURL(blob);
      } catch {
        // Same-origin path still works when the host sends the correct MIME type.
        pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;
      }
    })();
  }
  return workerReady;
}

function looksLikePdf(bytes: Uint8Array): boolean {
  return (
    bytes.length >= 5 &&
    bytes[0] === 0x25 && // %
    bytes[1] === 0x50 && // P
    bytes[2] === 0x44 && // D
    bytes[3] === 0x46 // F
  );
}

/**
 * Prefer in-memory Blob/bytes. Never ``fetch(blob:)`` — CSP connect-src on Cloud Run
 * blocks that with "Failed to fetch" even when the same Blob downloads fine via <a>.
 */
async function toPdfBytes(
  data: Blob | ArrayBuffer | Uint8Array,
): Promise<Uint8Array> {
  let bytes: Uint8Array;
  if (data instanceof Uint8Array) {
    bytes = data;
  } else if (data instanceof ArrayBuffer) {
    bytes = new Uint8Array(data);
  } else {
    bytes = new Uint8Array(await data.arrayBuffer());
  }
  if (!looksLikePdf(bytes)) {
    throw new Error("The downloaded file is not a valid PDF. Try Download instead.");
  }
  // pdf.js detaches the buffer in some builds — copy so the Blob stays usable.
  return bytes.slice();
}

type PdfPreviewProps = {
  data: Blob | ArrayBuffer | Uint8Array;
};

type PdfBounds = {
  maxWidth: number;
  maxHeight: number;
};

function measurePdfBounds(container: HTMLElement): PdfBounds {
  const scroll = container.closest(".cert-pdf-preview-scroll");
  const panel = scroll?.closest(".modal-panel");

  if (!scroll || !panel) {
    return {
      maxWidth: Math.max(window.innerWidth - 48, 280),
      maxHeight: Math.max(window.innerHeight - 180, 240),
    };
  }

  const header = panel.querySelector(".modal-header");
  const footer = panel.querySelector(".modal-footer");
  const scrollStyle = getComputedStyle(scroll);
  const padX =
    parseFloat(scrollStyle.paddingLeft) + parseFloat(scrollStyle.paddingRight);
  const padY =
    parseFloat(scrollStyle.paddingTop) + parseFloat(scrollStyle.paddingBottom);
  const headerH = header?.getBoundingClientRect().height ?? 72;
  const footerH = footer?.getBoundingClientRect().height ?? 72;
  const rootPad = 24;

  const maxPanelW = window.innerWidth - rootPad;
  const maxPanelH = window.innerHeight - rootPad;

  return {
    maxWidth: Math.max(maxPanelW - padX - 2, 280),
    maxHeight: Math.max(maxPanelH - headerH - footerH - padY - 6, 240),
  };
}

function computePageFitScale(
  pageWidth: number,
  pageHeight: number,
  bounds: PdfBounds,
) {
  const widthScale = bounds.maxWidth / pageWidth;
  const heightScale = bounds.maxHeight / pageHeight;
  const scale = Math.min(widthScale, heightScale);

  return Math.min(Math.max(scale, 0.55), 2.75);
}

async function waitForLayout() {
  await new Promise<void>((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
  });
}

async function renderPage(
  page: PDFPageProxy,
  host: HTMLElement,
  displayScale: number,
  pageNum: number,
) {
  const base = page.getViewport({ scale: 1 });
  const pixelRatio = Math.min(window.devicePixelRatio || 1, 3);
  const renderScale = displayScale * pixelRatio;
  const viewport = page.getViewport({ scale: renderScale });

  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d", { alpha: false });
  if (!context) return;

  const cssWidth = Math.floor(base.width * displayScale);
  const cssHeight = Math.floor(base.height * displayScale);

  canvas.width = Math.floor(viewport.width);
  canvas.height = Math.floor(viewport.height);
  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${cssHeight}px`;
  canvas.className = "cert-pdf-page";
  canvas.setAttribute("aria-label", `Page ${pageNum}`);

  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";

  await page.render({ canvasContext: context, viewport }).promise;
  host.appendChild(canvas);
}

export function PdfPreview({ data }: PdfPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    const container = containerRef.current;
    if (!container) return;

    container.replaceChildren();
    setStatus("loading");
    setErrorMessage("");

    async function renderPdf() {
      try {
        await ensurePdfWorker();
        await waitForLayout();
        if (cancelled || !containerRef.current) return;

        const bytes = await toPdfBytes(data);
        if (cancelled || !containerRef.current) return;

        const loadingTask = pdfjs.getDocument({ data: bytes });
        const pdf: PDFDocumentProxy = await loadingTask.promise;
        if (cancelled || !containerRef.current) return;

        const host = containerRef.current;
        const firstPage = await pdf.getPage(1);
        if (cancelled) return;

        const firstViewport = firstPage.getViewport({ scale: 1 });
        const bounds = measurePdfBounds(host);
        const displayScale = computePageFitScale(
          firstViewport.width,
          firstViewport.height,
          bounds,
        );

        for (let pageNum = 1; pageNum <= pdf.numPages; pageNum += 1) {
          const page = pageNum === 1 ? firstPage : await pdf.getPage(pageNum);
          if (cancelled) return;
          await renderPage(page, host, displayScale, pageNum);
          if (pageNum === 1 && !cancelled) setStatus("ready");
        }
      } catch (err) {
        if (cancelled) return;
        setStatus("error");
        setErrorMessage(
          err instanceof Error ? err.message : "Could not render the preview.",
        );
      }
    }

    void renderPdf();

    return () => {
      cancelled = true;
      container.replaceChildren();
    };
  }, [data]);

  return (
    <div className="cert-pdf-preview-scroll">
      {status === "loading" ? (
        <div className="cert-pdf-sheet" role="status" aria-live="polite">
          <div className="cert-pdf-sheet-art" aria-hidden="true">
            <span className="cert-pdf-sheet-bar" />
            <span className="cert-pdf-sheet-line cert-pdf-sheet-line--lg" />
            <span className="cert-pdf-sheet-line" />
            <span className="cert-pdf-sheet-line cert-pdf-sheet-line--md" />
            <span className="cert-pdf-sheet-rule" />
            <span className="cert-pdf-sheet-line" />
            <span className="cert-pdf-sheet-line cert-pdf-sheet-line--sm" />
            <span className="cert-pdf-sheet-line cert-pdf-sheet-line--md" />
          </div>
          <div className="cert-pdf-sheet-caption">
            <span className="cert-pdf-sheet-spinner" aria-hidden="true" />
            <div>
              <strong>Preparing preview</strong>
              <span>Rendering the certificate…</span>
            </div>
          </div>
        </div>
      ) : null}
      {status === "error" ? (
        <div className="cert-pdf-sheet cert-pdf-sheet--error" role="alert">
          <div className="cert-pdf-sheet-caption">
            <div>
              <strong>Preview unavailable</strong>
              <span>
                {errorMessage || "The document could not be rendered. Download the PDF instead."}
              </span>
            </div>
          </div>
        </div>
      ) : null}
      <div
        ref={containerRef}
        className="cert-pdf-pages"
        data-ready={status === "ready" ? "true" : undefined}
      />
    </div>
  );
}
