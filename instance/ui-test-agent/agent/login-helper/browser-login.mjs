import { chromium } from 'playwright';
import {
  disableCookiePrompt,
  login as redHatSsoLogin,
} from '@redhat-cloud-services/playwright-test-auth';

const TARGET_URL = process.env.UI_TEST_TARGET_URL;
const TARGET_HOST = 'console.stage.redhat.com';
const SHARED_CDP_URL = process.env.UI_TEST_CDP_URL || 'http://127.0.0.1:9222';
const LOGIN_DEADLINE_MS = 200_000;
const SSO_HOSTS = new Set([
  'sso.stage.redhat.com',
  'sso.redhat.com',
  'identity.redhat.com',
  'access.redhat.com',
]);
const AUTH_ORIGINS = new Set([TARGET_HOST, ...SSO_HOSTS]);
const AUTH_COOKIE_DOMAINS = new Set([...AUTH_ORIGINS, 'redhat.com']);
const CREDENTIAL_REJECTION_TEXT =
  /\b(?:invalid|incorrect|wrong)\s+(?:username|password|credentials|login)(?:\s+or\s+(?:username|password))?\b|\b(?:username|password|credentials)(?:\s+or\s+(?:username|password))?\s+(?:is|are)\s+(?:invalid|incorrect|wrong)\b/i;
let phase = 'validate_configuration';
let credentialSubmissionStarted = false;

function result(status, diagnosticCode, extra = {}) {
  return {
    status,
    diagnostic_phase: phase,
    diagnostic_code: diagnosticCode,
    ...extra,
  };
}

async function hasVisibleText(page, textPattern, allowedHosts) {
  if (!page) return false;
  try {
    const hostname = new URL(page.url()).hostname;
    if (!allowedHosts.has(hostname)) return false;
    await page
      .getByText(textPattern)
      .first()
      .waitFor({ state: 'visible', timeout: 1000 });
    return true;
  } catch {
    return false;
  }
}

function hasCredentialRejectionText(message) {
  return CREDENTIAL_REJECTION_TEXT.test(message);
}

async function hasCredentialRejectionMessage(page) {
  return hasVisibleText(page, CREDENTIAL_REJECTION_TEXT, SSO_HOSTS);
}

async function hasProxyLockdownMessage(page) {
  return hasVisibleText(page, /\blockdown\b/i, AUTH_ORIGINS);
}

async function hasSignedInUserMenu(page, timeout = 5000) {
  try {
    await page
      .getByRole('button', { name: /User Avatar/ })
      .first()
      .waitFor({ state: 'visible', timeout });
    return true;
  } catch {
    return false;
  }
}

function withBaseUrl(page) {
  return new Proxy(page, {
    get(target, property) {
      if (property === 'goto') {
        return (url, options) => target.goto(new URL(url, `${TARGET_URL}/`).href, options);
      }
      const value = Reflect.get(target, property, target);
      return typeof value === 'function' ? value.bind(target) : value;
    },
  });
}

async function clearLoginFields(page) {
  try {
    if (!SSO_HOSTS.has(new URL(page.url()).hostname)) return;
  } catch {
    return;
  }
  for (const selector of [
    'input[type="password"]',
    'input[autocomplete="username"], input[type="email"]',
  ]) {
    try {
      await page.locator(selector).fill('', { timeout: 1000 });
    } catch {
      // Navigation may already have replaced the sign-in document.
    }
  }
}

function browserEnvironment() {
  const env = { ...process.env };
  delete env.UI_TEST_USERNAME;
  delete env.UI_TEST_PASSWORD;
  delete env.UI_HARNESS_USERNAME;
  delete env.UI_HARNESS_PASSWORD;
  return env;
}

function sessionOrigins(storageState) {
  const storageByOrigin = new Map(
    storageState.origins
      .filter(({ origin }) => AUTH_ORIGINS.has(new URL(origin).hostname))
      .map(({ origin, localStorage }) => [origin, localStorage]),
  );
  for (const hostname of AUTH_ORIGINS) {
    const origin = `https://${hostname}`;
    if (!storageByOrigin.has(origin)) storageByOrigin.set(origin, []);
  }
  return [...storageByOrigin].map(([origin, localStorage]) => ({ origin, localStorage }));
}

async function transferSession(storageState, targetUrl, browsers) {
  const agentBrowser = await chromium.connectOverCDP(SHARED_CDP_URL, { timeout: 10000 });
  browsers.agent = agentBrowser;
  const context = agentBrowser.contexts()[0];
  const pages = context.pages();
  const page = pages.find((candidate) => {
    try {
      return new URL(candidate.url()).hostname === TARGET_HOST;
    } catch {
      return false;
    }
  }) || pages[0] || await context.newPage();

  await context.clearCookies();
  const cookies = storageState.cookies.filter((cookie) =>
    AUTH_COOKIE_DOMAINS.has(cookie.domain.replace(/^\./, '')),
  );
  await context.addCookies(cookies);
  await context.addInitScript((origins) => {
    const current = origins.find(({ origin }) => origin === location.origin);
    if (!current) return;
    localStorage.clear();
    for (const { name, value } of current.localStorage) {
      localStorage.setItem(name, value);
    }
  }, sessionOrigins(storageState));
  await disableCookiePrompt(page);
  await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
  if (!(await hasSignedInUserMenu(page, 45000))) {
    throw new Error('Transferred Stage session was not confirmed in the agent browser.');
  }
  return agentBrowser;
}

