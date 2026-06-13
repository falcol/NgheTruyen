"use client";

import { usePathname } from "next/navigation";
import TopNav from "./TopNav";

const READER_ROUTES = [
  /^\/read\/[^/]+\/\d+/,
  /^\/epub\/[^/]+\/read\/\d+/,
];

export default function NavWrapper({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isReader = READER_ROUTES.some((p) => p.test(pathname));

  if (isReader) {
    return <div className="relative z-10">{children}</div>;
  }

  return (
    <>
      <TopNav />
      <div className="relative z-10 pt-14">{children}</div>
    </>
  );
}
