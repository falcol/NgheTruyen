export const SITE_BASIC_AUTH_USER_ENV_KEY = "SITE_BASIC_AUTH_USER";
export const SITE_BASIC_AUTH_PASSWORD_ENV_KEY = "SITE_BASIC_AUTH_PASSWORD";
export const SITE_BASIC_AUTH_REALM = "NgheTruyen";

export function getSiteBasicAuthCredentials() {
  return {
    username: process.env[SITE_BASIC_AUTH_USER_ENV_KEY]?.trim() ?? "",
    password: process.env[SITE_BASIC_AUTH_PASSWORD_ENV_KEY]?.trim() ?? "",
  };
}

export function isSiteBasicAuthConfigured() {
  const { username, password } = getSiteBasicAuthCredentials();
  return username.length > 0 && password.length > 0;
}

export function decodeBasicAuthHeader(authorizationHeader?: string | null) {
  if (!authorizationHeader?.startsWith("Basic ")) {
    return null;
  }

  const encodedValue = authorizationHeader.slice("Basic ".length).trim();
  if (!encodedValue) {
    return null;
  }

  try {
    const decodedValue = atob(encodedValue);
    const separatorIndex = decodedValue.indexOf(":");

    if (separatorIndex <= 0) {
      return null;
    }

    return {
      username: decodedValue.slice(0, separatorIndex),
      password: decodedValue.slice(separatorIndex + 1),
    };
  } catch {
    return null;
  }
}

export function isValidBasicAuthAuthorization(authorizationHeader?: string | null) {
  const credentials = decodeBasicAuthHeader(authorizationHeader);
  if (!credentials) {
    return false;
  }

  const expectedCredentials = getSiteBasicAuthCredentials();
  return (
    expectedCredentials.username.length > 0 &&
    expectedCredentials.password.length > 0 &&
    credentials.username === expectedCredentials.username &&
    credentials.password === expectedCredentials.password
  );
}
