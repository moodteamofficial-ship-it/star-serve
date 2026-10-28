import { jsPDF } from "jspdf";

const LOGO_SRC = `${import.meta.env.BASE_URL}star-serve-logo.png?v=3`;
const LOGO_ASPECT = 249 / 1024;

const GREEN: [number, number, number] = [48, 168, 44];
const GREEN_DEEP: [number, number, number] = [36, 130, 32];
const GREEN_SOFT: [number, number, number] = [231, 246, 230];
const RED: [number, number, number] = [237, 28, 36];
const INK: [number, number, number] = [23, 30, 38];
const INK_SOFT: [number, number, number] = [98, 108, 120];
const RULE: [number, number, number] = [226, 230, 234];

export type QuoteSummaryPdfInput = {
  clientName?: string;
  clientPhone?: string;
  clientEmail?: string;
  cover: string;
  period: string;
  sumInsured: string;
  vehicle: string;
  registration: string;
  policyNumber: string;
  premium?: {
    basic: string;
    phcf: string;
    trainingLevy: string;
    stampDuty: string;
    gross: string;
    referralCost?: string;
  };
  amountDue: string;
  providerNote: string;
};

/** Keeps the Helvetica fallback safe: standard PDF fonts are Latin-1 only. */
function pdfText(value: string | undefined | null): string {
  const text = (value ?? "").replace(/[\u2013\u2014]/g, "-").replace(/[\u2018\u2019]/g, "'").trim();
  return text || "-";
}

const FONT_FILES = {
  normal: `${import.meta.env.BASE_URL}fonts/Poppins-Regular.ttf`,
  bold: `${import.meta.env.BASE_URL}fonts/Poppins-SemiBold.ttf`,
} as const;

let fontCache: Promise<Record<keyof typeof FONT_FILES, string> | null> | null = null;

function toBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

/** SPA fallbacks answer unknown paths with index.html (200), which jsPDF can't parse. */
function isTrueType(buffer: ArrayBuffer): boolean {
  if (buffer.byteLength < 12) return false;
  const tag = new DataView(buffer).getUint32(0);
  return tag === 0x00010000 || tag === 0x74727565; // 1.0 or "true"
}

function loadPoppins(): Promise<Record<keyof typeof FONT_FILES, string> | null> {
  if (!fontCache) {
    fontCache = (async () => {
      try {
        const entries = await Promise.all(
          (Object.keys(FONT_FILES) as Array<keyof typeof FONT_FILES>).map(async (style) => {
            const response = await fetch(FONT_FILES[style], { credentials: "same-origin" });
            if (!response.ok) throw new Error(`Font HTTP ${response.status}`);
            const buffer = await response.arrayBuffer();
            if (!isTrueType(buffer)) throw new Error("Font file is not TrueType");
            return [style, toBase64(buffer)] as const;
          }),
        );
        return Object.fromEntries(entries) as Record<keyof typeof FONT_FILES, string>;
      } catch {
        fontCache = null;
        return null;
      }
    })();
  }
  return fontCache;
}

/** Downscaled so the embedded logo stays sharp in print without a 1 MB file. */
async function loadLogoDataUrl(): Promise<string | null> {
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const el = new Image();
      el.onload = () => resolve(el);
      el.onerror = () => reject(new Error("logo"));
      el.src = LOGO_SRC;
    });
    const width = 900;
    const height = Math.round(width * LOGO_ASPECT);
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(img, 0, 0, width, height);
    return canvas.toDataURL("image/jpeg", 0.92);
  } catch {
    return null;
  }
}

export async function downloadQuoteSummaryPdf(input: QuoteSummaryPdfInput): Promise<void> {
  const { doc, fileName } = await buildQuoteSummaryPdf(input);
  doc.save(fileName);
}

