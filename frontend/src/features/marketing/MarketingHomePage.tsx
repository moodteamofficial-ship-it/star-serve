import { useOutletContext } from "react-router-dom";
import { MarketingHomeSkeleton } from "@/features/marketing/MarketingSkeletons";
import { SectionRenderer } from "@/features/marketing/sections/SectionRenderer";
import type { WebsiteBootstrap } from "@/services/website/websiteApi";

type MarketingOutletContext = {
  bootstrap?: WebsiteBootstrap;
  bootstrapLoading?: boolean;
  bootstrapError?: boolean;
};

export function MarketingHomePage() {
  const { bootstrap, bootstrapLoading, bootstrapError } =
    useOutletContext<MarketingOutletContext>();
  const sections = bootstrap?.homepage?.sections ?? [];
  const hero = sections.find((section) => section.type === "hero");
  const rest = sections.filter((section) => section.type !== "hero");

  if (bootstrapLoading) {
    return <MarketingHomeSkeleton />;
  }
  if (bootstrapError || !bootstrap) {
    return (
      <main className="mkt-main mkt-main--centered">
        Could not load the marketing homepage. Check that the API is running on port 8000.
      </main>
    );
  }

  return (
    <>
      {hero ? (
        <div className="mkt-hero-stage">
          <SectionRenderer section={hero} />
        </div>
      ) : null}
      <main className="mkt-main">
        {rest.map((section) => (
          <SectionRenderer key={section.key} section={section} />
        ))}
      </main>
    </>
  );
}
