import { describe, expect, it, vi, afterEach } from "vitest";
import {
  decodeBasicAuthHeader,
  isValidBasicAuthAuthorization,
  isSiteBasicAuthConfigured,
} from "@/lib/site-access";

describe("site access helpers", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("validates configured basic auth credentials", () => {
    vi.stubEnv("SITE_BASIC_AUTH_USER", "admin");
    vi.stubEnv("SITE_BASIC_AUTH_PASSWORD", "secret-pass");
    const validHeader = `Basic ${btoa("admin:secret-pass")}`;

    expect(isSiteBasicAuthConfigured()).toBe(true);
    expect(isValidBasicAuthAuthorization(validHeader)).toBe(true);
    expect(isValidBasicAuthAuthorization(`Basic ${btoa("admin:wrong-pass")}`)).toBe(false);
  });

  it("decodes a basic authorization header", () => {
    expect(decodeBasicAuthHeader(`Basic ${btoa("reader:123456")}`)).toEqual({
      username: "reader",
      password: "123456",
    });
    expect(decodeBasicAuthHeader("Bearer token")).toBeNull();
    expect(decodeBasicAuthHeader("Basic not-base64")).toBeNull();
    expect(decodeBasicAuthHeader(`Basic ${btoa("missing-separator")}`)).toBeNull();
  });
});
