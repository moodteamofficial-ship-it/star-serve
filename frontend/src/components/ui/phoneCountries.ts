export type PhoneCountry = {
  iso: string;
  name: string;
  dial: string;
};

/** Offline / fallback list when the DB catalog has not loaded yet. */
export const PHONE_COUNTRIES: readonly PhoneCountry[] = [
  { iso: "KE", name: "Kenya", dial: "254" },
  { iso: "UG", name: "Uganda", dial: "256" },
  { iso: "TZ", name: "Tanzania", dial: "255" },
  { iso: "RW", name: "Rwanda", dial: "250" },
  { iso: "BI", name: "Burundi", dial: "257" },
  { iso: "ET", name: "Ethiopia", dial: "251" },
  { iso: "SS", name: "South Sudan", dial: "211" },
  { iso: "SO", name: "Somalia", dial: "252" },
  { iso: "NG", name: "Nigeria", dial: "234" },
  { iso: "GH", name: "Ghana", dial: "233" },
  { iso: "ZA", name: "South Africa", dial: "27" },
  { iso: "AE", name: "United Arab Emirates", dial: "971" },
  { iso: "GB", name: "United Kingdom", dial: "44" },
  { iso: "US", name: "United States", dial: "1" },
  { iso: "IN", name: "India", dial: "91" },
  { iso: "CN", name: "China", dial: "86" },
] as const;

export const DEFAULT_PHONE_COUNTRY = "KE";

export function flagEmoji(iso: string): string {
  const code = iso.trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(code)) return "🏳️";
  return String.fromCodePoint(...[...code].map((c) => 127397 + c.charCodeAt(0)));
}

export function getPhoneCountry(
  iso: string,
  catalog: readonly PhoneCountry[] = PHONE_COUNTRIES,
): PhoneCountry {
  const list = catalog.length ? catalog : PHONE_COUNTRIES;
  return list.find((row) => row.iso === iso) ?? list[0] ?? PHONE_COUNTRIES[0];
}

/** Build E.164 from ISO country + national digits. */
export function toE164(
  iso: string,
  national: string,
  catalog: readonly PhoneCountry[] = PHONE_COUNTRIES,
): string {
  const country = getPhoneCountry(iso, catalog);
  let digits = national.replace(/\D/g, "");
  if (digits.startsWith("0")) digits = digits.slice(1);
  if (digits.startsWith(country.dial)) digits = digits.slice(country.dial.length);
  if (!digits) return "";
  return `+${country.dial}${digits}`;
}

/**
 * Drop a trunk leading 0 from national input.
 * - live: when the number reaches 10+ digits (e.g. 07XXXXXXXX → 7XXXXXXXX)
 * - blur: whenever a leading 0 is present
 */
export function normalizeNationalNumber(
  national: string,
  mode: "live" | "blur" = "blur",
): string {
  const digits = national.replace(/\D/g, "");
  if (!digits.startsWith("0")) return national;
  if (mode === "live" && digits.length < 10) return national;
  return digits.slice(1);
}

export function nationalPlaceholder(iso: string): string {
  switch (iso) {
    case "KE":
    case "UG":
    case "TZ":
      return "7XX XXX XXX";
    case "US":
      return "(555) 000-0000";
    case "GB":
      return "7400 000000";
    default:
      return "Phone number";
  }
}

export function fromE164(
  value: string | null | undefined,
  catalog: readonly PhoneCountry[] = PHONE_COUNTRIES,
): { iso: string; national: string } {
  const list = catalog.length ? catalog : PHONE_COUNTRIES;
  const fallback =
    list.find((row) => row.iso === DEFAULT_PHONE_COUNTRY)?.iso ??
    list[0]?.iso ??
    DEFAULT_PHONE_COUNTRY;
  const raw = (value ?? "").trim();
  if (!raw) return { iso: fallback, national: "" };
  const digits = raw.replace(/\D/g, "");
  const sorted = [...list].sort((a, b) => b.dial.length - a.dial.length);
  for (const country of sorted) {
    if (digits.startsWith(country.dial)) {
      return { iso: country.iso, national: digits.slice(country.dial.length) };
    }
  }
  return { iso: fallback, national: digits };
}
