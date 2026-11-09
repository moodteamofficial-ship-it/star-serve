import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { EnquiryForm } from "@/features/marketing/EnquiryForm";
import { MarketingInnerSkeleton } from "@/features/marketing/MarketingSkeletons";
import { SectionRenderer } from "@/features/marketing/sections/SectionRenderer";
import { websiteApi } from "@/services/website/websiteApi";

const SLUG_BY_PARAM: Record<string, string> = {
  services: "services",
  about: "about",
  "get-covered": "get-covered",
};

export function MarketingInnerPage() {
  const { pageSlug = "" } = useParams();
  const apiSlug = SLUG_BY_PARAM[pageSlug];

  const { data, isLoading, isError } = useQuery({
    queryKey: ["website", "page", apiSlug],
    queryFn: async () => (await websiteApi.page(apiSlug!)).data,
    enabled: Boolean(apiSlug),
    staleTime: 5 * 60_000,
    gcTime: 30 * 60_000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  useEffect(() => {
    if (data?.meta_title) document.title = data.meta_title;
    else if (data?.title) document.title = `${data.title} | Star Serve`;
  }, [data]);

  if (!apiSlug) {
    return <main className="mkt-main mkt-main--centered">Page not found.</main>;
  }

  if (isLoading) {
    const variant =
      apiSlug === "about" ? "about" : apiSlug === "services" ? "services" : "default";
    return <MarketingInnerSkeleton variant={variant} />;
  }
  if (isError || !data) {
    return <main className="mkt-main mkt-main--centered">Page not found.</main>;
  }

  return (
    <main className="mkt-main">
      {data.sections.map((section) => (
        <SectionRenderer key={section.key} section={section} />
      ))}
      {apiSlug === "get-covered" ? <EnquiryForm /> : null}
    </main>
  );
}
