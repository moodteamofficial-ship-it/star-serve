import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type ComponentType, type SVGProps } from "react";
import { FormError } from "@/components/ui/FormError";
import { Modal } from "@/components/ui/Modal";
import { PdfPreview } from "@/components/ui/PdfPreview";
import { PhoneField } from "@/components/ui/PhoneField";
import { Select } from "@/components/ui/Select";
import { TextField } from "@/components/ui/TextField";
import { DEFAULT_PHONE_COUNTRY, fromE164, toE164 } from "@/components/ui/phoneCountries";
import { useAuth } from "@/app/providers/AuthProvider";
import { getClientDeviceId, ApiError } from "@/services/api/client";
import { resolveApiBaseUrl } from "@/services/api/envTarget";
import { customerApi, type CustomerLastVehicle } from "@/services/customers/customerApi";
import type { GuestReturningLookup } from "@/services/insurance/insuranceApi";
import {
  insuranceApi,
  type CatalogMake,
  type CatalogProduct,
  type CustomerLocal,
  type IssuancePayResult,
  type IssuanceSubmitResult,
} from "@/services/insurance/insuranceApi";
import { withNormalizedCategories } from "@/services/insurance/catalogCategories";
import {
  clearPendingGuestAgentCode,
  resolveGuestAgentBootstrap,
  writeGuestAgentReferral,
  type GuestAgentReferral,
} from "@/services/insurance/guestAgent";
import {
  normalizeReferralCode,
  resolveGuestReferralBootstrap,
  writeGuestCustomerReferral,
} from "@/services/insurance/guestReferral";
import { GUEST_TENANTS_STALE_MS, readGuestTenantId, writeGuestTenantId } from "@/services/insurance/guestTenant";
import { intermediaryApi } from "@/services/intermediaries/intermediaryApi";
import { paymentApi } from "@/services/payments/paymentApi";
import { scrollModalToIssue } from "@/utils/scrollModalToIssue";
import {
  IconCar,
  IconCertificate,
  IconCheck,
  IconChevron,
  IconPackage,
  IconUser,
  IconWallet,
  categoryIcon,
} from "./quoteIcons";

type ClientFieldKey = "idNumber" | "firstName" | "lastName" | "phone" | "email";

type PdfReadyState = "idle" | "preparing" | "ready" | "opening" | "error";
type MpesaWaitState = "idle" | "waiting" | "finishing" | "failed";
type PayTrackStatus = "upcoming" | "active" | "done" | "error";
type PickerStage = "product" | "cover";
type StepIcon = ComponentType<SVGProps<SVGSVGElement>>;

type PayTrackStep = {
  id: string;
  title: string;
  detail: string;
  status: PayTrackStatus;
};

export type GuestHeroCopy = {
  title: string;
  subtitle?: string;
};

function formatProductLabel(name: string): string {
  const spaced = name.replace(/\s+/g, " ").trim();
  const withoutSuffix = spaced.split(/\s*[-—]\s*/)[0]?.trim() || spaced;
  const titled = withoutSuffix
    .toLowerCase()
    .replace(/(^|[\s(/])([a-z])/g, (_, edge: string, letter: string) => edge + letter.toUpperCase())
    .replace(/\bTpo\b/g, "TPO")
    .replace(/\bPsv\b/g, "PSV")
    .replace(/\bIra\b/g, "IRA")
    .replace(/\bChauffer\b/gi, "Chauffeur");
  return titled;
}

async function fetchCertificatePdf(
  certificateId: string,
  disposition: "inline" | "attachment" = "inline",
  guest = false,
): Promise<Blob> {
  const qs = new URLSearchParams({ disposition });
  const apiBase = resolveApiBaseUrl();
  const path = guest
    ? `${apiBase}/insurance/guest/certificates/${certificateId}/download`
    : `${apiBase}/certificates/${certificateId}/download`;
  const headers = new Headers();
  headers.set("X-Client-Device-Id", getClientDeviceId());
  const response = await fetch(
    `${path}?${qs.toString()}`,
    { credentials: "include", headers },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => null);
    const message =
      err?.error?.message ||
      "Certificate PDF is still being prepared. Please wait a moment.";
    const details = Array.isArray(err?.error?.details) ? err.error.details : [];
    const permanent = details.some(
      (d: { retryable?: boolean }) => d && d.retryable === false,
    );
    const error = new Error(message) as Error & { retryable?: boolean };
    error.retryable = !permanent;
    throw error;
  }
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength < 8) {
    const error = new Error(
      "Certificate PDF is still being prepared. Please wait a moment.",
    ) as Error & { retryable?: boolean };
    error.retryable = true;
    throw error;
  }
  const head = new Uint8Array(buffer.slice(0, 4));
  const isPdf =
    head[0] === 0x25 && head[1] === 0x50 && head[2] === 0x44 && head[3] === 0x46;
  if (!isPdf) {
    const error = new Error(
      "Certificate PDF is still being prepared. Please wait a moment.",
    ) as Error & { retryable?: boolean };
    error.retryable = true;
    throw error;
  }
  return new Blob([buffer], { type: "application/pdf" });
}

const STEPS: ReadonlyArray<{
  id: number;
  key: "product" | "client" | "vehicle" | "pay" | "certificate";
  label: string;
  Icon: StepIcon;
}> = [
  { id: 1, key: "product", label: "Product", Icon: IconPackage },
  { id: 2, key: "client", label: "Client", Icon: IconUser },
  { id: 3, key: "vehicle", label: "Vehicle", Icon: IconCar },
  { id: 4, key: "pay", label: "Pay", Icon: IconWallet },
  { id: 5, key: "certificate", label: "Certificate", Icon: IconCertificate },
];

type StepKey = (typeof STEPS)[number]["key"];

/** Values are Definite's own (case-sensitive) — anything else returns no premium. */
const COVER_PERIODS = [
  { value: "Monthly", label: "Monthly" },
  { value: "2installments", label: "Semi-annual (2 installments)" },
  { value: "Annually", label: "Annual" },
];

type CoverOption = CatalogProduct["cover_options"][number];

const MONTHLY_COVER_SUFFIX = /\s+MONTHLY$/i;

function coverKey(name: string) {
  return name.trim().toUpperCase().replace(/\s+/g, " ");
}

/** Definite sells monthly cover as a sibling option ("TPO MONTHLY"); the period picks it. */
function visibleCoverOptions(options: CoverOption[]): CoverOption[] {
  const names = new Set(options.map((opt) => coverKey(opt.name)));
  return options.filter((opt) => {
    const key = coverKey(opt.name);
    if (!MONTHLY_COVER_SUFFIX.test(key)) return true;
    return !names.has(key.replace(MONTHLY_COVER_SUFFIX, ""));
  });
}

function pricedCoverOption(
  options: CoverOption[],
  selected: CoverOption | undefined,
  period: string,
): CoverOption | undefined {
  if (!selected || period !== "Monthly") return selected;
  const monthlyKey = `${coverKey(selected.name)} MONTHLY`;
  return options.find((opt) => coverKey(opt.name) === monthlyKey) ?? selected;
}

/** True when Definite exposes a sibling "{Cover} MONTHLY" option for this cover. */
function coverHasMonthlyPlan(
  options: CoverOption[],
  selected: CoverOption | undefined,
): boolean {
  if (!selected) return false;
  if (MONTHLY_COVER_SUFFIX.test(coverKey(selected.name))) return true;
  const monthlyKey = `${coverKey(selected.name)} MONTHLY`;
  return options.some((opt) => coverKey(opt.name) === monthlyKey);
}

function money(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Client budget for Definite settle + generateCertificate (under Cloud Run ~180s). */
// KYC uploads (logbook + ID) are on standby until document storage is provisioned.
// Flip to true to restore the "Upload documents" step after payment.
const KYC_DOCS_ENABLED = false;
const PAY_DONE_ADVANCE_MS = 600;
const CERT_ISSUE_TIMEOUT_MS = 120_000;
const CERT_ISSUE_MAX_ATTEMPTS = 2;
const CERT_ISSUE_RETRY_MS = 2_000;
const CATALOG_STALE_MS = 30 * 60 * 1000;

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = window.setTimeout(() => resolve(), ms);
    const onAbort = () => {
      window.clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

function isAbortError(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === "AbortError") ||
    (error instanceof Error && error.name === "AbortError")
  );
}