export async function buildQuoteSummaryPdf(
  input: QuoteSummaryPdfInput,
): Promise<{ doc: jsPDF; fileName: string }> {
  const doc = new jsPDF({ unit: "mm", format: "a4", compress: true });
  const poppins = await loadPoppins();
  let family = "helvetica";
  if (poppins) {
    try {
      doc.addFileToVFS("Poppins-Regular.ttf", poppins.normal);
      doc.addFont("Poppins-Regular.ttf", "Poppins", "normal");
      doc.addFileToVFS("Poppins-SemiBold.ttf", poppins.bold);
      doc.addFont("Poppins-SemiBold.ttf", "Poppins", "bold");
      doc.setFont("Poppins", "bold");
      doc.getTextWidth("Star Serve");
      doc.setFont("Poppins", "normal");
      doc.getTextWidth("Star Serve");
      family = "Poppins";
    } catch {
      family = "helvetica";
    }
  }
  doc.setFont(family, "normal");
  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();
  const margin = 18;
  const contentW = pageW - margin * 2;
  let y = margin;

  const generatedAt = new Date();
  const dateLabel = generatedAt.toLocaleString("en-KE", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  // Header: logo left, document title right.
  const logo = await loadLogoDataUrl();
  const logoW = 52;
  const logoH = logoW * LOGO_ASPECT;
  if (logo) {
    doc.addImage(logo, "JPEG", margin, y, logoW, logoH);
  } else {
    doc.setFont(family, "bold");
    doc.setFontSize(20);
    doc.setTextColor(...GREEN);
    doc.text("Star Serve", margin, y + 9);
  }

  doc.setFont(family, "bold");
  doc.setFontSize(16);
  doc.setTextColor(...INK);
  doc.text("Quote Summary", pageW - margin, y + 5, { align: "right" });
  doc.setFont(family, "normal");
  doc.setFontSize(9);
  doc.setTextColor(...INK_SOFT);
  doc.text("Star Serve Insurance Agency", pageW - margin, y + 10.5, { align: "right" });
  doc.text(dateLabel, pageW - margin, y + 15, { align: "right" });

  y += Math.max(logoH, 16) + 5;
  doc.setFillColor(...GREEN);
  doc.rect(margin, y, contentW, 1.4, "F");
  doc.setFillColor(...RED);
  doc.rect(margin + contentW - 18, y, 18, 1.4, "F");
  y += 9;

  function sectionTitle(label: string) {
    doc.setFont(family, "bold");
    doc.setFontSize(10.5);
    doc.setTextColor(...GREEN_DEEP);
    doc.text(label.toUpperCase(), margin, y);
    y += 2.5;
    doc.setDrawColor(...RULE);
    doc.setLineWidth(0.3);
    doc.line(margin, y, pageW - margin, y);
    y += 6;
  }

  function fieldGrid(fields: Array<[string, string]>) {
    const colW = contentW / 2;
    const rowH = 13;
    fields.forEach(([label, value], index) => {
      const col = index % 2;
      const x = margin + col * colW;
      const rowY = y + Math.floor(index / 2) * rowH;
      doc.setFont(family, "normal");
      doc.setFontSize(8);
      doc.setTextColor(...INK_SOFT);
      doc.text(label.toUpperCase(), x, rowY);
      doc.setFont(family, "bold");
      doc.setFontSize(11);
      doc.setTextColor(...INK);
      const lines = doc.splitTextToSize(pdfText(value), colW - 6) as string[];
      doc.text(lines[0] ?? "-", x, rowY + 5.5);
    });
    y += Math.ceil(fields.length / 2) * rowH + 2;
  }

  const clientFields: Array<[string, string]> = [];
  if (input.clientName) clientFields.push(["Client", input.clientName]);
  if (input.clientPhone) clientFields.push(["Phone", input.clientPhone]);
  if (input.clientEmail) clientFields.push(["Email", input.clientEmail]);
  if (clientFields.length) {
    sectionTitle("Client");
    fieldGrid(clientFields);
  }

  sectionTitle("Cover details");
  fieldGrid([
    ["Cover", input.cover],
    ["Period", input.period],
    ["Sum insured", input.sumInsured],
    ["Vehicle", input.vehicle],
    ["Registration", input.registration],
    ["Policy", input.policyNumber],
  ]);

  if (input.premium) {
    sectionTitle("Premium (KES)");
    const rows: Array<[string, string]> = [
      ["Basic", input.premium.basic],
      ["PHCF", input.premium.phcf],
      ["Training levy", input.premium.trainingLevy],
      ["Stamp duty", input.premium.stampDuty],
    ];
    doc.setFontSize(10.5);
    rows.forEach(([label, value]) => {
      doc.setFont(family, "normal");
      doc.setTextColor(...INK_SOFT);
      doc.text(label, margin + 3, y);
      doc.setFont(family, "bold");
      doc.setTextColor(...INK);
      doc.text(pdfText(value), pageW - margin - 3, y, { align: "right" });
      y += 3;
      doc.setDrawColor(...RULE);
      doc.line(margin, y, pageW - margin, y);
      y += 5;
    });
    doc.setFillColor(...GREEN_SOFT);
    doc.roundedRect(margin, y - 5, contentW, 10, 1.5, 1.5, "F");
    doc.setFont(family, "bold");
    doc.setFontSize(11);
    doc.setTextColor(...GREEN_DEEP);
    doc.text("Gross premium", margin + 3, y + 1.3);
    doc.text(pdfText(input.premium.gross), pageW - margin - 3, y + 1.3, { align: "right" });
    y += 14;
    if (input.premium.referralCost) {
      doc.setFont(family, "normal");
      doc.setFontSize(10.5);
      doc.setTextColor(...INK_SOFT);
      doc.text("Referral cost", margin + 3, y);
      doc.setFont(family, "bold");
      doc.setTextColor(...INK);
      doc.text(pdfText(input.premium.referralCost), pageW - margin - 3, y, { align: "right" });
      y += 8;
    }
  }

  // Amount due banner.
  const bannerH = 22;
  doc.setFillColor(...GREEN);
  doc.roundedRect(margin, y, contentW, bannerH, 2.5, 2.5, "F");
  doc.setTextColor(255, 255, 255);
  doc.setFont(family, "normal");
  doc.setFontSize(9);
  doc.text("AMOUNT DUE", margin + 6, y + 8);
  doc.setFont(family, "bold");
  doc.setFontSize(20);
  doc.text(`KES ${pdfText(input.amountDue)}`, margin + 6, y + 17);
  doc.setFont(family, "normal");
  doc.setFontSize(8.5);
  doc.text("Provider note", pageW - margin - 6, y + 8, { align: "right" });
  doc.setFont(family, "bold");
  doc.setFontSize(11);
  doc.text(pdfText(input.providerNote), pageW - margin - 6, y + 15, { align: "right" });
  y += bannerH + 10;

  doc.setFont(family, "normal");
  doc.setFontSize(8.5);
  doc.setTextColor(...INK_SOFT);
  const disclaimer = doc.splitTextToSize(
    "This is a quote summary, not a certificate of insurance. Cover starts once payment is " +
      "confirmed and the certificate has been issued. Figures are as quoted by the insurer at the " +
      "time shown above and may change if details are updated.",
    contentW,
  ) as string[];
  doc.text(disclaimer, margin, y);

  // Footer.
  const footerY = pageH - 12;
  doc.setDrawColor(...RULE);
  doc.line(margin, footerY - 5, pageW - margin, footerY - 5);
  doc.setFontSize(8);
  doc.setTextColor(...INK_SOFT);
  doc.text("Star Serve Insurance Agency", margin, footerY);
  doc.setTextColor(...GREEN_DEEP);
  doc.text("quote.starserveinsuranceagency.com", pageW - margin, footerY, { align: "right" });

  const safePolicy = pdfText(input.policyNumber).replace(/[^A-Za-z0-9-]+/g, "");
  return { doc, fileName: `StarServe-Quote-${safePolicy || generatedAt.getTime()}.pdf` };
}
