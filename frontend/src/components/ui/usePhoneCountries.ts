import { useQuery } from "@tanstack/react-query";
import { referenceApi } from "@/services/systemConfig/systemConfigApi";
import {
  DEFAULT_PHONE_COUNTRY,
  PHONE_COUNTRIES,
  type PhoneCountry,
} from "@/components/ui/phoneCountries";

const STALE_MS = 10 * 60 * 1000;

export function usePhoneCountries() {
  const query = useQuery({
    queryKey: ["phone-countries"],
    queryFn: async () => (await referenceApi.phoneCountries()).data,
    staleTime: STALE_MS,
  });

  const items = query.data?.items?.length ? query.data.items : [...PHONE_COUNTRIES];
  const defaultIso =
    query.data?.default_iso && items.some((row) => row.iso === query.data.default_iso)
      ? query.data.default_iso
      : items.find((row) => row.iso === DEFAULT_PHONE_COUNTRY)?.iso ??
        items[0]?.iso ??
        DEFAULT_PHONE_COUNTRY;

  return {
    countries: items as PhoneCountry[],
    defaultIso,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}
