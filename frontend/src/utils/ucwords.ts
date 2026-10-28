/** Title-case labels from enum / snake_case / dot.notation values. */
export function ucwords(value: string | null | undefined): string {
  if (!value) return "";
  return value
    .replace(/[._·]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
