import { test, expect } from '@playwright/test';

/**
 * BAD EXAMPLE - Multiple anti-patterns
 * - Hard-coded sleeps (setTimeout, waitForTimeout)
 * - Disabled tests (test.skip)
 * - Missing assertions
 * - Broad try/catch hiding failures
 */

test.describe('Checkout Flow', () => {
  // ANTI-PATTERN: Disabled test
  test.skip('should add item to cart', async ({ page }) => {
    await page.goto('/products');
    await page.click('.product-card:first-child .add-to-cart');
  });

  test('should complete checkout process', async ({ page }) => {
    await page.goto('/cart');

    // ANTI-PATTERN: Hard-coded sleep
    await page.click('#checkout-button');
    await page.waitForTimeout(3000); // Wait for redirect

    // Fill shipping info
    await page.fill('#address', '123 Main St');
    await page.fill('#city', 'Springfield');

    // ANTI-PATTERN: Another hard-coded sleep
    await page.click('#submit-shipping');
    await new Promise(resolve => setTimeout(resolve, 2000));

    // ANTI-PATTERN: No assertion - test doesn't verify anything!
    await page.click('#complete-order');
  });

  test('should validate payment form', async ({ page }) => {
    await page.goto('/checkout/payment');

    // Fill invalid card
    await page.fill('#card-number', '1234');
    await page.click('#submit-payment');

    // ANTI-PATTERN: Broad try/catch hides real failures
    try {
      const error = page.locator('.error');
      await error.waitFor({ timeout: 1000 });
      // ANTI-PATTERN: No assertion on error content
    } catch (e) {
      // Silently pass if error doesn't appear
    }
  });

  // ANTI-PATTERN: Disabled test with todo comment
  test.skip('TODO: fix flaky test - should handle slow network', async ({ page }) => {
    await page.goto('/products', { waitUntil: 'domcontentloaded' });

    // ANTI-PATTERN: Hard-coded sleep for "slow network"
    await page.waitForTimeout(5000);

    // Click on product
    await page.click('.product-card:first-child');

    // ANTI-PATTERN: Missing assertion
  });

  test('should update cart quantity', async ({ page }) => {
    await page.goto('/cart');

    const quantityInput = page.locator('#quantity-1');
    await quantityInput.fill('3');

    // ANTI-PATTERN: Hard-coded sleep instead of waiting for update
    await page.waitForTimeout(1000);

    // ANTI-PATTERN: Weak assertion - should verify actual value
    await expect(quantityInput).toBeVisible();
  });
});
