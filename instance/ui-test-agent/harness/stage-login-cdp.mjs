import { setTimeout as delay } from 'node:timers/promises';

const TARGET_URL = process.env.UI_TEST_TARGET_URL;
const LOGIN_HOSTS = new Set([
  'console.stage.redhat.com',
  'sso.redhat.com',
  'identity.redhat.com',
  'access.redhat.com',
]);

class CdpConnection {
  constructor(socket) {
    this.socket = socket;
    this.nextId = 1;
    this.pending = new Map();
    socket.addEventListener('message', (event) => {
      let packet;
      try {
        packet = JSON.parse(event.data);
      } catch {
        return;
      }
      const waiting = this.pending.get(packet.id);
      if (!waiting) return;
      clearTimeout(waiting.timer);
      this.pending.delete(packet.id);
      if (packet.error) waiting.reject(new Error('CDP command failed'));
      else waiting.resolve(packet.result ?? {});
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error('CDP command timed out'));
      }, 15000);
      this.pending.set(id, { resolve, reject, timer });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expression) {
    const result = await this.send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (result.exceptionDetails) throw new Error('Page evaluation failed');
    return result.result?.value;
  }
}

function visibleFieldScript(kind, value = '') {
  const serializedValue = JSON.stringify(value);
  return `(() => {
    const visible = (element) => !!(element.offsetWidth || element.offsetHeight || element.getClientRects().length);
    const inputs = Array.from(document.querySelectorAll('input')).filter(visible);
    const field = ${kind === 'username'
      ? `inputs.find((el) => el.type === 'email' || /user|email|login/i.test([el.name, el.id, el.autocomplete].join(' ')))`
      : `inputs.find((el) => el.type === 'password')`};
    const allowed = ${JSON.stringify([...LOGIN_HOSTS])};
    if (location.protocol !== 'https:' || !allowed.includes(location.hostname)) {
      return { found: false, host: location.hostname, rejected_host: true };
    }
    if (!field) return { found: false, host: location.hostname };
    const value = ${serializedValue};
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(field, value);
    field.dispatchEvent(new Event('input', { bubbles: true }));
    field.dispatchEvent(new Event('change', { bubbles: true }));
    return { found: true, host: location.hostname };
  })()`;
}

async function clickContinue(cdp, passwordStep = false) {
  return cdp.evaluate(`(() => {
    const visible = (element) => !!(element.offsetWidth || element.offsetHeight || element.getClientRects().length);
    const controls = Array.from(document.querySelectorAll('button, input[type=submit], [role=button]')).filter(visible);
    const textOf = (el) => (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
    const preferred = ${passwordStep ? '/sign in|log in|submit|continue/i' : '/next|continue|sign in|log in/i'};
    const button = controls.find((el) => preferred.test(textOf(el)));
    if (button) { button.click(); return true; }
    const form = document.querySelector('form');
    if (form?.requestSubmit) { form.requestSubmit(); return true; }
    return false;
  })()`);
}

async function waitForPassword(cdp) {
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    const result = await cdp.evaluate(`(() => {
      const visible = (element) => !!(element.offsetWidth || element.offsetHeight || element.getClientRects().length);
      const field = Array.from(document.querySelectorAll('input[type=password]')).find(visible);
      return { found: !!field, host: location.hostname, protocol: location.protocol };
    })()`);
    if (result.found || result.protocol !== 'https:' || !LOGIN_HOSTS.has(result.host)) return result;
    await delay(500);
  }
  return { found: false, host: '' };
}

async function main() {
  const username = process.env.UI_TEST_USERNAME;
  const password = process.env.UI_TEST_PASSWORD;
  if (!username || !password || !TARGET_URL) throw new Error('Missing local configuration');

  const response = await fetch('http://127.0.0.1:9222/json/list');
  const pages = await response.json();
  const page = pages.find((item) => item.type === 'page' && item.webSocketDebuggerUrl);
  if (!page) throw new Error('No browser page is available');
  const entryUrl = new URL(page.url);
  if (entryUrl.protocol !== 'https:' || !LOGIN_HOSTS.has(entryUrl.hostname)) {
    return { status: 'blocked', message: 'The browser is not on the configured stage sign-in flow; credentials were not entered.' };
  }

  const socket = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', () => reject(new Error('Browser connection failed')), { once: true });
  });
  const cdp = new CdpConnection(socket);
  try {
    await cdp.send('Runtime.enable');
    const form = await cdp.evaluate(`(() => {
      const visible = (element) => !!(element.offsetWidth || element.offsetHeight || element.getClientRects().length);
      const inputs = Array.from(document.querySelectorAll('input')).filter(visible);
      return {
        username: inputs.some((el) => el.type === 'email' || /user|email|login/i.test([el.name, el.id, el.autocomplete].join(' '))),
        password: inputs.some((el) => el.type === 'password'),
        host: location.hostname,
        protocol: location.protocol
      };
    })()`);
    const hasLoginForm = form.username || form.password;
    if (hasLoginForm && (form.protocol !== 'https:' || !LOGIN_HOSTS.has(form.host))) {
      return { status: 'blocked', message: 'The sign-in page is on an unapproved host; credentials were not entered.' };
    }
    if (!hasLoginForm) {
      return { status: 'sign_in_form_not_found', message: 'No standard sign-in form was found. Inspect the page and report the blocker if authentication is required.' };
    }

    if (form.username) {
      const filledUser = await cdp.evaluate(visibleFieldScript('username', username));
      if (filledUser.rejected_host) {
        return { status: 'blocked', message: 'The sign-in page is on an unapproved host; credentials were not entered.' };
      }
      if (!filledUser.found) throw new Error('Username field unavailable');
    }

    if (form.username && !form.password) {
      const submitted = await clickContinue(cdp, false);
      if (!submitted) throw new Error('Username step could not be submitted');
      const step = await waitForPassword(cdp);
      if (step.host && (step.protocol !== 'https:' || !LOGIN_HOSTS.has(step.host))) {
        return { status: 'blocked', message: 'The identity provider redirected to an unapproved host; password was not entered.' };
      }
      if (!step.found) {
        return { status: 'password_step_not_found', message: 'The expected password step did not appear. Inspect the page and report the blocker.' };
      }
    }

    const filledPassword = await cdp.evaluate(visibleFieldScript('password', password));
    if (filledPassword.rejected_host) {
      return { status: 'blocked', message: 'The sign-in page is on an unapproved host; credentials were not entered.' };
    }
    if (!filledPassword.found) throw new Error('Password field unavailable');
    const submitted = await clickContinue(cdp, true);
    if (!submitted) throw new Error('Password step could not be submitted');
    try {
      await cdp.evaluate(`(() => {
        const clear = (selector) => Array.from(document.querySelectorAll(selector)).forEach((field) => {
          const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
          setter.call(field, '');
          field.dispatchEvent(new Event('input', { bubbles: true }));
        });
        clear('input[type=password]');
        clear('input[type=email], input[autocomplete=username], input[name*=user i], input[id*=user i]');
        return true;
      })()`);
    } catch {
      // A successful redirect may destroy the sign-in document before fields clear.
    }
    await delay(5000);
    return {
      status: 'credentials_submitted',
      message: 'Submitted the configured test account. Inspect the browser to confirm sign-in and account/org context.',
    };
  } finally {
    socket.close();
  }
}

main().then(
  (result) => process.stdout.write(`${JSON.stringify(result)}\n`),
  () => process.stdout.write(`${JSON.stringify({
    status: 'blocked',
    message: 'The local login helper could not complete the sign-in flow. Inspect the browser and report the blocker.',
  })}\n`),
);
