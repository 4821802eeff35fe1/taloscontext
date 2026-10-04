import { Link, type LinkProps } from "@tanstack/react-router";

/** Thin wrapper around TanStack Router's Link with a loosened `to` type.
 * The app's routes are built dynamically in App.tsx via a small helper, which
 * defeats the router's literal-path type inference for Link consumers in
 * other files — this wrapper avoids fighting that on every call site.
 */
export function AppLink(
  props: Omit<LinkProps, "to"> & { to: string; className?: string },
) {
  return <Link {...(props as LinkProps)} />;
}
