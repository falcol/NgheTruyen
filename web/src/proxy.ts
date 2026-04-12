import { NextRequest, NextResponse } from "next/server";
import {
  isSiteBasicAuthConfigured,
  isValidBasicAuthAuthorization,
  SITE_BASIC_AUTH_PASSWORD_ENV_KEY,
  SITE_BASIC_AUTH_REALM,
  SITE_BASIC_AUTH_USER_ENV_KEY,
} from "@/lib/site-access";

function unauthorizedResponse() {
  return new NextResponse("Authentication required.", {
    status: 401,
    headers: {
      "WWW-Authenticate": `Basic realm="${SITE_BASIC_AUTH_REALM}", charset="UTF-8"`,
      "Cache-Control": "no-store",
    },
  });
}

export function proxy(request: NextRequest) {
  if (!isSiteBasicAuthConfigured()) {
    return new NextResponse(
      `Missing ${SITE_BASIC_AUTH_USER_ENV_KEY} or ${SITE_BASIC_AUTH_PASSWORD_ENV_KEY}.`,
      {
        status: 500,
        headers: {
          "Cache-Control": "no-store",
        },
      },
    );
  }

  if (isValidBasicAuthAuthorization(request.headers.get("authorization"))) {
    return NextResponse.next();
  }

  return unauthorizedResponse();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml).*)",
  ],
};
