import QRCode from "qrcode";

const LOGO_SRC = `${import.meta.env.BASE_URL}star-serve-logo.png?v=3`;
/** Export multiplier — keeps logo + Poppins crisp when downloaded / printed. */
const EXPORT_SCALE = 3;

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.decoding = "async";
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Failed to load ${src}`));
    img.src = src;
  });
}

async function ensurePoppinsReady(): Promise<void> {
  if (typeof document === "undefined" || !document.fonts?.load) return;
  try {
    await document.fonts.ready;
    await Promise.all([
      document.fonts.load("600 28px Poppins"),
      document.fonts.load("700 22px Poppins"),
    ]);
  } catch {
    /* fall back to whatever is available */
  }
}

function truncateLabel(text: string, max: number): string {
  const trimmed = text.trim();
  if (trimmed.length <= max) return trimmed;
  return `${trimmed.slice(0, max - 1).trimEnd()}…`;
}

function fillRoundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  radius: number,
) {
  const r = Math.min(radius, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
  ctx.fill();
}

/** Professional card PNG: logo on top, QR below, Poppins captions — preview + download. */
export async function buildBrandedAgentQrDataUrl(options: {
  payloadUrl: string;
  agentName: string;
  agentCode: string;
  /** Line under the name; defaults to "Agent <code>". */
  caption?: string;
}): Promise<string> {
  const cardWidth = 720;
  const padX = 56;
  const padTop = 52;
  // Extra bottom pad so the agent/referral code isn’t clipped in modal previews.
  const padBottom = 64;
  const logoMaxWidth = cardWidth - padX * 2;
  const logoMaxHeight = 96;
  const gapLogoQr = 30;
  const qrSize = 440;
  const gapQrCaption = 32;
  const nameSize = 28;
  const codeSize = 22;
  const captionGap = 12;

  await ensurePoppinsReady();

  const qrPixelSize = qrSize * EXPORT_SCALE;
  const [logo, qrCanvas] = await Promise.all([
    loadImage(LOGO_SRC),
    QRCode.toCanvas(options.payloadUrl, {
      errorCorrectionLevel: "H",
      margin: 1,
      width: qrPixelSize,
      color: {
        dark: "#141414",
        light: "#ffffff",
      },
    }),
  ]);

  const logoScale = Math.min(logoMaxWidth / logo.naturalWidth, logoMaxHeight / logo.naturalHeight);
  const logoW = Math.round(logo.naturalWidth * logoScale);
  const logoH = Math.round(logo.naturalHeight * logoScale);

  const captionBlock = nameSize + captionGap + codeSize;
  const cardHeight =
    padTop + logoH + gapLogoQr + qrSize + gapQrCaption + captionBlock + padBottom;

  const canvas = document.createElement("canvas");
  canvas.width = Math.round(cardWidth * EXPORT_SCALE);
  canvas.height = Math.round(cardHeight * EXPORT_SCALE);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas unavailable");

  ctx.setTransform(EXPORT_SCALE, 0, 0, EXPORT_SCALE, 0, 0);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";

  // Card background
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, cardWidth, cardHeight);

  // Soft outer edge for downloads on dark backgrounds
  ctx.strokeStyle = "rgba(20, 20, 20, 0.08)";
  ctx.lineWidth = 1;
  ctx.strokeRect(0.5, 0.5, cardWidth - 1, cardHeight - 1);

  let y = padTop;

  // Logo — draw from full-res source into hi-dpi canvas (no intermediate downscale)
  const logoX = (cardWidth - logoW) / 2;
  ctx.drawImage(logo, logoX, y, logoW, logoH);
  y += logoH + gapLogoQr;

  // QR on a light inset panel
  const qrX = (cardWidth - qrSize) / 2;
  const panelPad = 14;
  const panelX = qrX - panelPad;
  const panelY = y - panelPad;
  const panelSize = qrSize + panelPad * 2;
  ctx.fillStyle = "#f6f7f5";
  fillRoundRect(ctx, panelX, panelY, panelSize, panelSize, 18);
  ctx.drawImage(qrCanvas, qrX, y, qrSize, qrSize);
  y += qrSize + gapQrCaption;

  // Captions — Poppins at export scale for sharp download type
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  ctx.fillStyle = "#141414";
  ctx.font = `600 ${nameSize}px Poppins, system-ui, sans-serif`;
  ctx.fillText(truncateLabel(options.agentName, 36), cardWidth / 2, y, cardWidth - padX * 2);
  y += nameSize + captionGap;

  ctx.fillStyle = "#2f6b3a";
  ctx.font = `700 ${codeSize}px Poppins, system-ui, sans-serif`;
  ctx.fillText(options.caption ?? `Agent ${options.agentCode}`, cardWidth / 2, y);

  return canvas.toDataURL("image/png");
}