export function QuoteWizardPage({
  guest = false,
  onHeadlineChange,
}: {
  guest?: boolean;
  onHeadlineChange?: (copy: GuestHeroCopy | null) => void;
}) {
  const { hasPermission } = useAuth();
  const canReconcileReceipt = !guest && hasPermission("payment:reconcile");
  // Definite Wallet spends agency float, so it needs wallet:debit — not payment:create.
  const canPayFromFloat = !guest && hasPermission("wallet:debit");
  const quoteModalPanelClass = "welcome-type-scale";
  const [step, setStep] = useState<StepKey>("product");
  const [maxReached, setMaxReached] = useState(0);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerStage, setPickerStage] = useState<PickerStage>("product");
  const [clientOpen, setClientOpen] = useState(false);
  const [vehicleOpen, setVehicleOpen] = useState(false);
  const [payOpen, setPayOpen] = useState(false);
  const [payFlowActive, setPayFlowActive] = useState(false);
  const [payFlowComplete, setPayFlowComplete] = useState(false);
  const [payConfirmed, setPayConfirmed] = useState(false);
  const [kycDocs, setKycDocs] = useState<{
    logbook: string | null;
    id_front: string | null;
    id_back: string | null;
  }>({ logbook: null, id_front: null, id_back: null });
  const [kycUploading, setKycUploading] = useState<string | null>(null);
  const [kycError, setKycError] = useState<string | null>(null);

  const [category, setCategory] = useState<string | null>(null);
  const [product, setProduct] = useState<CatalogProduct | null>(null);
  const [coverOptionId, setCoverOptionId] = useState("");
  const [capacity, setCapacity] = useState("4");
  const [sumInsured, setSumInsured] = useState("");
  const [coverPeriod, setCoverPeriod] = useState("Monthly");
  const [makeId, setMakeId] = useState("");
  const [modelId, setModelId] = useState("");
  const [agentCode, setAgentCode] = useState("");
  const [intermediaryId, setIntermediaryId] = useState("");
  const [pendingAgentCode, setPendingAgentCode] = useState<string | null>(null);

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [idNumber, setIdNumber] = useState("");
  const [phone, setPhone] = useState("");
  const [phoneCountry, setPhoneCountry] = useState(DEFAULT_PHONE_COUNTRY);
  const [kraPin, setKraPin] = useState("");
  const [email, setEmail] = useState("");
  const [customer, setCustomer] = useState<CustomerLocal | null>(null);
  const [clientMatched, setClientMatched] = useState(false);
  const [clientLookupStatus, setClientLookupStatus] = useState<
    "idle" | "loading" | "found" | "missing" | "error"
  >("idle");
  const [clientLookupError, setClientLookupError] = useState<string | null>(null);
  const clientLookupGenRef = useRef(0);
  const matchedIdRef = useRef<string | null>(null);
  const lookedUpIdRef = useRef<string | null>(null);
  const [guestReturning, setGuestReturning] = useState<GuestReturningLookup | null>(null);
  const [guestUseRecord, setGuestUseRecord] = useState(false);
  const [guestVehicleFromRecord, setGuestVehicleFromRecord] = useState(false);
  const [clientFieldErrors, setClientFieldErrors] = useState<Partial<Record<ClientFieldKey, string>>>(
    {},
  );
  const guestLookupGenRef = useRef(0);
  const guestLookedUpIdRef = useRef<string | null>(null);
  const guestReturningRef = useRef<GuestReturningLookup | null>(null);
  const guestOptOutIdRef = useRef<string | null>(null);
  const lastEnsureUsedReturningRef = useRef(false);
  const vehiclePrefillRef = useRef<{
    registration: string;
    chassis: string;
    engine: string;
    year: string;
    rating: string;
  } | null>(null);

  const [registration, setRegistration] = useState("");
  const [chassis, setChassis] = useState("");
  const [engine, setEngine] = useState("");
  const [vehicleYear, setVehicleYear] = useState(String(new Date().getFullYear() - 5));
  const [engineRating, setEngineRating] = useState("1500");

  const [submitResult, setSubmitResult] = useState<IssuanceSubmitResult | null>(null);
  const [payResult, setPayResult] = useState<IssuancePayResult | null>(null);
  const [payMethod, setPayMethod] = useState<
    "DEFINITE_WALLET" | "DEFINITE_MPESA" | "BIRDVIEW"
  >("BIRDVIEW");
  const [referralCode, setReferralCode] = useState("");
  const [pendingReferralCode, setPendingReferralCode] = useState<string | null>(null);
  const [guestSessionReady, setGuestSessionReady] = useState(!guest);
  const [guestSessionError, setGuestSessionError] = useState<string | null>(null);
  const [guestTenantId, setGuestTenantId] = useState(() => (guest ? readGuestTenantId() : ""));
  const [mpesaPhone, setMpesaPhone] = useState("");
  const [mpesaCountry, setMpesaCountry] = useState(DEFAULT_PHONE_COUNTRY);
  const [pdfState, setPdfState] = useState<PdfReadyState>("idle");
  const [pdfMessage, setPdfMessage] = useState("");
  const [pdfRetryKey, setPdfRetryKey] = useState(0);
  const [pdfPreviewOpen, setPdfPreviewOpen] = useState(false);
  const [pdfPreviewBlob, setPdfPreviewBlob] = useState<Blob | null>(null);
  const [summaryPdfBusy, setSummaryPdfBusy] = useState(false);
  const [summaryPdfError, setSummaryPdfError] = useState<string | null>(null);
  const [mpesaWait, setMpesaWait] = useState<MpesaWaitState>("idle");
  const [mpesaMessage, setMpesaMessage] = useState("");
  const [mpesaReceipt, setMpesaReceipt] = useState("");
  const [receiptConfirming, setReceiptConfirming] = useState(false);
  const pdfObjectUrlRef = useRef<string | null>(null);
  const pdfBlobRef = useRef<Blob | null>(null);
  const pdfPollGenRef = useRef(0);
  const mpesaPollGenRef = useRef(0);
  const payAttemptRef = useRef(0);
  const certIssueGenRef = useRef(0);
  const certFinishLockRef = useRef(false);
  const payAdvanceTimerRef = useRef<number | null>(null);
  const issueCertificateAfterPaymentRef = useRef<() => Promise<void>>(async () => {});

  const catalog = useQuery({
    queryKey: ["insurance-catalog", guest, guestSessionReady],
    queryFn: async () => withNormalizedCategories((await insuranceApi.catalog(guest)).data),
    enabled: !guest || guestSessionReady,
    staleTime: CATALOG_STALE_MS,
    gcTime: CATALOG_STALE_MS * 2,
    refetchOnWindowFocus: false,
    retry: (failureCount, error) => {
      const message = error instanceof Error ? error.message : String(error);
      if (/rate limit|too many|try later|try again later/i.test(message)) {
        return false;
      }
      return failureCount < 1;
    },
  });

  const guestTenants = useQuery({
    queryKey: ["guest-tenants"],
    queryFn: async () => (await insuranceApi.listGuestTenants()).data,
    enabled: guest,
    staleTime: GUEST_TENANTS_STALE_MS,
  });

  useEffect(() => {
    if (!guest || !guestTenants.data?.items?.length) return;
    // Welcome flow always uses the first agency in the DB (created_at order).
    const first = guestTenants.data.items[0]?.id ?? "";
    if (!first || guestTenantId === first) return;
    setGuestTenantId(first);
    writeGuestTenantId(first);
  }, [guest, guestTenants.data, guestTenantId]);

  useEffect(() => {
    if (!guest || !guestTenantId) return;
    let cancelled = false;
    let retryTimer: number | undefined;

    async function ensureSession(attempt = 0) {
      try {
        await insuranceApi.startGuestSession(guestTenantId);
        if (!cancelled) {
          setGuestSessionReady(true);
          setGuestSessionError(null);
        }
      } catch (err) {
        if (cancelled) return;
        const message =
          err instanceof Error ? err.message : "Could not start a secure guest quote session";
        const csrfFailed = /csrf/i.test(message);
        // Never auto-retry rate limits — that extends the lockout.
        if (csrfFailed && attempt < 1) {
          retryTimer = window.setTimeout(
            () => {
              void ensureSession(attempt + 1);
            },
            400,
          );
          return;
        }
        setGuestSessionReady(false);
        setGuestSessionError(message);
      }
    }

    setGuestSessionReady(false);
    void ensureSession();
    return () => {
      cancelled = true;
      if (retryTimer) window.clearTimeout(retryTimer);
    };
  }, [guest, guestTenantId]);

  useEffect(() => {
    if (!guest) return;
    const { pendingCode, referral } = resolveGuestAgentBootstrap();
    if (pendingCode) {
      setPendingAgentCode(pendingCode);
      return;
    }
    if (!referral) return;
    applyGuestAgentReferral(referral);
  }, [guest]);

  useEffect(() => {
    if (!guest || !guestSessionReady || !pendingAgentCode) return;
    let cancelled = false;
    void insuranceApi
      .resolveGuestAgent(pendingAgentCode)
      .then(({ data }) => {
        if (cancelled) return;
        writeGuestAgentReferral(data);
        clearPendingGuestAgentCode();
        applyGuestAgentReferral({ ...data, locked: true });
        setPendingAgentCode(null);
      })
      .catch(() => {
        if (cancelled) return;
        // Invalid codes fall back to the default agent; the pending code stays in
        // sessionStorage so a hard refresh retries the same scan.
        setPendingAgentCode(null);
      });
    return () => {
      cancelled = true;
    };
  }, [guest, guestSessionReady, pendingAgentCode]);

  useEffect(() => {
    if (!guest) return;
    const { pendingCode, referral } = resolveGuestReferralBootstrap();
    if (pendingCode) {
      setPendingReferralCode(pendingCode);
      return;
    }
    if (!referral) return;
    setReferralCode(referral.referral_code);
  }, [guest]);

  useEffect(() => {
    if (!guest || !guestSessionReady || !pendingReferralCode) return;
    let cancelled = false;
    void insuranceApi
      .resolveGuestReferral(pendingReferralCode)
      .then(({ data }) => {
        if (cancelled) return;
        writeGuestCustomerReferral(data);
        setReferralCode(data.referral_code);
        setPendingReferralCode(null);
      })
      .catch(() => {
        if (cancelled) return;
        setPendingReferralCode(null);
      });
    return () => {
      cancelled = true;
    };
  }, [guest, guestSessionReady, pendingReferralCode]);

  function applyGuestAgentReferral(agent: GuestAgentReferral) {
    setAgentCode(agent.agent_code);
    setIntermediaryId(agent.id);
  }

  const intermediaries = useQuery({
    queryKey: ["issuance-intermediaries"],
    queryFn: async () => (await intermediaryApi.list({ status: "APPROVED", page: 1 })).data,
    enabled: !guest,
  });

  const selectedMake: CatalogMake | undefined = useMemo(
    () => catalog.data?.makes.find((m) => m.external_id === makeId || m.code === makeId),
    [catalog.data?.makes, makeId],
  );
  const selectedModel = useMemo(
    () => selectedMake?.models.find((m) => m.id === modelId),
    [selectedMake, modelId],
  );
  const selectedCover = useMemo(
    () => product?.cover_options.find((o) => o.id === coverOptionId),
    [product, coverOptionId],
  );
  const pricedCover = useMemo(
    () => pricedCoverOption(product?.cover_options ?? [], selectedCover, coverPeriod),
    [product, selectedCover, coverPeriod],
  );
  const hasMonthlyCoverPlan = useMemo(
    () => coverHasMonthlyPlan(product?.cover_options ?? [], selectedCover),
    [product, selectedCover],
  );
  const showNoMonthlyBadge = Boolean(selectedCover) && !hasMonthlyCoverPlan;
  const selectedIntermediary = useMemo(
    () => intermediaries.data?.items.find((row) => row.id === intermediaryId),
    [intermediaries.data?.items, intermediaryId],
  );
  const lastCoverForPeriodRef = useRef<string | null>(null);

  function applyDefaultPeriodForCover(cover: CoverOption | undefined, options: CoverOption[]) {
    if (!cover) return;
    if (coverHasMonthlyPlan(options, cover)) {
      setCoverPeriod("Monthly");
    } else {
      setCoverPeriod("Annually");
    }
  }

  useEffect(() => {
    const coverId = selectedCover?.id ?? null;
    if (!coverId || coverId === lastCoverForPeriodRef.current) return;
    lastCoverForPeriodRef.current = coverId;
    applyDefaultPeriodForCover(selectedCover, product?.cover_options ?? []);
    invalidateQuote();
  }, [selectedCover, product]);

  const resolvedAgentCode =
    agentCode.trim() ||
    selectedIntermediary?.agent_code?.trim() ||
    selectedIntermediary?.external_intermediary_ref?.trim() ||
    undefined;

  const premium = useMutation({
    mutationFn: async () => {
      if (guest && !guestSessionReady) {
        throw new Error("Secure guest session is still starting — try again in a moment");
      }
      if (!product || !pricedCover) throw new Error("Select product and cover option");
      const seats = Number(capacity);
      if (!Number.isFinite(seats) || seats <= 0) {
        throw new Error("Enter seating capacity");
      }
      const sum = sumInsured.trim() === "" ? 0 : Number(sumInsured);
      if (!Number.isFinite(sum) || sum < 0) {
        throw new Error("Enter a valid sum insured, or leave it blank");
      }
      return (
        await insuranceApi.calculatePremium({
          product: product.external_id,
          cover_option: pricedCover.id,
          cover_period: coverPeriod,
          capacity: seats,
          tonnage: 0,
          sum_insured: sum,
          transaction_type: "1",
        }, guest)
      ).data;
    },
  });

  /** A changed quote input makes any submitted proposal stale. */
  function invalidateQuote() {
    premium.reset();
    setSubmitResult(null);
  }

  function clearLoadedClientDetails() {
    matchedIdRef.current = null;
    setClientMatched(false);
    setFirstName("");
    setLastName("");
    setPhone("");
    setPhoneCountry(DEFAULT_PHONE_COUNTRY);
    setKraPin("");
    setEmail("");
    setCustomer(null);
    clearPrefilledVehicle();
  }

  /** Undo a returning-client vehicle prefill, keeping anything the user edited. */
  function clearPrefilledVehicle() {
    const filled = vehiclePrefillRef.current;
    if (!filled) return;
    vehiclePrefillRef.current = null;
    const keepIfEdited = (cur: string, prefilled: string, reset: string) =>
      cur === prefilled ? reset : cur;
    setRegistration((cur) => keepIfEdited(cur, filled.registration, ""));
    setChassis((cur) => keepIfEdited(cur, filled.chassis, ""));
    setEngine((cur) => keepIfEdited(cur, filled.engine, ""));
    setVehicleYear((cur) =>
      keepIfEdited(cur, filled.year, String(new Date().getFullYear() - 5)),
    );
    setEngineRating((cur) => keepIfEdited(cur, filled.rating, "1500"));
  }

  /** Prefill the vehicle step from the client's last proposal when it's the same make. */
  function prefillLastVehicle(
    last: CustomerLastVehicle | GuestReturningLookup["vehicle"] | undefined,
  ): boolean {
    if (!last || !selectedMake || registration.trim() || chassis.trim()) return false;
    const lastMake = (last.make_code ?? "").trim();
    const sameMake =
      (lastMake !== "" &&
        (lastMake === selectedMake.external_id || lastMake === selectedMake.code)) ||
      (last.make_name ?? "").trim().toUpperCase() === selectedMake.name.trim().toUpperCase();
    if (!sameMake || !last.registration || !last.chassis_number) return false;
    const filled = {
      registration: (last.registration ?? "").toUpperCase(),
      chassis: (last.chassis_number ?? "").toUpperCase(),
      engine: (last.engine_number ?? "").toUpperCase(),
      year: last.vehicle_year ? String(last.vehicle_year) : vehicleYear,
      rating: last.engine_rating ? String(last.engine_rating) : engineRating,
    };
    vehiclePrefillRef.current = filled;
    setRegistration(filled.registration);
    setChassis(filled.chassis);
    setEngine(filled.engine);
    setVehicleYear(filled.year);
    setEngineRating(filled.rating);
    return true;
  }

  function resetGuestReturning() {
    guestLookupGenRef.current += 1;
    guestLookedUpIdRef.current = null;
    guestReturningRef.current = null;
    setGuestReturning(null);
    setGuestUseRecord(false);
    if (guestVehicleFromRecord) {
      setGuestVehicleFromRecord(false);
      clearPrefilledVehicle();
    }
  }

  /** Guests only ever receive masked values; the server applies the real ones. */
  async function lookupGuestReturning(cleaned: string): Promise<GuestReturningLookup | null> {
    if (cleaned.length < 7) {
      resetGuestReturning();
      return null;
    }
    if (guestLookedUpIdRef.current === cleaned) {
      return guestReturningRef.current;
    }
    const gen = ++guestLookupGenRef.current;
    try {
      const { data } = await insuranceApi.guestClientLookup(cleaned);
      if (gen !== guestLookupGenRef.current) return null;
      guestLookedUpIdRef.current = cleaned;
      const found = data.found && data.client ? data : null;
      guestReturningRef.current = found;
      setGuestReturning(found);
      // Keep an explicit "Not you" opt-out for this ID; otherwise auto-use the record.
      const optedOut = guestOptOutIdRef.current === cleaned;
      setGuestUseRecord(Boolean(found) && !optedOut);
      return found;
    } catch {
      if (gen !== guestLookupGenRef.current) return null;
      guestReturningRef.current = null;
      setGuestReturning(null);
      setGuestUseRecord(false);
      return null;
    }
  }

  async function lookupClientById(rawId: string) {
    const cleaned = rawId.trim().replace(/\s+/g, "").toUpperCase();
    if (guest) {
      if (guestSessionReady) await lookupGuestReturning(cleaned);
      return;
    }
    if (cleaned.length < 7) {
      clientLookupGenRef.current += 1;
      lookedUpIdRef.current = null;
      setClientLookupStatus("idle");
      setClientLookupError(null);
      clearLoadedClientDetails();
      return;
    }
    if (
      lookedUpIdRef.current === cleaned &&
      (clientLookupStatus === "found" || clientLookupStatus === "missing")
    ) {
      return;
    }

    const gen = ++clientLookupGenRef.current;
    setClientLookupStatus("loading");
    setClientLookupError(null);
    try {
      const { data } = await customerApi.lookupByIdNumber(cleaned);
      if (gen !== clientLookupGenRef.current) return;
      lookedUpIdRef.current = cleaned;
      if (data.found && data.customer) {
        const row = data.customer;
        const parsed = fromE164(row.phone);
        matchedIdRef.current = (row.id_number || cleaned).toUpperCase();
        lookedUpIdRef.current = matchedIdRef.current;
        prefillLastVehicle(data.last_vehicle);
        setFirstName(row.first_name || "");
        setLastName(row.last_name || "");
        setIdNumber(row.id_number || cleaned);
        setPhone(parsed.national);
        setPhoneCountry(parsed.iso);
        setKraPin(row.kra_pin || "");
        setEmail(row.email || "");
        setClientMatched(true);
        setClientLookupStatus("found");
        setCustomer({
          id: row.id,
          first_name: row.first_name,
          last_name: row.last_name,
          id_number: row.id_number,
          phone: row.phone,
          kra_pin: row.kra_pin,
          email: row.email,
          external_client_ref: row.external_client_ref,
        });
      } else {
        clearLoadedClientDetails();
        setClientLookupStatus("missing");
      }
    } catch (error) {
      if (gen !== clientLookupGenRef.current) return;
      clearLoadedClientDetails();
      setClientLookupStatus("error");
      setClientLookupError(
        error instanceof ApiError
          ? error.message
          : error instanceof Error
            ? error.message
            : "Could not look up this ID",
      );
    }
  }

  const lookupClientRef = useRef(lookupClientById);
  lookupClientRef.current = lookupClientById;

  useEffect(() => {
    if (!clientOpen) return;
    if (guest && !guestSessionReady) return;
    const cleaned = idNumber.trim().replace(/\s+/g, "");
    if (cleaned.length < 7) return;
    const timer = window.setTimeout(() => {
      void lookupClientRef.current(idNumber);
    }, 450);
    return () => window.clearTimeout(timer);
  }, [guest, guestSessionReady, clientOpen, idNumber]);

  const guestUsingRecord = Boolean(guest && guestUseRecord && guestReturning?.client);
  const clientDetailsLocked = !guest && clientMatched;
  const showClientDetailsForm =
    guest ||
    clientLookupStatus === "missing" ||
    clientLookupStatus === "found" ||
    clientMatched;

  function setClientFieldError(key: ClientFieldKey, message: string) {
    setClientFieldErrors((prev) => ({ ...prev, [key]: message }));
  }

  function clearClientFieldError(key: ClientFieldKey) {
    setClientFieldErrors((prev) => {
      if (!prev[key]) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }

  function validateClientDetailsForm(usingReturning: boolean): boolean {
    const next: Partial<Record<ClientFieldKey, string>> = {};
    const cleanedId = idNumber.trim().replace(/\s+/g, "");
    if (!cleanedId) next.idNumber = "ID / passport is required";
    if (!usingReturning) {
      if (!firstName.trim()) next.firstName = "First name is required";
      if (!lastName.trim()) next.lastName = "Last name is required";
      if (!phone.trim()) next.phone = "Phone is required";
      else if (!toE164(phoneCountry, phone)) next.phone = "Enter a valid phone number";
      if (!email.trim()) next.email = "Email is required for certificate issuance";
    }
    setClientFieldErrors(next);
    if (Object.keys(next).length) {
      window.requestAnimationFrame(() => scrollModalToIssue());
      return false;
    }
    return true;
  }

  const ensureClient = useMutation({
    mutationFn: async () => {
      if (clientLookupStatus === "loading") {
        throw new Error("Still looking up this ID — wait a moment");
      }
      const cleaned = idNumber.trim().replace(/\s+/g, "").toUpperCase();
      if (!cleaned) {
        setClientFieldError("idNumber", "ID / passport is required");
        window.requestAnimationFrame(() => scrollModalToIssue());
        throw new Error("ID / passport is required");
      }

      let useReturning = guestUsingRecord && guestLookedUpIdRef.current === cleaned;
      if (guest && guestSessionReady && cleaned.length >= 7) {
        const optedOut = guestOptOutIdRef.current === cleaned;
        if (!useReturning && !optedOut) {
          const found =
            guestLookedUpIdRef.current === cleaned && guestReturning?.client
              ? guestReturning
              : await lookupGuestReturning(cleaned);
          if (found?.client) {
            useReturning = true;
            setGuestUseRecord(true);
          }
        }
      }

      if (!validateClientDetailsForm(useReturning)) {
        throw new Error(
          useReturning
            ? "ID / passport is required"
            : "First name, last name, ID number, phone, and email are required",
        );
      }

      lastEnsureUsedReturningRef.current = useReturning;
      if (useReturning) {
        setGuestUseRecord(true);
        return (await insuranceApi.guestReturningClient(idNumber)).data;
      }
      const resolvedPhone = toE164(phoneCountry, phone);
      if (!resolvedPhone) {
        setClientFieldError("phone", "Enter a valid phone number");
        window.requestAnimationFrame(() => scrollModalToIssue());
        throw new Error("Enter a valid phone number");
      }
      return (
        await insuranceApi.issuanceClient({
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          id_number: idNumber.trim(),
          phone: resolvedPhone,
          kra_pin: kraPin.trim() || undefined,
          email: email.trim(),
        }, guest)
      ).data;
    },
    onSuccess: (data) => {
      setCustomer(data.local);
      setClientMatched(true);
      setClientFieldErrors({});
      if (guest && lastEnsureUsedReturningRef.current && !guestVehicleFromRecord) {
        setGuestVehicleFromRecord(prefillLastVehicle(guestReturningRef.current?.vehicle));
        setGuestUseRecord(true);
      }
      setClientOpen(false);
      goTo("vehicle");
      setVehicleOpen(true);
    },
  });

  const submitIssuance = useMutation({
    mutationFn: async () => {
      if (!product || !customer || !selectedMake || !pricedCover) {
        throw new Error("Product, client, and make are required");
      }
      if (!selectedModel) {
        throw new Error("Select the vehicle model. It is printed on the certificate");
      }
      const seats = Number(capacity);
      if (!Number.isFinite(seats) || seats <= 0) {
        throw new Error("Enter seating capacity");
      }
      const sum = sumInsured.trim() === "" ? 0 : Number(sumInsured);
      if (!Number.isFinite(sum) || sum < 0) {
        throw new Error("Enter a valid sum insured, or leave it blank");
      }
      if (!registration.trim() || !chassis.trim()) {
        throw new Error("Registration and chassis number are required");
      }
      const referral = referralCode.trim() ? normalizeReferralCode(referralCode) : null;
      return (
        await insuranceApi.issuanceSubmit({
          customer_id: customer.id,
          product_external_id: product.external_id,
          product_code: product.code || product.external_id,
          product_name: product.name,
          cover_option_id: pricedCover.id,
          cover_option_name: pricedCover.name,
          cover_period: coverPeriod,
          cover_period_used: coverPeriod,
          capacity: seats,
          tonnage: 0,
          sum_insured: sum,
          vehicle_registration: registration.trim(),
          vehicle_make_code: selectedMake.external_id || selectedMake.code,
          vehicle_make_name: selectedMake.name,
          vehicle_model_code: selectedModel.id,
          vehicle_model_name: selectedModel.name,
          vehicle_year: Number(vehicleYear) || new Date().getFullYear(),
          chassis_number: chassis.trim(),
          engine_number: engine.trim() || undefined,
          engine_rating: Number(engineRating) || 1500,
          agent_code: resolvedAgentCode,
          intermediary_id: intermediaryId || undefined,
          referral_code: referral ?? undefined,
          ...(guest && guestVehicleFromRecord ? { use_last_vehicle: true } : {}),
        }, guest)
      ).data;
    },
    onSuccess: (data) => {
      setSubmitResult(data);
      setPayResult(null);
      setPayFlowActive(false);
      setPayFlowComplete(false);
      setVehicleOpen(false);
      goTo("pay");
      setPayOpen(true);
    },
  });

  const payIssuance = useMutation({
    mutationFn: async (attempt: number) => {
      if (!submitResult?.policy?.id) throw new Error("Submit the vehicle step first");
      if (attempt > 1) {
        // A previous prompt may still be pending server-side; the backend never
        // re-sends an STK while one is open.
        await insuranceApi.cancelPendingPayment(submitResult.policy.id, guest);
      }
      return (
        await insuranceApi.issuancePay({
          policy_id: submitResult.policy.id,
          method: payMethod,
          phone:
            payMethod === "DEFINITE_MPESA" || payMethod === "BIRDVIEW"
              ? toE164(mpesaCountry, mpesaPhone) || toE164(phoneCountry, phone) || undefined
              : undefined,
        }, guest)
      ).data;
    },
    onSuccess: (data, attempt) => {
      if (attempt !== payAttemptRef.current) {
        // Abandoned while the STK request was in flight.
        if (data.payment.status !== "SUCCESS" && !data.certificate && submitResult?.policy?.id) {
          void insuranceApi.cancelPendingPayment(submitResult.policy.id, guest).catch(() => {});
        }
        return;
      }
      setPayResult(data);
      if (data.payment.status === "SUCCESS" || data.certificate) {
        finishPayFlowAndAdvance();
        return;
      }
      if (data.payment.status === "PENDING" || data.payment.status === "INITIATED") {
        // One STK only. Wait for Definite / BirdView confirmation before certificate
        setPayFlowActive(true);
        setPayOpen(false);
        setMpesaWait("waiting");
        setMpesaMessage(
          "STK prompt sent. Confirm on your phone. We continue when payment is confirmed.",
        );
      }
    },
    onError: (error, attempt) => {
      if (attempt !== payAttemptRef.current) return;
      const alreadyPaid = payResult?.payment?.status === "SUCCESS";
      if (alreadyPaid) {
        setPayConfirmed(true);
        setMpesaWait("failed");
        setMpesaMessage(
          error instanceof Error
            ? error.message
            : "Payment succeeded but the certificate could not be issued yet.",
        );
        return;
      }
      setMpesaWait("failed");
      setMpesaMessage(error instanceof Error ? error.message : "Payment could not be started.");
    },
  });

  const currentIndex = STEPS.findIndex((s) => s.key === step);
  const stepsListRef = useRef<HTMLOListElement>(null);
  const certificateId = payResult?.certificate?.id ?? null;
  const pendingPaymentId =
    mpesaWait === "waiting" || mpesaWait === "finishing"
      ? payResult?.payment?.id ?? null
      : null;

  useEffect(() => {
    const list = stepsListRef.current;
    if (!list) return;
    const frame = window.requestAnimationFrame(() => {
      const current = list.querySelector<HTMLElement>(".quote-step--current");
      if (!current) return;
      const listWidth = list.clientWidth;
      const maxScroll = Math.max(0, list.scrollWidth - listWidth);
      const target = Math.min(
        maxScroll,
        Math.max(0, current.offsetLeft - (listWidth - current.offsetWidth) / 2),
      );
      list.scrollTo({ left: target, behavior: "smooth" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [currentIndex]);

  useEffect(() => {
    if (!pendingPaymentId || mpesaWait !== "waiting") return;

    const gen = ++mpesaPollGenRef.current;
    let cancelled = false;
    let timer: number | undefined;

    async function poll(attempt: number) {
      if (cancelled || mpesaPollGenRef.current !== gen) return;
      try {
        const { data } = await paymentApi.get(pendingPaymentId!, { guest });
        if (cancelled || mpesaPollGenRef.current !== gen) return;

        if (data.status === "SUCCESS") {
          if (certFinishLockRef.current) return;
          certFinishLockRef.current = true;
          setMpesaWait("finishing");
          setPayConfirmed(true);
          setPayResult((prev) =>
            prev
              ? { ...prev, payment: { ...prev.payment, status: "SUCCESS" } }
              : prev,
          );
          setMpesaMessage("Payment confirmed. Issuing certificate…");
          // Do not await inside this effect: switching to "finishing" cancels the
          // effect and would drop a successful certificate response.
          void issueCertificateAfterPaymentRef.current();
          return;
        }

        if (data.status === "FAILED" || data.status === "CANCELLED" || data.status === "REVERSED") {
          setMpesaWait("failed");
          setMpesaMessage(
            data.failure_message ||
              `Payment ${data.status.toLowerCase()}. You can send the STK prompt again.`,
          );
          return;
        }

        setMpesaMessage(
          attempt < 2
            ? "Waiting for payment confirmation…"
            : payMethod === "BIRDVIEW"
              ? "Still waiting for BirdView to confirm the payment…"
              : "Still waiting for Definite to confirm the payment…",
        );
      } catch {
        // Keep polling through transient network errors
      }

      if (attempt >= 90) {
        setMpesaWait("failed");
        setMpesaMessage(
          "No payment confirmation yet. If you already paid, wait a moment and try again. We will not send another STK until you ask.",
        );
        return;
      }
      // Poll faster early (webhook usually arrives within ~30s), then back off.
      const delayMs = attempt < 12 ? 1500 : attempt < 30 ? 2500 : 4000;
      timer = window.setTimeout(() => {
        void poll(attempt + 1);
      }, delayMs);
    }

    void poll(0);
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [pendingPaymentId, mpesaWait, guest, payMethod]);

  useEffect(() => {
    return () => {
      if (pdfObjectUrlRef.current) {
        URL.revokeObjectURL(pdfObjectUrlRef.current);
        pdfObjectUrlRef.current = null;
      }
      pdfBlobRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (step !== "certificate" || !certificateId) {
      return;
    }

    const gen = ++pdfPollGenRef.current;
    let cancelled = false;
    let timer: number | undefined;

    if (pdfObjectUrlRef.current) {
      URL.revokeObjectURL(pdfObjectUrlRef.current);
      pdfObjectUrlRef.current = null;
    }
    pdfBlobRef.current = null;

    setPdfState("preparing");
    setPdfMessage("Preparing your certificate PDF…");

    const maxAttempts = 60;

    async function poll(attempt: number) {
      if (cancelled || pdfPollGenRef.current !== gen) return;
      try {
        const blob = await fetchCertificatePdf(certificateId!, "inline", guest);
        if (cancelled || pdfPollGenRef.current !== gen) return;
        if (pdfObjectUrlRef.current) URL.revokeObjectURL(pdfObjectUrlRef.current);
        pdfBlobRef.current = blob;
        pdfObjectUrlRef.current = URL.createObjectURL(blob);
        setPdfState("ready");
        setPdfMessage("Your certificate PDF is ready.");
      } catch (err) {
        if (cancelled || pdfPollGenRef.current !== gen) return;
        const retryable = (err as Error & { retryable?: boolean }).retryable !== false;
        const message =
          err instanceof Error && err.message
            ? err.message
            : "Certificate PDF is still being prepared.";
        if (!retryable) {
          setPdfState("error");
          setPdfMessage(message);
          return;
        }
        if (attempt >= maxAttempts) {
          setPdfState("error");
          setPdfMessage(
            "The PDF is taking longer than usual. You can keep waiting or try again.",
          );
          return;
        }
        // Backend probes Azure only after the URL is saved — poll a bit slower
        const delayMs = attempt < 10 ? 1500 : attempt < 25 ? 2500 : 4000;
        setPdfMessage(
          attempt < 4
            ? "Preparing your certificate PDF…"
            : "Still preparing. Definite is finalizing the document…",
        );
        timer = window.setTimeout(() => {
          void poll(attempt + 1);
        }, delayMs);
      }
    }

    void poll(0);

    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [step, certificateId, pdfRetryKey, guest]);

  async function downloadCertificatePdf() {
    if (!certificateId) return;
    const name =
      (payResult?.certificate?.external_certificate_ref ||
        payResult?.certificate?.certificate_number ||
        "certificate") + ".pdf";
    try {
      const blob = await fetchCertificatePdf(certificateId, "attachment", guest);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = name;
      link.rel = "noopener";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch {
      // Fall back to preview blob if a fresh download fails
      const blob = pdfPreviewBlob || pdfBlobRef.current;
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = name;
      link.rel = "noopener";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    }
  }

  async function openCertificatePdf() {
    if (!certificateId) return;
    if (pdfState === "ready" && pdfBlobRef.current) {
      setPdfPreviewBlob(pdfBlobRef.current);
      setPdfPreviewOpen(true);
      return;
    }
    setPdfState("opening");
    setPdfMessage("Opening certificate PDF…");
    try {
      const blob = await fetchCertificatePdf(certificateId, "inline", guest);
      if (pdfObjectUrlRef.current) URL.revokeObjectURL(pdfObjectUrlRef.current);
      pdfBlobRef.current = blob;
      pdfObjectUrlRef.current = URL.createObjectURL(blob);
      setPdfState("ready");
      setPdfMessage("Your certificate PDF is ready.");
      setPdfPreviewBlob(blob);
      setPdfPreviewOpen(true);
    } catch {
      setPdfState("preparing");
      setPdfMessage("Still preparing. Definite is finalizing the document…");
    }
  }

  function goTo(next: StepKey) {
    const idx = STEPS.findIndex((s) => s.key === next);
    setMaxReached((prev) => Math.max(prev, idx));
    setStep(next);
  }

  function clearPayAdvanceTimer() {
    if (payAdvanceTimerRef.current != null) {
      window.clearTimeout(payAdvanceTimerRef.current);
      payAdvanceTimerRef.current = null;
    }
  }

  function finishPayFlowAndAdvance() {
    setPayFlowComplete(true);
    setPayConfirmed(true);
    setMpesaWait("idle");
    setMpesaMessage("");
    setPayOpen(false);
    setPayFlowActive(true);
    setKycDocs({ logbook: null, id_front: null, id_back: null });
    setKycError(null);
    clearPayAdvanceTimer();
    if (KYC_DOCS_ENABLED) return;
    // Brief "Certificate issued" beat on the tracker, then straight to the certificate.
    payAdvanceTimerRef.current = window.setTimeout(() => {
      payAdvanceTimerRef.current = null;
      setPayFlowActive(false);
      setPayFlowComplete(false);
      goTo("certificate");
    }, PAY_DONE_ADVANCE_MS);
  }

  async function issueCertificateAfterPayment() {
    const policyId = submitResult?.policy?.id;
    if (!policyId) {
      certFinishLockRef.current = false;
      setPayConfirmed(true);
      setMpesaWait("failed");
      setMpesaMessage("Missing policy. Submit the vehicle step again.");
      return;
    }

    const method =
      (payResult?.payment?.method as "DEFINITE_MPESA" | "BIRDVIEW" | undefined) ?? payMethod;
    const payPhone =
      toE164(mpesaCountry, mpesaPhone) || toE164(phoneCountry, phone) || undefined;

    const issueGen = ++certIssueGenRef.current;
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), CERT_ISSUE_TIMEOUT_MS);

    try {
      let lastError: unknown;
      for (let attempt = 0; attempt < CERT_ISSUE_MAX_ATTEMPTS; attempt++) {
        if (certIssueGenRef.current !== issueGen) return;
        try {
          const finished = (
            await insuranceApi.issuancePay(
              {
                policy_id: policyId,
                method,
                phone: payPhone,
              },
              guest,
              { signal: controller.signal },
            )
          ).data;
          if (certIssueGenRef.current !== issueGen) return;
          setPayResult(finished);
          if (finished.certificate?.id) {
            finishPayFlowAndAdvance();
            return;
          }
          if (finished.payment.status === "SUCCESS") {
            lastError = new Error(
              "Payment succeeded but the certificate is not ready yet.",
            );
            if (attempt < CERT_ISSUE_MAX_ATTEMPTS - 1) {
              setMpesaMessage(
                "Payment confirmed. Still generating your cover document…",
              );
              await sleep(CERT_ISSUE_RETRY_MS, controller.signal);
              continue;
            }
            throw lastError;
          }
          throw new Error(
            `Unexpected payment status ${finished.payment.status} while issuing the certificate.`,
          );
        } catch (error) {
          if (certIssueGenRef.current !== issueGen) return;
          if (isAbortError(error)) throw error;
          lastError = error;
          if (attempt < CERT_ISSUE_MAX_ATTEMPTS - 1) {
            setMpesaMessage("Payment confirmed. Retrying certificate issuance…");
            await sleep(CERT_ISSUE_RETRY_MS, controller.signal);
            continue;
          }
          throw error;
        }
      }
      throw lastError ?? new Error("Certificate could not be issued yet.");
    } catch (error) {
      if (certIssueGenRef.current !== issueGen) return;
      certFinishLockRef.current = false;
      setPayConfirmed(true);
      setMpesaWait("failed");
      setMpesaMessage(
        isAbortError(error)
          ? "Certificate is taking longer than expected. Your payment is confirmed — tap Issue certificate to finish and view it."
          : error instanceof Error
            ? error.message
            : "Payment succeeded but the certificate could not be issued yet.",
      );
    } finally {
      window.clearTimeout(timeoutId);
    }
  }

  issueCertificateAfterPaymentRef.current = issueCertificateAfterPayment;

  function retryCertificateIssuance() {
    if (mpesaWait === "waiting" || mpesaWait === "finishing") {
      return;
    }
    clearPayAdvanceTimer();
    certFinishLockRef.current = true;
    setPayConfirmed(true);
    setPayFlowComplete(false);
    setPayOpen(false);
    setPayFlowActive(true);
    setMpesaWait("finishing");
    setMpesaMessage("Payment confirmed. Issuing certificate…");
    payIssuance.reset();
    void issueCertificateAfterPayment();
  }

  /** Payment confirmed — only the certificate step remains, so never abandon it. */
  const paymentLocked =
    mpesaWait === "finishing" || payConfirmed || payResult?.payment?.status === "SUCCESS";

  /** Stop waiting on the current STK so a new one can be sent. */
  function abandonPendingPayment() {
    if (paymentLocked) return;
    const hadPrompt =
      payIssuance.isPending || mpesaWait === "waiting" || mpesaWait === "failed";
    payAttemptRef.current += 1;
    clearPayAdvanceTimer();
    mpesaPollGenRef.current += 1;
    certIssueGenRef.current += 1;
    certFinishLockRef.current = false;
    setMpesaWait("idle");
    setMpesaMessage("");
    setMpesaReceipt("");
    setReceiptConfirming(false);
    setPayResult(null);
    payIssuance.reset();
    const policyId = submitResult?.policy?.id;
    if (hadPrompt && policyId) {
      void insuranceApi.cancelPendingPayment(policyId, guest).catch(() => {});
    }
  }

  function startPayFlow() {
    if (mpesaWait === "finishing") return;
    if (payConfirmed || payResult?.payment?.status === "SUCCESS") {
      retryCertificateIssuance();
      return;
    }
    clearPayAdvanceTimer();
    certFinishLockRef.current = false;
    mpesaPollGenRef.current += 1;
    certIssueGenRef.current += 1;
    setMpesaWait("idle");
    setMpesaMessage("");
    setMpesaReceipt("");
    setReceiptConfirming(false);
    setPayConfirmed(false);
    setPayFlowComplete(false);
    setPayOpen(false);
    setPayFlowActive(true);
    payIssuance.reset();
    payAttemptRef.current += 1;
    payIssuance.mutate(payAttemptRef.current);
  }

  function cancelPayFlow() {
    if (paymentLocked) return;
    abandonPendingPayment();
    setPayFlowActive(false);
    setPayFlowComplete(false);
    setPayConfirmed(false);
  }

  function leavePayStep() {
    if (paymentLocked) return;
    if (!(payIssuance.isPending || mpesaWait === "waiting" || mpesaWait === "failed")) return;
    cancelPayFlow();
  }

  const leavePayStepRef = useRef(leavePayStep);
  leavePayStepRef.current = leavePayStep;

  useEffect(() => {
    if (step !== "pay") leavePayStepRef.current();
  }, [step]);

  async function confirmPaidWithReceipt() {
    const paymentId = payResult?.payment?.id;
    if (!paymentId || !submitResult?.policy?.id || receiptConfirming) return;
    const receipt = mpesaReceipt.trim();
    if (receipt.length < 6) {
      setMpesaMessage("Enter the M-Pesa receipt code from your confirmation SMS.");
      return;
    }
    setReceiptConfirming(true);
    setMpesaMessage("Confirming your M-Pesa receipt…");
    try {
      await paymentApi.confirmReceipt(paymentId, receipt);
      certFinishLockRef.current = true;
      setMpesaWait("finishing");
      setPayConfirmed(true);
      setMpesaMessage("Payment confirmed. Issuing certificate…");
      await issueCertificateAfterPayment();
    } catch (error) {
      certFinishLockRef.current = false;
      setMpesaWait("waiting");
      setMpesaMessage(
        error instanceof Error ? error.message : "Could not confirm that receipt. Try again.",
      );
    } finally {
      setReceiptConfirming(false);
    }
  }

  function resetQuote() {
    setStep("product");
    setMaxReached(0);
    setSubmitResult(null);
    setPayResult(null);
    setCustomer(null);
    setPayFlowActive(false);
    setPayFlowComplete(false);
    setPayConfirmed(false);
    setMpesaWait("idle");
    setMpesaMessage("");
    clearPayAdvanceTimer();
    certFinishLockRef.current = false;
    mpesaPollGenRef.current += 1;
    certIssueGenRef.current += 1;
    setPdfPreviewOpen(false);
    setPdfPreviewBlob(null);
    setPdfState("idle");
    setPdfMessage("");
    premium.reset();
  }

  const kycDocsReady =
    !KYC_DOCS_ENABLED || Boolean(kycDocs.logbook && kycDocs.id_front && kycDocs.id_back);

  const payTrackSteps = useMemo((): PayTrackStep[] => {
    const paymentSettled =
      payConfirmed || payResult?.payment?.status === "SUCCESS";
    const failed = mpesaWait === "failed" || payIssuance.isError;
    const errorDetail =
      mpesaMessage ||
      (payIssuance.error instanceof Error ? payIssuance.error.message : "Something went wrong.");

    const docsStatus: PayTrackStatus = !payFlowComplete
      ? "upcoming"
      : kycDocsReady
        ? "done"
        : "active";

    const docsStep: PayTrackStep = {
      id: "documents",
      title: "Upload documents",
      detail:
        docsStatus === "active"
          ? "Upload logbook and ID (front & back) before previewing the certificate."
          : docsStatus === "done"
            ? "Documents saved."
            : "Logbook and national ID photos after cover is issued.",
      status: docsStatus,
    };
    const docsSteps: PayTrackStep[] = KYC_DOCS_ENABLED ? [docsStep] : [];
    const docsUpcoming: PayTrackStep[] = docsSteps.map((s) => ({ ...s, status: "upcoming" }));

    if (payMethod === "DEFINITE_MPESA" || payMethod === "BIRDVIEW") {
      const railLabel =
        payMethod === "BIRDVIEW"
          ? "BirdView"
          : payMethod === "DEFINITE_MPESA"
            ? "Definite M-Pesa"
            : "M-Pesa";
      const stkDone =
        payFlowComplete ||
        paymentSettled ||
        mpesaWait === "waiting" ||
        mpesaWait === "finishing" ||
        (mpesaWait === "failed" && Boolean(payResult?.payment?.id));
      const confirmDone = payFlowComplete || paymentSettled || mpesaWait === "finishing";
      const certDone = payFlowComplete;

      let stkStatus: PayTrackStatus = "upcoming";
      if (failed && !stkDone) stkStatus = "error";
      else if (stkDone) stkStatus = "done";
      else if (payIssuance.isPending) stkStatus = "active";

      let confirmStatus: PayTrackStatus = "upcoming";
      if (failed && stkDone && !confirmDone) confirmStatus = "error";
      else if (confirmDone) confirmStatus = "done";
      else if (mpesaWait === "waiting") confirmStatus = "active";

      let certStatus: PayTrackStatus = "upcoming";
      if (failed && confirmDone) certStatus = "error";
      else if (certDone) certStatus = "done";
      else if (mpesaWait === "finishing") certStatus = "active";

      return [
        {
          id: "stk",
          title: `Send ${railLabel} prompt`,
          detail:
            stkStatus === "active"
              ? "Sending the STK push to your phone…"
              : stkStatus === "done"
                ? "Prompt sent to your phone."
                : stkStatus === "error"
                  ? errorDetail
                  : `We’ll push a payment request via ${railLabel}.`,
          status: stkStatus,
        },
        {
          id: "confirm",
          title: "Confirm on your phone",
          detail:
            confirmStatus === "active"
              ? mpesaMessage || "Enter your M-Pesa PIN when prompted."
              : confirmStatus === "done"
                ? "Payment confirmed."
                : confirmStatus === "error"
                  ? errorDetail
                  : "Approve the payment on your handset.",
          status: confirmStatus,
        },
        {
          id: "certificate",
          title: "Issue certificate",
          detail:
            certStatus === "active"
              ? "Payment received. Generating your cover document…"
              : certStatus === "done"
                ? "Certificate issued."
                : certStatus === "error"
                  ? errorDetail
                  : "Activate cover and create the certificate.",
          status: certStatus,
        },
        ...docsSteps,
      ];
    }

    // Wallet: one API call. Show clear before / during / after states
    if (payFlowComplete) {
      return [
        {
          id: "settle",
          title: "Settle with wallet",
          detail: "Wallet settled.",
          status: "done",
        },
        {
          id: "provider",
          title: "Confirm with insurer",
          detail: "Definite approval complete.",
          status: "done",
        },
        {
          id: "certificate",
          title: "Issue certificate",
          detail: "Certificate issued.",
          status: "done",
        },
        ...docsSteps,
      ];
    }

    if (failed) {
      return [
        {
          id: "settle",
          title: "Settle with wallet",
          detail: errorDetail,
          status: "error",
        },
        {
          id: "provider",
          title: "Confirm with insurer",
          detail: "Waiting for wallet settlement first.",
          status: "upcoming",
        },
        {
          id: "certificate",
          title: "Issue certificate",
          detail: "Activates after insurer confirmation.",
          status: "upcoming",
        },
        ...docsUpcoming,
      ];
    }

    if (payIssuance.isPending) {
      return [
        {
          id: "settle",
          title: "Settle with wallet",
          detail: "Debiting your local wallet…",
          status: "active",
        },
        {
          id: "provider",
          title: "Confirm with insurer",
          detail: "Next: approve once with Definite.",
          status: "upcoming",
        },
        {
          id: "certificate",
          title: "Issue certificate",
          detail: "Then generate your cover document.",
          status: "upcoming",
        },
        ...docsUpcoming,
      ];
    }

    return [
      {
        id: "settle",
        title: "Settle with wallet",
        detail: "Star Serve settles the premium from wallet.",
        status: "upcoming",
      },
      {
        id: "provider",
        title: "Confirm with insurer",
        detail: "Definite confirms the payment once.",
        status: "upcoming",
      },
      {
        id: "certificate",
        title: "Issue certificate",
        detail: "Activate cover and create the certificate.",
        status: "upcoming",
      },
      ...docsUpcoming,
    ];
  }, [
    payMethod,
    payIssuance.isPending,
    payIssuance.isError,
    payIssuance.error,
    mpesaWait,
    mpesaMessage,
    payFlowComplete,
    payConfirmed,
    payResult,
    kycDocsReady,
  ]);

  const payTrackHeadline = useMemo(() => {
    const paymentSettled =
      payConfirmed || payResult?.payment?.status === "SUCCESS";
    if (payFlowComplete && !kycDocsReady) return "Upload documents";
    if (payFlowComplete) return "Payment complete";
    if ((mpesaWait === "failed" || payIssuance.isError) && paymentSettled) {
      return "Certificate not issued yet";
    }
    if (mpesaWait === "failed" || payIssuance.isError) return "Payment interrupted";
    if (mpesaWait === "finishing") return "Issuing certificate";
    if (mpesaWait === "waiting") {
      return payMethod === "BIRDVIEW" || payMethod === "DEFINITE_MPESA"
        ? "Waiting for payment"
        : "Processing payment";
    }
    if (payIssuance.isPending) return "Starting payment";
    return payFlowActive ? "Pay premium" : "Pay premium";
  }, [payFlowComplete, kycDocsReady, mpesaWait, payIssuance.isError, payIssuance.isPending, payMethod, payConfirmed, payResult?.payment?.status, payFlowActive]);

  async function uploadKycDoc(kind: "logbook" | "id_front" | "id_back", file: File | null) {
    if (!file || !customer?.id) return;
    setKycError(null);
    setKycUploading(kind);
    try {
      const data = await insuranceApi.uploadCustomerDocument(customer.id, kind, file, guest);
      setKycDocs((prev) => ({ ...prev, [kind]: data.url }));
    } catch (err) {
      setKycError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setKycUploading(null);
    }
  }

  const guestHeroCopy = useMemo((): GuestHeroCopy | null => {
    if (!guest) return null;
    if (step === "client") return { title: "Client details" };
    if (step === "vehicle") return { title: "Vehicle & proposal" };
    if (step === "pay") {
      return { title: payFlowActive ? payTrackHeadline : "Pay premium" };
    }
    if (step === "certificate") {
      return {
        title: payResult?.certificate
          ? "Cover issued"
          : payResult?.payment.status === "SUCCESS"
            ? "Almost there"
            : "Certificate",
        subtitle: payResult?.certificate
          ? pdfState === "ready"
            ? "Your PDF is ready to open."
            : "Active cover. Preparing your PDF."
          : "Finish payment to get your PDF.",
      };
    }
    return null;
  }, [
    guest,
    step,
    payFlowActive,
    payTrackHeadline,
    payResult?.certificate,
    payResult?.payment.status,
    pdfState,
  ]);

  useEffect(() => {
    onHeadlineChange?.(guestHeroCopy);
  }, [guestHeroCopy, onHeadlineChange]);

  useEffect(() => {
    return () => onHeadlineChange?.(null);
  }, [onHeadlineChange]);

  useEffect(() => {
    return () => clearPayAdvanceTimer();
  }, []);

  function selectCategory(name: string) {
    setCategory(name);
    setProduct(null);
    setCoverOptionId("");
    invalidateQuote();
    setPickerStage("product");
    setPickerOpen(true);
  }

  function selectProduct(row: CatalogProduct) {
    setProduct(row);
    const first = visibleCoverOptions(row.cover_options)[0];
    setCoverOptionId(first?.id ?? "");
    lastCoverForPeriodRef.current = first?.id ?? null;
    applyDefaultPeriodForCover(first, row.cover_options);
    invalidateQuote();
    setPickerStage("cover");
  }

  function closePicker() {
    setPickerOpen(false);
  }

  async function continueFromCover() {
    if (guest && !guestSessionReady) return;
    if (!coverOptionId || !makeId || !modelId) return;
    const seats = Number(capacity);
    if (!Number.isFinite(seats) || seats <= 0) return;
    try {
      const result = premium.data ?? (await premium.mutateAsync());
      if (result.premium.gross_premium == null) return;
      setPickerOpen(false);
      goTo("client");
      setClientOpen(true);
    } catch {
      // Error surfaces via premium.isError in the modal.
    }
  }

  const categoryProducts =
    catalog.data?.categories.find((c) => c.category === category)?.products ?? [];
  const SelectedCategoryIcon = category ? categoryIcon(category) : null;

  // Referral credit / monthly referral cost are collected on BirdView only — the
  // customer pays Star Serve; Definite is settled later at its own total.
  const definiteTotal = Number(
    submitResult?.provider?.amount_to_pay ??
      submitResult?.policy?.gross_premium ??
      premium.data?.premium.gross_premium ??
      0,
  );
  const isMonthlyPeriod = /month/i.test(coverPeriod) && !/semi|install/i.test(coverPeriod);
  const referralCost = Number(
    submitResult?.referral?.referral_cost ?? (isMonthlyPeriod ? 50 : 0),
  );
  const referralDiscount =
    payMethod === "BIRDVIEW" ? Number(submitResult?.referral?.discount ?? 0) : 0;
  const amountDue =
    payMethod === "BIRDVIEW" && submitResult?.referral?.amount_payable != null
      ? submitResult.referral.amount_payable
      : payMethod === "BIRDVIEW"
        ? definiteTotal + referralCost - referralDiscount
        : definiteTotal ||
          submitResult?.provider?.amount_to_pay ||
          submitResult?.policy?.gross_premium ||
          premium.data?.premium.gross_premium;

  async function downloadSummaryPdf() {
    if (!submitResult) return;
    setSummaryPdfBusy(true);
    setSummaryPdfError(null);
    try {
      const { downloadQuoteSummaryPdf } = await import("./quoteSummaryPdf");
      const breakdown = premium.data?.premium;
      const clientName = [customer?.first_name ?? firstName, customer?.last_name ?? lastName]
        .map((part) => part.trim())
        .filter(Boolean)
        .join(" ");
      await downloadQuoteSummaryPdf({
        clientName: clientName || undefined,
        clientPhone: (customer?.phone ?? phone).trim() || undefined,
        clientEmail: (customer?.email ?? email).trim() || undefined,
        cover: formatProductLabel(
          product?.cover_options.find((opt) => opt.id === coverOptionId)?.name ?? "Selected cover",
        ),
        period: COVER_PERIODS.find((p) => p.value === coverPeriod)?.label ?? coverPeriod,
        sumInsured: money(sumInsured),
        vehicle: `${selectedMake?.name ?? "-"} / ${selectedModel?.name ?? "-"}`,
        registration: submitResult.policy.vehicle_registration ?? registration,
        policyNumber: submitResult.policy.policy_number,
        premium: breakdown
          ? {
              basic: money(breakdown.basic_premium),
              phcf: money(breakdown.phcf),
              trainingLevy: money(breakdown.training_levy),
              stampDuty: money(breakdown.stamp_duty),
              gross: money(breakdown.gross_premium),
              referralCost: referralCost > 0 ? money(referralCost) : undefined,
            }
          : undefined,
        amountDue: money(amountDue),
        providerNote: String(submitResult.provider.document_number ?? "-"),
      });
    } catch (err) {
      setSummaryPdfError(err instanceof Error ? err.message : "Could not create the PDF");
    } finally {
      setSummaryPdfBusy(false);
    }
  }

  const stepsNav = (
    <header className="quote-hero">
      <ol ref={stepsListRef} className="quote-steps" aria-label="Issuance steps">
        {STEPS.map((item, index) => {
          const state =
            index < currentIndex ? "done" : index === currentIndex ? "current" : "upcoming";
          const StepIcon = item.Icon;
          return (
            <li key={item.key} className={`quote-step quote-step--${state}`}>
              <button
                type="button"
                disabled={index > maxReached && index > currentIndex}
                onClick={() => {
                  if (index <= Math.max(maxReached, currentIndex)) {
                    setStep(item.key);
                    setClientOpen(item.key === "client");
                    setVehicleOpen(item.key === "vehicle");
                    setPayOpen(item.key === "pay");
                  }
                }}
              >
                <span className="quote-step-index" aria-hidden="true">
                  {state === "done" ? <IconCheck /> : <StepIcon />}
                </span>
                <span className="quote-step-label">{item.label}</span>
                <span className="quote-step-ordinal">{item.id}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </header>
  );

  return (
    <section className={`quote-wizard${guest ? "" : " quote-wizard--staff"}`}>
      {step === "product" ? (
        <div className="quote-body">
          <div className="quote-panel">
            <div className="quote-panel-head quote-panel-head--toolbar">
              {guest ? null : (
                <div className="quote-panel-copy">
                  <h2>Choose a product class</h2>
                </div>
              )}
              {stepsNav}
            </div>
            {guestSessionError ? (
              <div className="guest-session-error">
                <FormError title="Guest session unavailable">{guestSessionError}</FormError>
                <button
                  type="button"
                  className="text-link guest-session-retry"
                  onClick={() => {
                    setGuestSessionError(null);
                    setGuestSessionReady(false);
                    void insuranceApi
                      .startGuestSession(guestTenantId)
                      .then(() => {
                        setGuestSessionReady(true);
                        setGuestSessionError(null);
                      })
                      .catch((err: unknown) => {
                        setGuestSessionReady(false);
                        setGuestSessionError(
                          err instanceof Error
                            ? err.message
                            : "Could not start a secure guest quote session",
                        );
                      });
                  }}
                >
                  Try again
                </button>
              </div>
            ) : null}
            {catalog.isError && !(catalog.data?.categories?.length) ? (
              <FormError title="Catalog unavailable">
                {(catalog.error as Error).message}
                <button
                  type="button"
                  className="config-btn config-btn--ghost"
                  style={{ marginTop: "0.65rem" }}
                  onClick={() => void catalog.refetch()}
                >
                  Try again
                </button>
              </FormError>
            ) : null}
            {guest ? (
              <div className="guest-quote-toolbar">
                <div className="quote-panel-copy quote-panel-copy--guest-row">
                  <h2 className="quote-section-title">Choose a product class</h2>
                </div>
              </div>
            ) : null}
            <div
              className={`product-category-grid${
                catalog.isPending && !catalog.data ? " is-loading" : ""
              }`}
              aria-busy={catalog.isPending && !catalog.data ? true : undefined}
              aria-label={
                catalog.isPending && !catalog.data ? "Loading product classes" : undefined
              }
            >
              {catalog.isPending && !catalog.data
                ? Array.from({ length: 6 }, (_, index) => (
                    <div
                      key={`category-skeleton-${index}`}
                      className="product-category-card product-category-card--skeleton"
                      aria-hidden="true"
                    >
                      <span className="product-category-top">
                        <span className="skeleton-block skeleton-block--icon" />
                        <span className="skeleton-block skeleton-block--chip" />
                      </span>
                      <span className="product-category-copy">
                        <span className="skeleton-block skeleton-block--title" />
                        <span className="skeleton-block skeleton-block--meta" />
                      </span>
                    </div>
                  ))
                : (catalog.data?.categories ?? []).map((group) => {
                    const CategoryIcon = categoryIcon(group.category);
                    const selected = category === group.category;
                    return (
                      <button
                        key={group.category}
                        type="button"
                        className={`product-category-card${selected ? " is-selected" : ""}`}
                        onClick={() => selectCategory(group.category)}
                      >
                        <span className="product-category-top">
                          <span className="product-category-icon" aria-hidden="true">
                            <CategoryIcon />
                          </span>
                          <span className="product-category-chevron" aria-hidden="true">
                            <IconChevron />
                          </span>
                        </span>
                        <span className="product-category-copy">
                          <strong>{group.category}</strong>
                          <em>
                            {group.product_count} product{group.product_count === 1 ? "" : "s"}
                          </em>
                        </span>
                      </button>
                    );
                  })}
            </div>
          </div>

          {product && premium.data?.premium.gross_premium != null ? (
            <div className="quote-selection-block">
              <h3 className="quote-selection-heading">Selected cover</h3>
              <div className="quote-selection-card quote-selection-card--cover">
                <div className="quote-selection-main">
                  {SelectedCategoryIcon ? (
                    <span className="quote-selection-icon" aria-hidden="true">
                      <SelectedCategoryIcon />
                    </span>
                  ) : null}
                  <p className="quote-selection-inline">
                    <strong>{formatProductLabel(product.name)}</strong>
                    <span>{category ?? "Product class"}</span>
                  </p>
                </div>
                <div className="quote-selection-aside">
                  <div className="quote-selection-amount">
                    <span className="quote-selection-amount-label">Gross</span>
                    <strong>
                      <em>KES</em>
                      {money(premium.data.premium.gross_premium)}
                    </strong>
                  </div>
                  <div className="quote-actions" style={{ marginTop: 0 }}>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => {
                        setPickerStage("cover");
                        setPickerOpen(true);
                      }}
                    >
                      Edit
                    </button>
                    <button type="button" onClick={() => goTo("client")}>
                      Continue
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          <Modal
            open={pickerOpen}
            size="xl"
            panelClassName={quoteModalPanelClass}
            icon={SelectedCategoryIcon ? <SelectedCategoryIcon /> : undefined}
            title={
              pickerStage === "product"
                ? category ?? "Select product"
                : "Cover & premium"
            }
            subtitle={
              pickerStage === "product"
                ? `${categoryProducts.length} product${
                    categoryProducts.length === 1 ? "" : "s"
                  } · choose one to continue`
                : product
                  ? formatProductLabel(product.name)
                  : undefined
            }
            onClose={closePicker}
            footer={
              pickerStage === "cover" ? (
                <>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => {
                      setPickerStage("product");
                      invalidateQuote();
                    }}
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    disabled={
                      !coverOptionId ||
                      !makeId ||
                      !modelId ||
                      premium.isPending ||
                      !capacity ||
                      Number(capacity) <= 0 ||
                      (guest && !guestSessionReady)
                    }
                    onClick={() => void continueFromCover()}
                  >
                    {premium.isPending
                      ? "Pricing…"
                      : guest && !guestSessionReady
                        ? "Connecting…"
                        : "Next"}
                  </button>
                </>
              ) : (
                <button type="button" className="secondary" onClick={closePicker}>
                  Cancel
                </button>
              )
            }
          >
            {pickerStage === "product" ? (
              <div className="modal-choice-list">
                {categoryProducts.map((row) => {
                  const selected = product?.external_id === row.external_id;
                  const coverCount = visibleCoverOptions(row.cover_options).length;
                  return (
                    <button
                      key={row.external_id}
                      type="button"
                      className={`modal-choice${selected ? " is-selected" : ""}`}
                      onClick={() => selectProduct(row)}
                    >
                      <span className="modal-choice-copy">
                        <strong>{formatProductLabel(row.name)}</strong>
                        <em>
                          {coverCount > 0
                            ? `${coverCount} cover option${coverCount === 1 ? "" : "s"}`
                            : row.description
                              ? formatProductLabel(row.description)
                              : "Tap to set cover"}
                        </em>
                      </span>
                      <span className="modal-choice-marker" aria-hidden="true">
                        {selected ? <IconCheck /> : <IconChevron />}
                      </span>
                    </button>
                  );
                })}
                {categoryProducts.length === 0 ? (
                  <p className="empty">No products in this class.</p>
                ) : null}
              </div>
            ) : (
              <div className="modal-cover">
                <div className="form-grid modal-form-grid">
                      <Select
                        label="Cover option"
                        value={coverOptionId}
                        onChange={(next) => {
                          setCoverOptionId(next);
                          const cover = product?.cover_options.find((opt) => opt.id === next);
                          lastCoverForPeriodRef.current = next || null;
                          applyDefaultPeriodForCover(cover, product?.cover_options ?? []);
                          invalidateQuote();
                        }}
                        options={visibleCoverOptions(product?.cover_options ?? []).map((opt) => ({
                          value: opt.id,
                          label: opt.name,
                        }))}
                        placeholder="Select cover…"
                        required
                      />
                      <Select
                        label="Cover period"
                        value={coverPeriod}
                        onChange={(next) => {
                          setCoverPeriod(next);
                          invalidateQuote();
                        }}
                        options={COVER_PERIODS.map((p) => ({
                          value: p.value,
                          label: p.label,
                          disabled: p.value === "Monthly" && showNoMonthlyBadge,
                          badge:
                            p.value === "Monthly" && showNoMonthlyBadge
                              ? "No monthly"
                              : undefined,
                        }))}
                        badge={showNoMonthlyBadge ? "No monthly" : undefined}
                        hint={
                          showNoMonthlyBadge
                            ? undefined
                            : undefined
                        }
                        required
                      />
                      <TextField
                        label="Seating capacity"
                        type="number"
                        min={1}
                        step={1}
                        value={capacity}
                        onChange={(e) => {
                          setCapacity(e.target.value);
                          invalidateQuote();
                        }}
                        required
                      />
                      <Select
                        label="Vehicle make"
                        value={makeId}
                        onChange={(next) => {
                          setMakeId(next);
                          setModelId("");
                          setSumInsured("");
                          invalidateQuote();
                        }}
                        options={(catalog.data?.makes ?? []).map((m) => ({
                          value: m.external_id,
                          label: m.name,
                        }))}
                        placeholder="Select make…"
                        required
                      />
                      {selectedMake ? (
                        <Select
                          label="Model"
                          value={modelId}
                          onChange={(next) => {
                            setModelId(next);
                            invalidateQuote();
                          }}
                          options={(selectedMake.models ?? []).map((m) => ({
                            value: m.id,
                            label: m.name,
                          }))}
                          placeholder="Select model…"
                          required
                        />
                      ) : null}
                      {selectedModel ? (
                        <TextField
                          label="Sum insured (KES)"
                          type="number"
                          min={0}
                          step={1000}
                          placeholder="Optional · e.g. 1500000"
                          value={sumInsured}
                          onChange={(e) => {
                            setSumInsured(e.target.value);
                            invalidateQuote();
                          }}
                        />
                      ) : null}
                    </div>

                {premium.isError ? (
                  <FormError title="Premium calculation failed">
                    {(premium.error as Error).message}
                  </FormError>
                ) : null}
              </div>
            )}
          </Modal>
        </div>
      ) : null}

      {step === "client" ? (
        <div className="quote-body">
          <div className="quote-panel">
            <div className="quote-panel-head quote-panel-head--toolbar">
              {guest ? null : (
                <div className="quote-panel-copy">
                  <h2>Client details</h2>
                </div>
              )}
              {stepsNav}
            </div>

            {customer ? (
              <div className="quote-selection-card">
                <div className="quote-selection-main">
                  <span className="quote-selection-icon" aria-hidden="true">
                    <IconUser />
                  </span>
                  <p className="quote-selection-inline">
                    <strong>
                      {customer.first_name} {customer.last_name}
                    </strong>
                    <span>
                      {customer.id_number}
                      {customer.phone ? ` · ${customer.phone}` : ""}
                    </span>
                  </p>
                </div>
                <div className="quote-actions" style={{ marginTop: 0 }}>
                  <button type="button" className="secondary" onClick={() => setClientOpen(true)}>
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      goTo("vehicle");
                      setVehicleOpen(true);
                    }}
                  >
                    Continue
                  </button>
                </div>
              </div>
            ) : (
              <div className="quote-selection-card quote-selection-card--prompt">
                <div className="quote-selection-main">
                  <span className="quote-selection-icon" aria-hidden="true">
                    <IconUser />
                  </span>
                  <p className="quote-selection-inline">
                    <strong>Add client details</strong>
                    <span>
                      {guest
                        ? "Name, ID, phone, email, and optional KRA"
                        : "Start with ID / passport — returning clients load automatically"}
                    </span>
                  </p>
                </div>
                <div className="quote-actions" style={{ marginTop: 0 }}>
                  <button type="button" className="secondary" onClick={() => setStep("product")}>
                    Back
                  </button>
                  <button type="button" onClick={() => setClientOpen(true)}>
                    Continue
                  </button>
                </div>
              </div>
            )}

            <Modal
              open={clientOpen}
              size="xl"
              panelClassName={quoteModalPanelClass}
              icon={<IconUser />}
              title="Client details"
              onClose={() => setClientOpen(false)}
              footer={
                <>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => {
                      setClientOpen(false);
                      setStep("product");
                    }}
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    disabled={
                      ensureClient.isPending ||
                      (!guest &&
                        (clientLookupStatus === "loading" ||
                          clientLookupStatus === "idle" ||
                          (clientLookupStatus === "missing" &&
                            (!firstName.trim() || !lastName.trim() || !phone.trim() || !email.trim()))))
                    }
                    onClick={() => ensureClient.mutate()}
                  >
                    {ensureClient.isPending
                      ? "Saving…"
                      : clientLookupStatus === "loading"
                        ? "Checking…"
                        : "Next"}
                  </button>
                </>
              }
            >
              <div className="modal-cover">
                <div className="form-grid modal-form-grid">
                  <TextField
                    label="ID / passport"
                    value={idNumber}
                    onChange={(e) => {
                      const next = e.target.value;
                      setIdNumber(next);
                      clearClientFieldError("idNumber");
                      const cleaned = next.trim().replace(/\s+/g, "").toUpperCase();
                      if (guest) {
                        if (guestLookedUpIdRef.current !== cleaned) {
                          if (guestUsingRecord && customer) {
                            setCustomer(null);
                            setClientMatched(false);
                          }
                          if (guestOptOutIdRef.current && guestOptOutIdRef.current !== cleaned) {
                            guestOptOutIdRef.current = null;
                          }
                          resetGuestReturning();
                        }
                        return;
                      }
                      if (matchedIdRef.current && matchedIdRef.current !== cleaned) {
                        clearLoadedClientDetails();
                      }
                      if (clientLookupStatus !== "idle" && clientLookupStatus !== "loading") {
                        setClientLookupStatus("idle");
                        setClientLookupError(null);
                      }
                    }}
                    onBlur={() => {
                      void lookupClientById(idNumber);
                    }}
                    autoComplete="off"
                    required
                    error={clientFieldErrors.idNumber}
                    hint={
                      guest
                        ? guestUsingRecord
                          ? `Welcome back, ${guestReturning?.masked_name || "there"} — your saved details will be used`
                          : undefined
                        : clientLookupStatus === "loading"
                          ? "Looking up existing client…"
                          : clientLookupStatus === "found"
                            ? vehiclePrefillRef.current
                              ? "Returning client loaded — last vehicle prefilled for the next step"
                              : "Returning client loaded — details are locked"
                            : clientLookupStatus === "missing"
                              ? "No match — enter the remaining details"
                              : "Type the ID / passport — we'll search existing clients automatically"
                    }
                    fieldClassName="quote-client-id-field"
                  />
                  {guestUsingRecord && guestReturning?.client ? (
                    <>
                      <TextField
                        label="First name"
                        value={guestReturning.client.first_name}
                        disabled
                        readOnly
                      />
                      <TextField
                        label="Last name"
                        value={guestReturning.client.last_name}
                        disabled
                        readOnly
                      />
                      <TextField
                        label="Phone"
                        value={guestReturning.client.phone ?? "—"}
                        disabled
                        readOnly
                      />
                      <TextField
                        label="Email"
                        value={guestReturning.client.email ?? "—"}
                        disabled
                        readOnly
                      />
                      <div className="quote-returning-switch">
                        <button
                          type="button"
                          className="link-button"
                          onClick={() => {
                            guestOptOutIdRef.current =
                              idNumber.trim().replace(/\s+/g, "").toUpperCase() || null;
                            setGuestUseRecord(false);
                            if (guestVehicleFromRecord) {
                              setGuestVehicleFromRecord(false);
                              clearPrefilledVehicle();
                            }
                          }}
                        >
                          Not you? Enter details instead
                        </button>
                      </div>
                    </>
                  ) : showClientDetailsForm ? (
                    <>
                      <TextField
                        label="First name"
                        value={firstName}
                        onChange={(e) => {
                          setFirstName(e.target.value);
                          clearClientFieldError("firstName");
                        }}
                        autoComplete="given-name"
                        required
                        disabled={clientDetailsLocked}
                        error={clientFieldErrors.firstName}
                      />
                      <TextField
                        label="Last name"
                        value={lastName}
                        onChange={(e) => {
                          setLastName(e.target.value);
                          clearClientFieldError("lastName");
                        }}
                        autoComplete="family-name"
                        required
                        disabled={clientDetailsLocked}
                        error={clientFieldErrors.lastName}
                      />
                      <PhoneField
                        label="Phone"
                        value={phone}
                        onChange={(value) => {
                          setPhone(value);
                          clearClientFieldError("phone");
                        }}
                        country={phoneCountry}
                        onCountryChange={(iso) => {
                          setPhoneCountry(iso);
                          if (!mpesaPhone.trim()) setMpesaCountry(iso);
                        }}
                        autoComplete="tel-national"
                        required
                        disabled={clientDetailsLocked}
                        error={clientFieldErrors.phone}
                      />
                      <TextField
                        label="KRA PIN"
                        value={kraPin}
                        onChange={(e) => setKraPin(e.target.value)}
                        disabled={clientDetailsLocked}
                      />
                      <TextField
                        label="Email"
                        type="email"
                        value={email}
                        onChange={(e) => {
                          setEmail(e.target.value);
                          clearClientFieldError("email");
                        }}
                        placeholder="client@email.com"
                        autoComplete="email"
                        required
                        disabled={clientDetailsLocked}
                        error={clientFieldErrors.email}
                      />
                    </>
                  ) : null}
                </div>
                {clientLookupError ? (
                  <FormError title="Lookup failed">{clientLookupError}</FormError>
                ) : null}
                {ensureClient.isError ? (
                  <FormError title="Couldn’t save client">
                    {(ensureClient.error as Error).message}
                  </FormError>
                ) : null}
                {clientMatched && customer ? (
                  <div className="quote-modal-ready" role="status">
                    <span className="quote-modal-ready-icon" aria-hidden="true">
                      <IconCheck />
                    </span>
                    <div className="quote-modal-ready-copy">
                      <p className="quote-modal-ready-kicker">Existing client</p>
                      <p className="quote-modal-ready-title">
                        {customer.first_name} {customer.last_name}
                      </p>
                      <p className="quote-modal-ready-meta">
                        <span>{customer.id_number}</span>
                        {customer.phone ? <span>{customer.phone}</span> : null}
                      </p>
                    </div>
                  </div>
                ) : null}
              </div>
            </Modal>
          </div>
        </div>
      ) : null}

      {step === "vehicle" ? (
        <div className="quote-body">
          <div className="quote-panel">
            <div className="quote-panel-head quote-panel-head--toolbar">
              {guest ? null : (
                <div className="quote-panel-copy">
                  <h2>Vehicle & proposal</h2>
                </div>
              )}
              {stepsNav}
            </div>

            {submitResult ? (
              <div className="quote-selection-card">
                <div>
                  <p className="quote-selection-label">Proposal</p>
                  <strong className="mono">{submitResult.policy.policy_number}</strong>
                  <span>
                    {submitResult.policy.vehicle_registration ?? registration} · awaiting payment
                  </span>
                </div>
                <div className="quote-actions" style={{ marginTop: 0 }}>
                  <button type="button" className="secondary" onClick={() => setVehicleOpen(true)}>
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      goTo("pay");
                      setPayOpen(true);
                    }}
                  >
                    Continue
                  </button>
                </div>
              </div>
            ) : (
              <div className="quote-selection-card">
                <div>
                  <p className="quote-selection-label">Next</p>
                  <strong>Confirm vehicle details</strong>
                  <span>
                    {selectedMake?.name ?? "Make"} / {selectedModel?.name ?? "model"} ·{" "}
                    {registration || "registration pending"}
                  </span>
                </div>
                <div className="quote-actions" style={{ marginTop: 0 }}>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => {
                      setStep("client");
                      setClientOpen(true);
                    }}
                  >
                    Back
                  </button>
                  <button type="button" onClick={() => setVehicleOpen(true)}>
                    Continue
                  </button>
                </div>
              </div>
            )}

            <Modal
              open={vehicleOpen}
              size="xl"
              panelClassName={quoteModalPanelClass}
              icon={<IconCar />}
              title="Vehicle & proposal"
              subtitle="Confirm vehicle details, then submit the proposal for payment."
              onClose={() => setVehicleOpen(false)}
              footer={
                <>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => {
                      setVehicleOpen(false);
                      setStep("client");
                      setClientOpen(true);
                    }}
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    disabled={
                      submitIssuance.isPending ||
                      !customer ||
                      !selectedModel ||
                      !capacity ||
                      Number(capacity) <= 0
                    }
                    onClick={() => submitIssuance.mutate()}
                  >
                    {submitIssuance.isPending ? "Submitting…" : "Submit"}
                  </button>
                </>
              }
            >
              <div className="modal-cover">
                <div className="form-grid modal-form-grid">
                  <TextField
                    label="Registration"
                    value={registration}
                    onChange={(e) => setRegistration(e.target.value.toUpperCase())}
                    placeholder="KDA 123A"
                    required
                    disabled={guestVehicleFromRecord}
                    hint={guestVehicleFromRecord ? "From your last quote" : undefined}
                  />
                  <TextField
                    label="Chassis number"
                    value={chassis}
                    onChange={(e) => setChassis(e.target.value.toUpperCase())}
                    required
                    disabled={guestVehicleFromRecord}
                  />
                  <TextField
                    label="Engine number"
                    value={engine}
                    onChange={(e) => setEngine(e.target.value.toUpperCase())}
                    placeholder="Optional"
                    disabled={guestVehicleFromRecord}
                  />
                  {guestVehicleFromRecord ? (
                    <div className="quote-returning-switch">
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => {
                          setGuestVehicleFromRecord(false);
                          clearPrefilledVehicle();
                        }}
                      >
                        Insuring a different vehicle? Enter its details
                      </button>
                    </div>
                  ) : null}
                  <TextField
                    label="Year of manufacture"
                    type="number"
                    min={1980}
                    max={2100}
                    value={vehicleYear}
                    onChange={(e) => setVehicleYear(e.target.value)}
                  />
                  <TextField
                    label="Engine rating (cc)"
                    type="number"
                    min={0}
                    value={engineRating}
                    onChange={(e) => setEngineRating(e.target.value)}
                  />
                  <TextField
                    label="Make / model"
                    value={`${selectedMake?.name ?? "—"} / ${selectedModel?.name ?? "—"}`}
                    disabled
                    readOnly
                  />
                  <TextField
                    label="Sum insured (on certificate)"
                    value={sumInsured ? money(sumInsured) : "—"}
                    disabled
                    readOnly
                  />
                  <TextField
                    label="Agent / IRA"
                    value={`${resolvedAgentCode || "env default"} · IRA ${
                      selectedIntermediary?.kra_pin || "—"
                    }`}
                    disabled
                    readOnly
                  />
                </div>
                {submitIssuance.isError ? (
                  <FormError title="Proposal failed">
                    {(submitIssuance.error as Error).message}
                  </FormError>
                ) : null}
              </div>
            </Modal>
          </div>
        </div>
      ) : null}

      {step === "pay" ? (
        <div className="quote-body">
          <div className="quote-panel">
            <div className="quote-panel-head quote-panel-head--toolbar">
              {guest ? null : (
                <div className="quote-panel-copy">
                  <h2>{payFlowActive ? payTrackHeadline : "Pay premium"}</h2>
                </div>
              )}
              {stepsNav}
            </div>

            {payFlowActive ? (
              <div className="pay-progress" aria-live="polite">
                <div className="pay-progress-meta">
                  <div>
                    <p className="quote-selection-label">
                      {payMethod === "BIRDVIEW"
                        ? "BirdView"
                        : payMethod === "DEFINITE_MPESA"
                          ? "Definite M-Pesa"
                          : "Definite Wallet"}{" "}
                      · amount due
                    </p>
                    <strong>{money(amountDue)}</strong>
                    <span>
                      {submitResult?.policy.policy_number ?? "Policy"}
                      {submitResult
                        ? ` · ${submitResult.policy.vehicle_registration ?? registration}`
                        : ""}
                    </span>
                  </div>
                  {!payFlowComplete &&
                  !(mpesaWait === "failed" || payIssuance.isError) &&
                  (payIssuance.isPending ||
                    mpesaWait === "waiting" ||
                    mpesaWait === "finishing") ? (
                    <span className="pay-progress-live">Working</span>
                  ) : payFlowComplete ? (
                    <span className="pay-progress-live pay-progress-live--done">Complete</span>
                  ) : mpesaWait === "failed" || payIssuance.isError ? (
                    <span className="pay-progress-live pay-progress-live--error">Needs action</span>
                  ) : null}
                </div>

                <ol className="pay-progress-steps">
                  {payTrackSteps.map((item, index) => (
                    <li
                      key={item.id}
                      className={`pay-progress-step pay-progress-step--${item.status}`}
                    >
                      <div className="pay-progress-marker" aria-hidden="true">
                        {item.status === "done" ? (
                          <IconCheck />
                        ) : item.status === "active" ? (
                          <span className="pay-progress-spinner" />
                        ) : item.status === "error" ? (
                          <span className="pay-progress-error-mark">!</span>
                        ) : (
                          <span className="pay-progress-index">{index + 1}</span>
                        )}
                      </div>
                      <div className="pay-progress-copy">
                        <strong>{item.title}</strong>
                        <span>{item.detail}</span>
                      </div>
                    </li>
                  ))}
                </ol>

                <div className="pay-progress-footer">
                  {mpesaWait === "failed" || payIssuance.isError ? (
                    <>
                      <FormError
                        title={
                          payConfirmed || payResult?.payment?.status === "SUCCESS"
                            ? "Certificate not issued yet"
                            : "Payment failed"
                        }
                      >
                        {mpesaMessage ||
                          (payIssuance.error instanceof Error
                            ? payIssuance.error.message
                            : "Please try again later.")}
                      </FormError>
                      <div className="quote-actions" style={{ marginTop: 0 }}>
                        <button type="button" className="secondary" onClick={cancelPayFlow}>
                          Back
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            if (payConfirmed || payResult?.payment?.status === "SUCCESS") {
                              retryCertificateIssuance();
                              return;
                            }
                            setPayFlowActive(false);
                            setPayOpen(true);
                          }}
                        >
                          {payConfirmed || payResult?.payment?.status === "SUCCESS"
                            ? "Issue cert"
                            : "Retry"}
                        </button>
                      </div>
                    </>
                  ) : payFlowComplete && !KYC_DOCS_ENABLED ? (
                    <div className="quote-actions" style={{ marginTop: "0.85rem" }}>
                      <p className="pay-progress-footnote">Cover issued. Opening your certificate…</p>
                      <button
                        type="button"
                        onClick={() => {
                          clearPayAdvanceTimer();
                          setPayFlowActive(false);
                          setPayFlowComplete(false);
                          goTo("certificate");
                        }}
                      >
                        Continue
                      </button>
                    </div>
                  ) : payFlowComplete ? (
                    <div className="kyc-upload-panel">
                      <p className="pay-progress-footnote">
                        Upload the vehicle logbook and both sides of the national ID. We save
                        them securely, then you can preview the certificate.
                      </p>
                      <div className="kyc-upload-grid">
                        {(
                          [
                            { kind: "logbook" as const, label: "Log book", hint: "Vehicle logbook photo or PDF" },
                            { kind: "id_front" as const, label: "ID front", hint: "National ID · front" },
                            { kind: "id_back" as const, label: "ID back", hint: "National ID · back" },
                          ] as const
                        ).map((slot) => {
                          const ready = Boolean(kycDocs[slot.kind]);
                          const busy = kycUploading === slot.kind;
                          return (
                            <label
                              key={slot.kind}
                              className={`kyc-upload-slot${ready ? " is-ready" : ""}${busy ? " is-busy" : ""}`}
                            >
                              <input
                                type="file"
                                accept="image/jpeg,image/png,image/webp,application/pdf"
                                disabled={busy || !customer?.id}
                                onChange={(e) => {
                                  const file = e.target.files?.[0] ?? null;
                                  e.target.value = "";
                                  void uploadKycDoc(slot.kind, file);
                                }}
                              />
                              <span className="kyc-upload-slot-icon" aria-hidden="true">
                                {ready ? <IconCheck /> : busy ? <span className="pay-progress-spinner" /> : null}
                              </span>
                              <span className="kyc-upload-slot-copy">
                                <strong>{slot.label}</strong>
                                <em>{ready ? "Uploaded" : busy ? "Uploading…" : slot.hint}</em>
                              </span>
                            </label>
                          );
                        })}
                      </div>
                      {kycError ? <FormError title="Upload failed">{kycError}</FormError> : null}
                      <div className="quote-actions" style={{ marginTop: "0.85rem" }}>
                        <button
                          type="button"
                          disabled={!kycDocsReady || !customer?.id}
                          onClick={() => {
                            clearPayAdvanceTimer();
                            setPayFlowActive(false);
                            setPayFlowComplete(false);
                            goTo("certificate");
                          }}
                        >
                          Continue
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="pay-receipt-reconcile">
                      <p className="pay-progress-footnote">
                        {mpesaWait === "waiting"
                          ? guest
                            ? payMethod === "BIRDVIEW"
                              ? "Approve the prompt on your phone. This page updates when BirdView confirms the payment."
                              : "Approve the prompt on your phone. This page updates when Definite confirms the payment."
                            : canReconcileReceipt
                              ? "Approve the prompt on your phone. If you already paid, enter the M-Pesa receipt from your SMS."
                              : payMethod === "BIRDVIEW"
                                ? "Approve the prompt on your phone. This page updates when BirdView confirms the payment."
                                : "Approve the prompt on your phone. This page updates when Definite confirms the payment."
                          : "Please wait. This usually takes a few seconds."}
                      </p>
                      {!guest && canReconcileReceipt && mpesaWait === "waiting" && payResult?.payment?.id ? (
                        <div className="pay-receipt-row">
                          <label className="config-field">
                            <span>M-Pesa receipt</span>
                            <input
                              value={mpesaReceipt}
                              onChange={(e) => setMpesaReceipt(e.target.value.toUpperCase())}
                              placeholder="e.g. UICEG6L9A3"
                              autoComplete="off"
                              spellCheck={false}
                            />
                          </label>
                          <button
                            type="button"
                            disabled={receiptConfirming || mpesaReceipt.trim().length < 6}
                            onClick={() => void confirmPaidWithReceipt()}
                          >
                            {receiptConfirming ? "Confirming…" : "Confirm payment"}
                          </button>
                        </div>
                      ) : null}
                      {mpesaMessage && mpesaWait === "waiting" ? (
                        <p className="pay-progress-footnote">{mpesaMessage}</p>
                      ) : null}
                      {!paymentLocked && (payIssuance.isPending || mpesaWait === "waiting") ? (
                        <div className="quote-actions" style={{ marginTop: "0.85rem" }}>
                          <button type="button" className="secondary" onClick={cancelPayFlow}>
                            Cancel
                          </button>
                          {mpesaWait === "waiting" ? (
                            <button type="button" onClick={startPayFlow}>
                              Resend
                            </button>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="quote-selection-card quote-selection-card--pay">
                <div className="quote-pay-summary">
                  <p className="quote-selection-label">Amount due</p>
                  <strong>
                    <em>KES</em> {money(amountDue)}
                  </strong>
                  <span>
                    {submitResult?.policy.policy_number ?? "No policy yet"}
                    {submitResult
                      ? ` · ${submitResult.policy.vehicle_registration ?? registration}`
                      : ""}
                  </span>
                  {payMethod === "BIRDVIEW" && referralCost > 0 ? (
                    <span className="quote-referral-credit">
                      Includes KES {money(referralCost)} monthly referral cost
                    </span>
                  ) : null}
                  {referralDiscount > 0 ? (
                    <span className="quote-referral-credit">
                      Referral credit −KES {money(referralDiscount)} applied
                    </span>
                  ) : Number(submitResult?.referral?.discount ?? 0) > 0 ? (
                    <span className="quote-referral-credit">
                      Pay with M-Pesa (BirdView) to use KES{" "}
                      {money(submitResult?.referral?.discount)} referral credit
                    </span>
                  ) : null}
                </div>
                <div className="quote-actions quote-pay-actions">
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => {
                      setStep("vehicle");
                      setVehicleOpen(true);
                    }}
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    onClick={() => setPayOpen(true)}
                    disabled={!submitResult?.policy?.id}
                  >
                    {payResult?.payment.status === "SUCCESS" ? "View payment" : "Pay now"}
                  </button>
                </div>
              </div>
            )}

            <Modal
              open={payOpen && !payFlowActive}
              size="xl"
              panelClassName={quoteModalPanelClass}
              icon={<IconWallet />}
              title="Pay premium"
              subtitle="Choose how to settle cover and issue the certificate."
              onClose={() => setPayOpen(false)}
              footer={
                <>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => {
                      setPayOpen(false);
                      setStep("vehicle");
                      setVehicleOpen(true);
                    }}
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    disabled={!submitResult || summaryPdfBusy}
                    onClick={() => void downloadSummaryPdf()}
                  >
                    {summaryPdfBusy ? "Preparing…" : "PDF"}
                  </button>
                  <button
                    type="button"
                    disabled={!submitResult?.policy?.id || payIssuance.isPending}
                    onClick={startPayFlow}
                  >
                    {`Pay ${money(amountDue)}`}
                  </button>
                </>
              }
            >
              <div className="modal-cover">
                {submitResult ? (
                  <>
                    <div className="cover-calc-summary">
                      <div>
                        <span>Cover</span>
                        <strong>
                          {formatProductLabel(
                            product?.cover_options.find((opt) => opt.id === coverOptionId)?.name ??
                              "Selected cover",
                          )}
                        </strong>
                      </div>
                      <div>
                        <span>Period</span>
                        <strong>
                          {COVER_PERIODS.find((p) => p.value === coverPeriod)?.label ?? coverPeriod}
                        </strong>
                      </div>
                      <div>
                        <span>Sum insured</span>
                        <strong>{money(sumInsured)}</strong>
                      </div>
                      <div>
                        <span>Vehicle</span>
                        <strong>
                          {selectedMake?.name ?? "—"} / {selectedModel?.name ?? "—"}
                        </strong>
                      </div>
                      <div>
                        <span>Registration</span>
                        <strong>
                          {submitResult.policy.vehicle_registration ?? registration}
                        </strong>
                      </div>
                      <div>
                        <span>Policy</span>
                        <strong className="mono">{submitResult.policy.policy_number}</strong>
                      </div>
                    </div>

                    {premium.data ? (
                      <div className="premium-breakdown modal-premium">
                        <div className="premium-breakdown-head">
                          <h3>Premium</h3>
                          <span>KES</span>
                        </div>
                        <dl>
                          <div>
                            <dt>Basic</dt>
                            <dd>{money(premium.data.premium.basic_premium)}</dd>
                          </div>
                          <div>
                            <dt>PHCF</dt>
                            <dd>{money(premium.data.premium.phcf)}</dd>
                          </div>
                          <div>
                            <dt>Training levy</dt>
                            <dd>{money(premium.data.premium.training_levy)}</dd>
                          </div>
                          <div>
                            <dt>Stamp duty</dt>
                            <dd>{money(premium.data.premium.stamp_duty)}</dd>
                          </div>
                          <div className="premium-gross">
                            <dt>Gross premium</dt>
                            <dd>{money(premium.data.premium.gross_premium)}</dd>
                          </div>
                        </dl>
                      </div>
                    ) : null}

                    <div className="pay-summary">
                      <dl className="pay-summary-meta">
                        {referralCost > 0 ? (
                          <div>
                            <dt>Referral cost</dt>
                            <dd>
                              <em>KES</em> {money(referralCost)}
                            </dd>
                          </div>
                        ) : null}
                        {referralDiscount > 0 ? (
                          <div>
                            <dt>Referral credit</dt>
                            <dd>
                              −<em>KES</em> {money(referralDiscount)}
                            </dd>
                          </div>
                        ) : null}
                        <div>
                          <dt>Provider note</dt>
                          <dd className="mono">
                            {String(submitResult.provider.document_number ?? "—")}
                          </dd>
                        </div>
                      </dl>
                      <div className="pay-summary-amount">
                        <span>Amount due</span>
                        <strong>
                          <em>KES</em> {money(amountDue)}
                        </strong>
                      </div>
                    </div>
                    {summaryPdfError ? (
                      <FormError title="PDF not created">{summaryPdfError}</FormError>
                    ) : null}
                  </>
                ) : (
                  <FormError title="No policy yet">
                    Complete the vehicle step first.
                  </FormError>
                )}

                <div className="form-grid modal-form-grid">
                                    <Select
                    label="Payment method"
                    value={payMethod}
                    onChange={(next) =>
                      setPayMethod(next as "DEFINITE_WALLET" | "DEFINITE_MPESA" | "BIRDVIEW")
                    }
                    options={
                      guest
                        ? [{ value: "BIRDVIEW", label: "BirdView M-Pesa Push" }]
                        : [
                            { value: "BIRDVIEW", label: "BirdView M-Pesa Push" },
                            { value: "DEFINITE_MPESA", label: "Definite M-Pesa Push" },
                            ...(canPayFromFloat
                              ? [
                                  {
                                    value: "DEFINITE_WALLET",
                                    label: "Definite Wallet (agency float)",
                                  },
                                ]
                              : []),
                          ]
                    }
                  />
                  {payMethod === "DEFINITE_MPESA" || payMethod === "BIRDVIEW" ? (
                    <PhoneField
                      label={
                        payMethod === "BIRDVIEW"
                          ? "BirdView phone"
                          : "Definite M-Pesa phone"
                      }
                      value={mpesaPhone}
                      onChange={setMpesaPhone}
                      country={mpesaCountry}
                      onCountryChange={setMpesaCountry}
                      placeholder={phone || undefined}
                    />
                  ) : (
                    <p className="pay-method-note">
                      Deducts once from the Definite agency wallet, then issues the certificate.
                    </p>
                  )}
                </div>

                {payIssuance.isError ? (
                  <FormError
                    title={
                      payResult?.payment?.status === "SUCCESS"
                        ? "Certificate not issued yet"
                        : "Payment failed"
                    }
                  >
                    {(payIssuance.error as Error).message}
                  </FormError>
                ) : null}
              </div>
            </Modal>
          </div>
        </div>
      ) : null}

      {step === "certificate" ? (
        <div className="quote-body">
          <div className="quote-panel quote-certificate">
            <div className="quote-panel-head quote-panel-head--toolbar">
              {guest ? null : (
                <div className="quote-panel-copy">
                  <h2>
                    {payResult?.certificate
                      ? "Cover issued"
                      : payResult?.payment.status === "SUCCESS"
                        ? "Almost there"
                        : "Certificate"}
                  </h2>
                  <p>
                    {payResult?.certificate
                      ? pdfState === "ready"
                        ? "Your PDF is ready to open."
                        : "Active cover. Preparing your PDF."
                      : "Finish payment to get your PDF."}
                  </p>
                </div>
              )}
              {stepsNav}
            </div>

            {payResult?.certificate ? (
              <div className="cert-result" aria-live="polite">
                <div className="cert-result-meta">
                  <div>
                    <p className="quote-selection-label">Certificate</p>
                    <strong className="mono">
                      {payResult.certificate.certificate_number ||
                        payResult.certificate.external_certificate_ref ||
                        payResult.certificate.id}
                    </strong>
                    <span>
                      {payResult.policy.policy_number}
                      {submitResult?.policy.vehicle_registration || registration
                        ? ` · ${submitResult?.policy.vehicle_registration ?? registration}`
                        : ""}
                    </span>
                  </div>
                  <span className="pay-progress-live pay-progress-live--done">Issued</span>
                </div>

                <dl className="cert-result-grid">
                  <div>
                    <dt>Policy status</dt>
                    <dd>{payResult.policy.status}</dd>
                  </div>
                  <div>
                    <dt>Payment</dt>
                    <dd>
                      {payResult.payment.status}
                      {payResult.payment.method ? ` · ${payResult.payment.method}` : ""}
                    </dd>
                  </div>
                </dl>

                {payResult.certificate.id ? (
                  <div
                    className={
                      pdfState === "ready"
                        ? "cert-pdf-row cert-pdf-row--ready"
                        : pdfState === "error"
                          ? "cert-pdf-row cert-pdf-row--error"
                          : "cert-pdf-row cert-pdf-row--busy"
                    }
                  >
                    <div className="cert-pdf-thumb" aria-hidden="true">
                      {pdfState === "ready" ? (
                        <span className="cert-pdf-check">
                          <IconCheck />
                        </span>
                      ) : pdfState === "error" ? (
                        <span className="pay-progress-error-mark">!</span>
                      ) : (
                        <span className="cert-pdf-sheet-spinner" />
                      )}
                    </div>
                    <div className="cert-pdf-copy">
                      <strong>
                        {pdfState === "ready"
                          ? "PDF ready"
                          : pdfState === "error"
                            ? "Still waiting on PDF"
                            : pdfState === "opening"
                              ? "Opening PDF"
                              : "Preparing PDF"}
                      </strong>
                      <span>{pdfMessage || "Preparing your certificate PDF…"}</span>
                    </div>
                  </div>
                ) : (
                  <p className="cert-result-note">
                    Certificate is recorded. The downloadable PDF link is still being prepared.
                  </p>
                )}

                <div className="cert-result-footer">
                  <div className="quote-actions" style={{ marginTop: 0 }}>
                    <button type="button" className="secondary" onClick={() => setStep("pay")}>
                      Back to pay
                    </button>
                    <button type="button" className="secondary" onClick={resetQuote}>
                      Start another quote
                    </button>
                    {payResult.certificate.id ? (
                      <button
                        type="button"
                        disabled={pdfState === "preparing" || pdfState === "opening"}
                        onClick={() => {
                          void openCertificatePdf();
                        }}
                      >
                        {pdfState === "preparing"
                          ? "Waiting for PDF…"
                          : pdfState === "opening"
                            ? "Opening…"
                            : pdfState === "error"
                              ? "Try open again"
                              : "Open certificate PDF"}
                      </button>
                    ) : null}
                  </div>
                  {payResult.certificate.id && pdfState === "error" ? (
                    <button
                      type="button"
                      className="cert-result-link"
                      onClick={() => setPdfRetryKey((k) => k + 1)}
                    >
                      Keep waiting for PDF
                    </button>
                  ) : null}
                </div>
              </div>
            ) : (
              <div className="cert-result cert-result--empty">
                <p className="cert-result-note">
                  {payResult?.payment.status === "SUCCESS"
                    ? "Payment succeeded but the certificate is still generating. Stay on this step or check Certificates in the app."
                    : "Complete payment to activate the policy and generate the certificate."}
                </p>
                <div className="quote-actions" style={{ marginTop: 0 }}>
                  <button type="button" className="secondary" onClick={() => setStep("pay")}>
                    Back to pay
                  </button>
                  <button type="button" onClick={resetQuote}>
                    Start another quote
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : null}

      <Modal
        open={pdfPreviewOpen && Boolean(pdfPreviewBlob)}
        title="Certificate PDF"
        subtitle={
          payResult?.certificate?.certificate_number ||
          payResult?.certificate?.external_certificate_ref ||
          "Preview"
        }
        icon={<IconCertificate />}
        size="fit"
        panelClassName={quoteModalPanelClass}
        bodyClassName="modal-body--pdf"
        onClose={() => setPdfPreviewOpen(false)}
        footer={
          <>
            <button type="button" className="secondary" onClick={() => setPdfPreviewOpen(false)}>
              Close
            </button>
            <button type="button" onClick={downloadCertificatePdf}>
              Download PDF
            </button>
          </>
        }
      >
        {pdfPreviewBlob ? <PdfPreview data={pdfPreviewBlob} /> : null}
      </Modal>
    </section>
  );
}
