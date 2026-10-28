import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type ReactNode, type SVGProps } from "react";
import { useAuth } from "@/app/providers/AuthProvider";
import { AnimatedFormError } from "@/components/ui/AnimatedFormError";
import { IconAlert, IconBox, IconChevronRight, IconSearch } from "@/components/ui/icons";
import { ApiError } from "@/services/api/client";
import { insuranceApi } from "@/services/insurance/insuranceApi";
import { productApi, type Product, type VehicleMake } from "@/services/products/productApi";

const PAGE_SIZE = 10;

type CatalogTab = "products" | "makes";

function IconChevronLeft(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="1em"
      height="1em"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="m14.5 6-6 6 6 6" />
    </svg>
  );
}

function ucwords(value: string | null | undefined) {
  if (!value) return "";
  return value
    .replace(/_/g, " ")
    .trim()
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function scopeLabel(scope: string) {
  return ucwords(scope);
}

function scopeTone(scope: string) {
  const key = scope.trim().toUpperCase();
  if (key === "PLATFORM") return "active";
  if (key === "TENANT") return "suspended";
  return "neutral";
}

function formatShortDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function DirectoryCard({
  children,
  footer,
}: {
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="config-card config-card--scene">
      <div className="config-card-body">{children}</div>
      {footer ? <div className="config-card-footer">{footer}</div> : null}
    </div>
  );
}

function DirectorySkeleton({
  tab,
  count = 5,
}: {
  tab: CatalogTab;
  count?: number;
}) {
  return (
    <div className="customers-table-wrap" aria-busy="true">
      <table className="customers-table products-table">
        <thead>
          <tr>
            <th scope="col">{tab === "products" ? "Product" : "Make"}</th>
            <th scope="col">Code</th>
            <th scope="col">Scope</th>
            <th scope="col">{tab === "products" ? "Cover" : "Order"}</th>
            {tab === "products" ? <th scope="col">Synced</th> : null}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: count }, (_, index) => (
            <tr key={`products-skeleton-${index}`} className="customers-table-row--skeleton">
              <td>
                <div className="customers-table-person">
                  <span className="skeleton-block customers-avatar-skeleton" />
                  <div className="customers-table-person-text">
                    <span className="skeleton-block skeleton-block--title" />
                    <span className="skeleton-block customers-meta-skeleton" />
                  </div>
                </div>
              </td>
              <td>
                <span className="skeleton-block skeleton-block--meta" />
              </td>
              <td>
                <span className="skeleton-block customers-status-skeleton" />
              </td>
              <td>
                <span className="skeleton-block skeleton-block--meta" />
              </td>
              {tab === "products" ? (
                <td>
                  <span className="skeleton-block skeleton-block--meta" />
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ProductsPage() {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<CatalogTab>("products");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [syncError, setSyncError] = useState<string | null>(null);

  useEffect(() => {
    setPage(1);
  }, [q, tab]);

  const canManage = hasPermission("product:manage");

  const products = useQuery({
    queryKey: ["products"],
    queryFn: async () => (await productApi.listProducts()).data,
  });
  const makes = useQuery({
    queryKey: ["vehicle-makes"],
    queryFn: async () => (await productApi.listMakes()).data,
  });

  const sync = useMutation({
    mutationFn: () => insuranceApi.syncReference(),
    onMutate: () => {
      setSyncError(null);
    },
    onSuccess: async () => {
      setSyncError(null);
      await queryClient.invalidateQueries({ queryKey: ["products"] });
      await queryClient.invalidateQueries({ queryKey: ["vehicle-makes"] });
    },
    onError: (err) => {
      setSyncError(err instanceof ApiError ? err.message : "Sync failed");
    },
  });

  const productItems = products.data ?? [];
  const makeItems = makes.data ?? [];
  const platformCount =
    productItems.filter((row) => row.scope === "PLATFORM").length +
    makeItems.filter((row) => row.scope === "PLATFORM").length;
  const tenantCount =
    productItems.filter((row) => row.scope === "TENANT").length +
    makeItems.filter((row) => row.scope === "TENANT").length;

  const filteredProducts = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return productItems;
    return productItems.filter((row) => {
      const cover = (row.cover_options ?? []).join(" ").toLowerCase();
      return (
        row.name.toLowerCase().includes(needle) ||
        row.code.toLowerCase().includes(needle) ||
        cover.includes(needle) ||
        row.scope.toLowerCase().includes(needle)
      );
    });
  }, [productItems, q]);

  const filteredMakes = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return makeItems;
    return makeItems.filter(
      (row) =>
        row.name.toLowerCase().includes(needle) ||
        row.code.toLowerCase().includes(needle) ||
        row.scope.toLowerCase().includes(needle),
    );
  }, [makeItems, q]);

  const activeRows: Array<Product | VehicleMake> =
    tab === "products" ? filteredProducts : filteredMakes;
  const total = activeRows.length;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const rangeStart = total === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
  const rangeEnd = total === 0 ? 0 : Math.min(safePage * PAGE_SIZE, total);
  const canPrev = safePage > 1;
  const canNext = safePage < totalPages;
  const pageRows = activeRows.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const loading =
    tab === "products"
      ? products.isLoading && !products.data
      : makes.isLoading && !makes.data;
  const errored = tab === "products" ? products.isError : makes.isError;

  const footer = (
    <div className="customers-footer">
      <div className="customers-pager-meta customers-footer-range">
        {total === 0 ? "0 of 0" : `${rangeStart}–${rangeEnd} of ${total}`}
      </div>
      <div className="customers-pager" aria-label="Catalog pagination">
        <button
          type="button"
          className="customers-pager-btn"
          aria-label="Previous page"
          disabled={!canPrev}
          onClick={() => setPage((p) => Math.max(1, p - 1))}
        >
          <IconChevronLeft />
        </button>
        <span className="customers-pager-page" aria-current="page">
          {safePage}
        </span>
        <button
          type="button"
          className="customers-pager-btn"
          aria-label="Next page"
          disabled={!canNext}
          onClick={() => setPage((p) => p + 1)}
        >
          <IconChevronRight />
        </button>
      </div>
    </div>
  );

  return (
    <section className="config-page customers-page products-page">
      <h1 className="config-title">Insurance products</h1>

      <div className="customers-top">
        <div className="customers-stat-grid" aria-live="polite">
          <article className="customers-stat-card">
            <span className="customers-stat-label">Products</span>
            <strong className="customers-stat-value">
              {productItems.length.toLocaleString()}
            </strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Vehicle makes</span>
            <strong className="customers-stat-value">
              {makeItems.length.toLocaleString()}
            </strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Platform</span>
            <strong className="customers-stat-value">{platformCount.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Tenant</span>
            <strong className="customers-stat-value">{tenantCount.toLocaleString()}</strong>
          </article>
        </div>

        <div className="customers-search-card">
          <div className="products-tabs" role="tablist" aria-label="Catalog">
            <button
              type="button"
              role="tab"
              aria-selected={tab === "products"}
              className={`products-tab${tab === "products" ? " is-active" : ""}`}
              onClick={() => setTab("products")}
            >
              Products
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === "makes"}
              className={`products-tab${tab === "makes" ? " is-active" : ""}`}
              onClick={() => setTab("makes")}
            >
              Vehicle makes
            </button>
          </div>
          <label className="config-field customers-search">
            <span className="config-sr-only">Search catalog</span>
            <span className="customers-search-shell">
              <IconSearch className="customers-search-icon" />
              <input
                type="search"
                placeholder={
                  tab === "products"
                    ? "Search product name or code"
                    : "Search make name or code"
                }
                value={q}
                onChange={(e) => setQ(e.target.value)}
                autoComplete="off"
              />
            </span>
          </label>
          {canManage ? (
            <button
              type="button"
              className="config-btn customers-toolbar-add"
              disabled={sync.isPending}
              onClick={() => {
                setSyncError(null);
                sync.mutate();
              }}
            >
              {sync.isPending ? "Syncing…" : "Sync"}
            </button>
          ) : null}
        </div>
        <AnimatedFormError error={syncError} title="Sync failed" />
      </div>

      <div className="config-stage config-stage--fill">
        <DirectoryCard footer={footer}>
          {loading ? <DirectorySkeleton tab={tab} /> : null}

          {errored ? (
            <div className="customers-empty" role="alert">
              <span className="customers-empty-icon is-error" aria-hidden="true">
                <IconAlert />
              </span>
              <p className="customers-empty-title">Couldn’t load catalog</p>
              <p className="customers-empty-copy">Try again in a moment.</p>
            </div>
          ) : null}

          {!loading && !errored ? (
            pageRows.length > 0 ? (
              <div className="customers-table-wrap">
                <table
                  className={`customers-table products-table${
                    tab === "products" ? " products-table--products" : " products-table--makes"
                  }`}
                >
                  <thead>
                    <tr>
                      <th scope="col">{tab === "products" ? "Product" : "Make"}</th>
                      <th scope="col">Code</th>
                      <th scope="col">Scope</th>
                      <th scope="col">{tab === "products" ? "Cover" : "Order"}</th>
                      {tab === "products" ? <th scope="col">Synced</th> : null}
                    </tr>
                  </thead>
                  <tbody>
                    {tab === "products"
                      ? (pageRows as Product[]).map((row) => (
                          <tr key={row.id}>
                            <td>
                              <div className="customers-table-person">
                                <span
                                  className="customers-avatar customers-avatar--empty"
                                  aria-hidden="true"
                                >
                                  <IconBox />
                                </span>
                                <div className="customers-table-person-text">
                                  <span className="customers-table-name">
                                    {ucwords(row.name)}
                                  </span>
                                  {row.provider_code ? (
                                    <div className="customers-table-meta">
                                      <span className="customers-tag customers-tag--id">
                                        {ucwords(row.provider_code)}
                                      </span>
                                    </div>
                                  ) : null}
                                </div>
                              </div>
                            </td>
                            <td>
                              <span className="customers-tag customers-tag--id products-code">
                                {ucwords(row.code)}
                              </span>
                            </td>
                            <td>
                              <span
                                className={`customers-status-badge customers-status-badge--${scopeTone(row.scope)}`}
                              >
                                <span className="customers-status-dot__mark" aria-hidden="true" />
                                {scopeLabel(row.scope)}
                              </span>
                            </td>
                            <td>
                              <div className="products-cover-list">
                                {(row.cover_options ?? []).length > 0 ? (
                                  (row.cover_options ?? []).map((option) => (
                                    <span
                                      key={`${row.id}-${option}`}
                                      className="customers-tag customers-tag--kra"
                                    >
                                      {ucwords(option)}
                                    </span>
                                  ))
                                ) : (
                                  <span className="customers-date-badge">—</span>
                                )}
                              </div>
                            </td>
                            <td>
                              <span className="customers-date-badge">
                                {formatShortDate(row.synced_at)}
                              </span>
                            </td>
                          </tr>
                        ))
                      : (pageRows as VehicleMake[]).map((row) => (
                          <tr key={row.id}>
                            <td>
                              <div className="customers-table-person">
                                <span
                                  className="customers-avatar customers-avatar--empty"
                                  aria-hidden="true"
                                >
                                  <IconBox />
                                </span>
                                <div className="customers-table-person-text">
                                  <span className="customers-table-name">
                                    {ucwords(row.name)}
                                  </span>
                                  {row.provider_code ? (
                                    <div className="customers-table-meta">
                                      <span className="customers-tag customers-tag--id">
                                        {ucwords(row.provider_code)}
                                      </span>
                                    </div>
                                  ) : null}
                                </div>
                              </div>
                            </td>
                            <td>
                              <span className="customers-tag customers-tag--id products-code">
                                {ucwords(row.code)}
                              </span>
                            </td>
                            <td>
                              <span
                                className={`customers-status-badge customers-status-badge--${scopeTone(row.scope)}`}
                              >
                                <span className="customers-status-dot__mark" aria-hidden="true" />
                                {scopeLabel(row.scope)}
                              </span>
                            </td>
                            <td>
                              <span className="customers-metric-badge">{row.sort_order}</span>
                            </td>
                          </tr>
                        ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="customers-empty" role="status">
                <span className="customers-empty-icon" aria-hidden="true">
                  {q.trim() ? <IconSearch /> : <IconBox />}
                </span>
                <p className="customers-empty-title">
                  {q.trim()
                    ? "No matches"
                    : tab === "products"
                      ? "No products yet"
                      : "No vehicle makes yet"}
                </p>
                <p className="customers-empty-copy">
                  {q.trim()
                    ? "Try another name or code."
                    : canManage
                      ? "Sync from the provider to load the catalog."
                      : "Catalog is empty for this tenant."}
                </p>
              </div>
            )
          ) : null}
        </DirectoryCard>
      </div>
    </section>
  );
}
