import { chromium } from 'playwright';
import {
  disableCookiePrompt,
  login as redHatSsoLogin,
} from '@redhat-cloud-services/playwright-test-auth';

const TARGET_URL = process.env.UI_TEST_TARGET_URL;
const TARGET_HOST = 'console.stage.redhat.com';
const SHOW_COOKIE_PROMPT = process.env.UI_HARNESS_SHOW_COOKIE_PROMPT === '1';
const SSO_HOSTS = new Set([
  'sso.stage.redhat.com',
  'sso.redhat.com',
  'identity.redhat.com',
  'access.redhat.com',
]);
let credentialSubmissionStarted = false;

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

async function main() {
  const username = process.env.UI_TEST_USERNAME;
  const password = process.env.UI_TEST_PASSWORD;
  if (!username || !password || !TARGET_URL) {
    return { status: 'blocked', message: 'Missing local sign-in configuration.' };
  }

  let browser;
  let page;
  try {
    browser = await chromium.connectOverCDP('http://127.0.0.1:9222', { timeout: 10000 });
    const pages = browser.contexts().flatMap((context) => context.pages());
    page = pages.find((candidate) => {
      try {
        return new URL(candidate.url()).hostname === TARGET_HOST;
      } catch {
        return false;
      }
    }) || pages[0];
    if (!page) {
      return { status: 'blocked', message: 'No browser page is available for sign-in.' };
    }

    // Install the package's TrustArc request blocker before re-entering Stage.
    await disableCookiePrompt(page);
    await page.goto(TARGET_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });

    if (await hasSignedInUserMenu(page)) {
      return {
        status: 'already_authenticated',
        message: 'The Insights Chrome User Avatar control is visible. Verify the account and org context before testing.',
      };
    }

    const usernameField = page.getByLabel('Red Hat login').first();
    try {
      await usernameField.waitFor({ state: 'visible', timeout: 30000 });
    } catch {
      const currentHost = new URL(page.url()).hostname;
      if (currentHost === TARGET_HOST) {
        if (await hasSignedInUserMenu(page)) {
          return {
            status: 'already_authenticated',
            message: 'The Insights Chrome User Avatar control is visible. Verify the account and org context before testing.',
          };
        }
        return {
          status: 'authentication_unconfirmed',
          message: 'Stage loaded without an SSO form, but the signed-in User Avatar control was not found. Do not assume authentication.',
        };
      }
      return {
        status: 'sign_in_form_not_found',
        message: 'The standard Red Hat SSO login form did not appear. Report the sign-in blocker.',
      };
    }

    credentialSubmissionStarted = true;
    await redHatSsoLogin(withBaseUrl(page), username, password);
    if (SHOW_COOKIE_PROMPT) {
      await page.unroute('**/*');
      await page.goto(TARGET_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
    }
    if (new URL(page.url()).hostname !== TARGET_HOST) {
      return {
        status: 'login_unconfirmed',
        credential_submission_started: true,
        message: 'The SSO helper completed without returning to the Stage console. Do not retry in this cycle.',
      };
    }
    if (!(await hasSignedInUserMenu(page, 60000))) {
      return {
        status: 'login_unconfirmed',
        credential_submission_started: true,
        message: 'Stage loaded after SSO, but the signed-in User Avatar control was not found. Do not assume authentication or retry in this cycle.',
      };
    }
    return {
      status: 'authenticated',
      credential_submission_started: true,
      message: 'Stage loaded and the Insights Chrome User Avatar control is visible. Verify the account and org context before testing.',
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : '';
    if (/Invalid login credentials/i.test(message)) {
      return {
        status: 'authentication_failed',
        credential_submission_started: credentialSubmissionStarted,
        message: 'Red Hat SSO rejected the configured test account. Do not retry in this cycle.',
      };
    }
    if (/Lockdown/i.test(message)) {
      return {
        status: 'blocked',
        credential_submission_started: credentialSubmissionStarted,
        message: 'The Stage proxy returned a Lockdown page. Report the proxy blocker.',
      };
    }
    if (credentialSubmissionStarted) {
      return {
        status: 'login_unconfirmed',
        credential_submission_started: true,
        message: 'The SSO helper could not confirm Stage sign-in. Do not retry in this cycle.',
      };
    }
    return {
      status: 'blocked',
      credential_submission_started: false,
      message: 'The local SSO helper could not prepare the Stage login flow.',
    };
  } finally {
    if (page) await clearLoginFields(page);
    if (browser) await browser.close();
  }
}

main().then(
  (result) => process.stdout.write(`${JSON.stringify({
    credential_submission_started: credentialSubmissionStarted,
    ...result,
  })}\n`),
  () => process.stdout.write(`${JSON.stringify({
    status: 'blocked',
    credential_submission_started: credentialSubmissionStarted,
    message: 'The local SSO helper stopped unexpectedly. Do not retry if a password submission was attempted.',
  })}\n`),
);
