import type { CatalogCategory, CatalogProduct, CatalogResponse } from "@/services/insurance/insuranceApi";

/** Display order for Definite motor classes on the quote welcome grid. */
const CATEGORY_ORDER = [
  "Tuk Tuk",
  "Motor PSV",
  "Cars",
  "Motorcycle",
  "Motor Commercial",
  "Private Hire",
] as const;

/**
 * Re-classify products whose provider category lagged behind name-based rules
 * (e.g. staging still filing TUK TUK under Motor PSV / Motor Commercial).
 */
export function categoryFromProductName(name: string, fallback: string): string {
  const upper = name.replace(/\s+/g, " ").trim().toUpperCase();
  const tokens = new Set(
    upper.replace(/[-()/,]/g, " ").split(/\s+/).filter(Boolean),
  );
  if (tokens.has("TUK") || tokens.has("TUKTUK")) return "Tuk Tuk";
  return fallback || "Other";
}

function flattenProducts(catalog: CatalogResponse): CatalogProduct[] {
  if (catalog.products?.length) return catalog.products;
  return (catalog.categories ?? []).flatMap((group) => group.products ?? []);
}

export function withNormalizedCategories(catalog: CatalogResponse): CatalogResponse {
  const products = flattenProducts(catalog).map((product) => ({
    ...product,
    category: categoryFromProductName(product.name, product.category),
  }));

  const groups = new Map<string, CatalogProduct[]>();
  for (const product of products) {
    const list = groups.get(product.category) ?? [];
    list.push(product);
    groups.set(product.category, list);
  }

  const ordered = [
    ...CATEGORY_ORDER.filter((key) => groups.has(key)),
    ...[...groups.keys()].filter((key) => !(CATEGORY_ORDER as readonly string[]).includes(key)).sort(),
  ];

  const categories: CatalogCategory[] = ordered.map((category) => {
    const rows = groups.get(category) ?? [];
    return {
      category,
      product_count: rows.length,
      products: rows,
    };
  });

  return { ...catalog, products, categories };
}
