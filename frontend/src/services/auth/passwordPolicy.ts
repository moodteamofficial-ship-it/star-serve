// Mirrors the backend password policy (min length + denylist).
const FORBIDDEN_PASSWORDS = new Set(["111111", "123456", "password", "qwerty", "abcdef"]);

export function passwordStrengthError(password: string): string | null {
  const value = password || "";
  if (FORBIDDEN_PASSWORDS.has(value) || FORBIDDEN_PASSWORDS.has(value.toLowerCase())) {
    return "This password is not allowed";
  }
  if (value.length < 6) {
    return "Password must be at least 6 characters";
  }
  return null;
}