async function runLogin(username, password, browsers) {
  const proxy = process.env.UI_BROWSER_PROXY;
  if (!proxy) {
    return result('blocked', 'proxy_configuration_missing', {
      credential_submission_started: false,
    });
  }

  phase = 'launch_browser';
  const loginBrowser = await chromium.launch({
    headless: true,
    proxy: { server: proxy },
    env: browserEnvironment(),
    args: [
      '--no-sandbox',
      '--disable-dev-shm-usage',
      '--disable-extensions',
      '--ignore-certificate-errors',
      '--host-resolver-rules=MAP consent.trustarc.com 127.0.0.1',
      '--proxy-bypass-list=localhost;127.0.0.1;::1',
    ],
  });
  browsers.login = loginBrowser;
  const context = await loginBrowser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.setDefaultNavigationTimeout(30000);
  try {
    phase = 'prepare_browser';
    await disableCookiePrompt(page);
    phase = 'navigate_to_stage';
    await page.goto(TARGET_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    if (await hasProxyLockdownMessage(page)) {
      return result('blocked', 'proxy_lockdown', {
        credential_submission_started: false,
      });
    }

    phase = 'wait_for_sso_form';
    const usernameField = page.getByLabel('Red Hat login').first();
    try {
      await usernameField.waitFor({ state: 'visible', timeout: 15000 });
    } catch {
      if (await hasProxyLockdownMessage(page)) {
        return result('blocked', 'proxy_lockdown', {
          credential_submission_started: false,
        });
      }
      return result('sign_in_form_not_found', 'sso_form_missing', {
        credential_submission_started: false,
      });
    }

    phase = 'submit_credentials';
    credentialSubmissionStarted = true;
    await redHatSsoLogin(withBaseUrl(page), username, password);
    if (await hasCredentialRejectionMessage(page)) {
      return result('authentication_failed', 'sso_rejected_credentials', {
        credential_submission_started: true,
      });
    }
    if (await hasProxyLockdownMessage(page)) {
      return result('blocked', 'proxy_lockdown', {
        credential_submission_started: true,
      });
    }

    phase = 'verify_stage_session';
    if (new URL(page.url()).hostname !== TARGET_HOST) {
      return result('login_unconfirmed', 'stage_return_missing', {
        credential_submission_started: true,
      });
    }
    if (!(await hasSignedInUserMenu(page, 45000))) {
      return result('login_unconfirmed', 'signed_in_marker_missing_after_sso', {
        credential_submission_started: true,
      });
    }

    phase = 'transfer_session';
    await transferSession(await context.storageState(), TARGET_URL, browsers);
    return result('authenticated', 'signed_in_marker_confirmed', {
      credential_submission_started: true,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : '';
    if (
      hasCredentialRejectionText(message) ||
      await hasCredentialRejectionMessage(page)
    ) {
      return result('authentication_failed', 'sso_rejected_credentials', {
        credential_submission_started: credentialSubmissionStarted,
      });
    }
    if (/Lockdown/i.test(message) || await hasProxyLockdownMessage(page)) {
      return result('blocked', 'proxy_lockdown', {
        credential_submission_started: credentialSubmissionStarted,
      });
    }
    return result(
      credentialSubmissionStarted ? 'login_unconfirmed' : 'blocked',
      credentialSubmissionStarted ? 'sso_flow_error' : 'browser_preparation_error',
      {
        credential_submission_started: credentialSubmissionStarted,
      },
    );
  } finally {
    await clearLoginFields(page);
    await loginBrowser.close();
  }
}

async function closeBrowsers(browsers) {
  await Promise.all(Object.values(browsers).map((browser) => browser?.close().catch(() => {})));
}

let activeBrowsers = {};
process.once('SIGTERM', () => {
  void closeBrowsers(activeBrowsers).finally(() => process.exit(143));
});

async function main() {
  const username = process.env.UI_TEST_USERNAME;
  const password = process.env.UI_TEST_PASSWORD;
  if (!username || !password || !TARGET_URL) {
    return result('blocked', 'missing_login_configuration', {
      credential_submission_started: false,
    });
  }

  const browsers = {};
  activeBrowsers = browsers;
  let deadline;
  try {
    return await Promise.race([
      runLogin(username, password, browsers),
      new Promise((_, reject) => {
        deadline = setTimeout(() => {
          void closeBrowsers(browsers);
          reject(new Error('Stage sign-in deadline exceeded.'));
        }, LOGIN_DEADLINE_MS);
      }),
    ]);
  } catch (error) {
    const deadlineExceeded =
      error instanceof Error && error.message === 'Stage sign-in deadline exceeded.';
    return result(
      credentialSubmissionStarted ? 'login_unconfirmed' : 'blocked',
      deadlineExceeded
        ? 'login_deadline_exceeded'
        : credentialSubmissionStarted
          ? 'sso_flow_error'
          : 'browser_preparation_error',
      { credential_submission_started: credentialSubmissionStarted },
    );
  } finally {
    clearTimeout(deadline);
    await closeBrowsers(browsers);
  }
}

main().then(
  (result) => process.stdout.write(`${JSON.stringify(result)}\n`),
  () => process.stdout.write(`${JSON.stringify({
    status: 'blocked',
    diagnostic_phase: phase,
    diagnostic_code: 'browser_process_unhandled',
    credential_submission_started: credentialSubmissionStarted,
  })}\n`),
);
